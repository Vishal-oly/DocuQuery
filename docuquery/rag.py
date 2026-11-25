"""RAG orchestration, citation formatting, and an offline extractive fallback."""

import logging
import re
from typing import Any

from .llm import (
    LLMError,
    answer_from_context,
    generate_questions,
    generate_structured_summary,
    looks_non_english,
    translate_query,
)

_PAGE_REF = re.compile(r"\[\s*p\.?\s*\d+(?:\s*[,–-]\s*\d+)*\s*\]", re.IGNORECASE)
_ANY_BRACKET = re.compile(r"\[[^\]\n]{1,24}\]")

QUESTION_INTENT = re.compile(
    r"\b(question|questions|quiz|mcq|mcqs|viva|exam|assignment|question bank|interview)\b",
    re.IGNORECASE,
)
QUESTION_TRIGGER = re.compile(
    r"\b(give|generate|make|create|suggest|list|prepare|frame|write|some|few|more|ask)\b",
    re.IGNORECASE,
)

BROAD_QUESTION = re.compile(
    r"\b(objective|main idea|overview|summar\w*|what is this paper|what is the paper about|"
    r"purpose|aim|goal|introduction|abstract|in short|briefly)\b",
    re.IGNORECASE,
)

SUMMARY_QUERIES = (
    "What research problem, objective, motivation, and contribution does the paper state?",
    "What method, methodology, model, algorithm, or experimental approach is used?",
    "What dataset, materials, participants, benchmarks, or data sources are used?",
    "What are the main experimental results, findings, and measurements?",
    "What limitations, threats to validity, or future work does the paper mention?",
    "What conclusion and implications does the paper report?",
)
SUMMARY_FIELDS = {
    "objective": ("objective", "aim", "purpose", "problem", "motivation", "propose", "contribution"),
    "methodology": ("method", "approach", "model", "algorithm", "we use", "procedure", "framework"),
    "dataset": ("dataset", "data", "benchmark", "participants", "sample", "corpus", "materials"),
    "key_findings": ("result", "finding", "accuracy", "performance", "outperform", "improve", "show that"),
    "limitations": ("limitation", "challenge", "future work", "threat", "however", "weakness"),
    "conclusion": ("conclusion", "conclude", "in summary", "implication", "overall"),
}


LOGGER = logging.getLogger(__name__)


def sanitize_answer(text: str) -> str:
    """Keep page citations, drop the paper's own reference numbers.

    Small models happily copy bracketed numbers such as [33.31] or [28.6] out of the
    source text, which look like citations but point nowhere. Only [p. N] survives.
    """
    if not text:
        return text
    def keep(match: re.Match) -> str:
        value = match.group(0)
        if _PAGE_REF.fullmatch(value):
            return value
        inner = value[1:-1].strip()
        # Drop the paper's own numeric references ("[33.31]", "[1, 2]") but keep
        # meaningful labels such as "[Figure 3]" or "[Table 2]".
        return "" if re.fullmatch(r"[\d.,;:\s–—-]{1,24}", inner) else value

    cleaned = _ANY_BRACKET.sub(keep, text)
    # The chat bubble is plain text, so Markdown emphasis looks like clutter.
    cleaned = re.sub(r"^\s{0,3}#{1,6}\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\*\*(.+?)\*\*", r"\1", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"(?<![\w*])__(.+?)__(?![\w*])", r"\1", cleaned, flags=re.DOTALL)
    cleaned = cleaned.replace("`", "")
    cleaned = re.sub(r"^\s*\*\s+", "• ", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^\s*[-•]\s+", "• ", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^\s*\|?[\s:\-|]{6,}\|?\s*$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([.,;:])", r"\1", cleaned)
    cleaned = re.sub(r"(\[\s*p\.?\s*\d+\s*\])(?:\s*\1)+", r"\1", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def wants_mcq(question: str) -> bool:
    return bool(re.search(r"\b(mcq|mcqs|multiple[- ]choice|objective questions?)\b", question or "", re.IGNORECASE))


def wants_questions(question: str) -> bool:
    return bool(QUESTION_INTENT.search(question or "") and QUESTION_TRIGGER.search(question or ""))


def is_broad_question(question: str) -> bool:
    text = (question or "").strip()
    if len(text.split()) <= 6 and BROAD_QUESTION.search(text):
        return True
    return bool(BROAD_QUESTION.search(text))


def _intro_chunks(repository, session_id: str, paper_id: str, limit: int = 4) -> list[dict[str, Any]]:
    """Opening pages carry the objective and abstract, which embeddings often miss."""
    try:
        chunks = repository.list_chunks(session_id, paper_id)
    except Exception:
        return []
    picked = [chunk for chunk in chunks if int(chunk.get("page_number") or 99) <= 2]
    picked.extend(
        chunk for chunk in chunks
        if str(chunk.get("section") or "").lower() in {"abstract", "introduction"}
    )
    unique, seen = [], set()
    for chunk in picked:
        identity = _chunk_identity(chunk)
        if identity in seen:
            continue
        seen.add(identity)
        unique.append({**chunk, "similarity": float(chunk.get("similarity") or 0.0)})
    return unique[:limit]


def _spread_chunks(repository, session_id: str, paper_id: str, limit: int = 8) -> list[dict[str, Any]]:
    """Sample chunks evenly across the paper so generated questions cover more pages."""
    try:
        chunks = repository.list_chunks(session_id, paper_id)
    except Exception:
        return []
    chunks = [chunk for chunk in chunks if len(str(chunk.get("content") or "")) >= 80]
    if len(chunks) <= limit:
        return chunks
    step = len(chunks) / float(limit)
    picked = [chunks[int(index * step)] for index in range(limit)]
    return [{**chunk, "similarity": float(chunk.get("similarity") or 0.0)} for chunk in picked]


def _excerpt(chunk: dict[str, Any], limit: int = 300) -> str:
    """One clean quote: no stray page numbers, no half sentences."""
    text = re.sub(r"\s+", " ", _content(chunk)).strip()
    text = re.sub(r"^\d{1,3}\s+", "", text)
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    if end > 100:
        return cut[: end + 1]
    space = cut.rfind(" ")
    return (cut[:space] if space > 100 else cut).rstrip(",;:") + "…"


def _fallback_answer(error: Exception, chunks: list[dict[str, Any]]) -> str:
    quotes = [
        f"• p. {_page_number(chunk)} — “{_excerpt(chunk)}”"
        for chunk in chunks[:3]
    ]
    return (
        "The local model is not running, so here are the exact passages from your paper "
        "instead of a written answer:\n\n"
        + "\n\n".join(quotes)
        + "\n\nStart it with start.bat (or python local_ai.py) and ask again for a written, "
        "page-cited answer."
    )


def _page_number(chunk: dict[str, Any]) -> int:
    return int(chunk.get("page_number") or chunk.get("page") or 1)


def _section(chunk: dict[str, Any]) -> str:
    return str(chunk.get("section") or "Paper excerpt")


def _content(chunk: dict[str, Any]) -> str:
    return str(chunk.get("content") or "").strip()


def _chunk_identity(chunk: dict[str, Any]) -> str:
    return str(chunk.get("id") or f"{_page_number(chunk)}:{_section(chunk)}:{_content(chunk)[:120]}")


def retrieve_summary_chunks(repository, embedder, session_id: str, paper_id: str, fallback_chunks: list[dict[str, Any]], top_k: int = 2) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    try:
        for query in SUMMARY_QUERIES:
            vector = embedder.embed([query])[0]
            matches = repository.search_chunks(session_id, paper_id, vector, limit=top_k)
            for chunk in matches:
                identity = _chunk_identity(chunk)
                if identity not in seen:
                    seen.add(identity)
                    found.append(chunk)
    except Exception:
        # A failed retrieval should not break the summary: the uploaded text can still
        # produce an extractive brief. Q&A surfaces database errors explicitly.
        pass
    if not found:
        found = list(fallback_chunks[:12])
    return found


def format_context(chunks: list[dict[str, Any]], filename: str = "paper.pdf", max_chars: int = 18000) -> str:
    parts: list[str] = []
    total = 0
    for chunk in chunks:
        text = _content(chunk)
        if not text:
            continue
        kind = str(chunk.get("kind") or "text")
        label = {"table": "table", "formula": "equation/values"}.get(kind, "")
        type_note = f" | {label}" if label else ""
        header = f"[Source: {filename} | p. {_page_number(chunk)} | {_section(chunk)}{type_note}]"
        block = f"{header}\n{text}"
        remaining = max_chars - total
        if remaining <= 0:
            break
        if len(block) > remaining:
            block = block[:remaining]
        parts.append(block)
        total += len(block) + 2
    return "\n\n".join(parts)


_DATA_QUESTION = re.compile(
    r"\b(table|tables|accuracy|score|scores|result|results|number|numbers|value|values|"
    r"equation|equations|formula|formulas|metric|metrics|percentage|percent|f1|auc|rmse)\b",
    re.IGNORECASE,
)


def boost_data_chunks(question: str, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Nudge tables and equations up when the question is about numbers."""
    if not _DATA_QUESTION.search(question or ""):
        return chunks
    weighted = []
    for chunk in chunks:
        bonus = {"table": 0.06, "formula": 0.04}.get(str(chunk.get("kind") or ""), 0.0)
        weighted.append((float(chunk.get("similarity") or 0.0) + bonus, chunk))
    weighted.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _score, chunk in weighted]


def citation_sources(chunks: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    sources = []
    seen = set()
    for chunk in chunks:
        identity = _chunk_identity(chunk)
        if identity in seen:
            continue
        seen.add(identity)
        sources.append(
            {
                "page_number": _page_number(chunk),
                "section": _section(chunk),
                "excerpt": _content(chunk)[:360],
                "similarity": round(float(chunk.get("similarity") or 0), 3),
            }
        )
        if len(sources) >= limit:
            break
    return sources


def _sentences(chunks: list[dict[str, Any]]) -> list[tuple[str, int, str]]:
    values: list[tuple[str, int, str]] = []
    seen = set()
    for chunk in chunks:
        text = _content(chunk)
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
            sentence = re.sub(r"\s+", " ", sentence).strip(" •-\t")
            if len(sentence) < 35:
                continue
            key = sentence.lower()
            if key in seen:
                continue
            seen.add(key)
            values.append((sentence, _page_number(chunk), _section(chunk)))
    return values


def _best_extract(
    chunks: list[dict[str, Any]],
    keywords: tuple[str, ...],
    limit: int = 2,
    section_labels: tuple[str, ...] = (),
    allow_unmatched: bool = False,
) -> str:
    candidates = _sentences(chunks)
    ranked = []
    for sentence, page, section in candidates:
        lower = sentence.lower()
        section_lower = section.lower()
        word_hits = sum(1 for word in keywords if word in lower)
        section_hit = any(label in section_lower for label in section_labels)
        score = word_hits * 2.0 + (4.0 if section_hit else 0.0)
        if score > 0:
            # Prefer informative but not excessively long sentences after relevance is established.
            score += min(len(sentence), 220) / 1000
            ranked.append((score, sentence, page))
    if not ranked and allow_unmatched:
        ranked = [
            (min(len(sentence), 220) / 1000, sentence, page)
            for sentence, page, _section_name in candidates
        ]
    ranked.sort(key=lambda item: item[0], reverse=True)
    chosen: list[str] = []
    for _score, sentence, page in ranked:
        chosen.append(f"{sentence} [p. {page}]")
        if len(chosen) >= limit:
            break
    return " ".join(chosen) if chosen else "Not clearly stated in the retrieved text."


def extractive_summary(chunks: list[dict[str, Any]]) -> dict[str, str]:
    section_hints = {
        "objective": ("abstract", "introduction"),
        "methodology": ("method", "approach"),
        "dataset": ("data", "dataset"),
        "key_findings": ("result", "finding", "evaluation"),
        "limitations": ("limitation", "discussion"),
        "conclusion": ("conclusion",),
    }
    fields = {
        name: _best_extract(chunks, terms, section_labels=section_hints.get(name, ()))
        for name, terms in SUMMARY_FIELDS.items()
    }
    overview_parts = [fields["objective"], fields["key_findings"], fields["conclusion"]]
    overview = " ".join(part for part in overview_parts if part != "Not clearly stated in the retrieved text.")
    fields["overall_summary"] = overview or _best_extract(chunks, (), limit=3, allow_unmatched=True)
    return fields


def make_summary(repository, embedder, config: dict[str, Any], session_id: str, paper: dict[str, Any], fallback_chunks: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    chunks = retrieve_summary_chunks(
        repository, embedder, session_id, paper["id"], fallback_chunks, top_k=2
    )
    context = format_context(
        chunks,
        paper.get("filename", "paper.pdf"),
        int(config.get("SUMMARY_CONTEXT_CHARS", 9000)),
    )
    notice = None
    mode = "Quick extract (model off)"
    try:
        summary = generate_structured_summary(
            context,
            config,
        )
        mode = "Local model"
    except LLMError as exc:
        summary = extractive_summary(chunks)
        LOGGER.debug("Summary fell back to an extract: %s", exc)
        notice = (
            "The local model is not running yet, so this is a quick extract built from the "
            "paper's own sentences. Start the app with start.bat (or python local_ai.py) for a "
            "written summary."
        )
    # Summaries copy reference numbers from the paper just as answers do.
    summary = {
        key: sanitize_answer(value) if isinstance(value, str) else value
        for key, value in summary.items()
    }
    summary["mode"] = mode
    summary["notice"] = notice
    sources = citation_sources(chunks)
    return summary, sources


def answer_question(repository, embedder, config: dict[str, Any], session_id: str, paper: dict[str, Any], question: str, detail: str | None = None) -> dict[str, Any]:
    retrieval_question = question
    translated = None
    if looks_non_english(question):
        # The paper is usually English: translate the question just for retrieval.
        translated = translate_query(question, config)
        if translated:
            retrieval_question = translated
    vector = embedder.embed([retrieval_question])[0]
    chunks = boost_data_chunks(
        retrieval_question,
        repository.search_chunks(
            session_id,
            paper["id"],
            vector,
            limit=int(config.get("RAG_TOP_K", 4)),
        ),
    )
    sources = citation_sources(chunks, limit=6)
    if not chunks:
        return {
            "answer": "I could not find relevant text for that question in this paper.",
            "mode": "no matching passages",
            "sources": [],
        }

    question_mode = wants_questions(question)
    if question_mode:
        # Question generation needs breadth: sample across the whole paper, not 4 near vectors.
        spread = _spread_chunks(repository, session_id, paper["id"])
        known = {_chunk_identity(chunk) for chunk in chunks}
        chunks = chunks + [c for c in spread if _chunk_identity(c) not in known]
        sources = citation_sources(chunks, limit=6)

    if is_broad_question(question):
        # "Main objective" and friends need the opening pages, not just nearest vectors.
        intro = _intro_chunks(repository, session_id, paper["id"])
        known = {_chunk_identity(chunk) for chunk in chunks}
        chunks = intro + [c for c in chunks if _chunk_identity(c) not in known]
        sources = citation_sources(chunks, limit=6)

    context = format_context(chunks, paper.get("filename", "paper.pdf"), int(config.get("ANSWER_CONTEXT_CHARS", 12000)))
    try:
        if question_mode:
            mcq = wants_mcq(question)
            count = int(config.get("MCQ_COUNT" if mcq else "QUESTION_COUNT", 5 if mcq else 8))
            answer = generate_questions(context, config, count=count,
                                        style="mcq" if mcq else "exam")
            mode = "Generated MCQ quiz" if mcq else "Generated questions"
        else:
            answer = answer_from_context(
                question,
                context,
                config,
                detail,
            )
            mode = "Local model"
        answer = sanitize_answer(answer)
    except LLMError as exc:
        answer = sanitize_answer(_fallback_answer(exc, chunks))
        mode = "Passages only (model off)"
    if translated:
        mode = f"{mode} · asked in another language"
    return {"answer": answer, "mode": mode, "sources": sources}
