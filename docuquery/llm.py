"""Local model adapters (Ollama or any OpenAI-compatible server) and safe parsing."""

import json
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class LLMError(RuntimeError):
    pass


DEFAULT_MODEL = "qwen2.5:1.5b"
DEFAULT_OPENAI_BASE = "http://127.0.0.1:1234/v1"


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# Keep requests local even if a proxy is configured or the endpoint redirects.
_opener = build_opener(ProxyHandler({}), _NoRedirect())


def _http_json(url: str, payload=None, timeout: int = 120, headers: dict[str, str] | None = None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(url, data=data, headers={"Content-Type": "application/json", **(headers or {})})
    with _opener.open(request, timeout=timeout) as response:
        return json.load(response)


def _request(config: dict[str, Any], path: str, timeout: int, payload=None):
    port = config.get("OLLAMA_PORT", 11434)
    return _http_json(f"http://127.0.0.1:{port}{path}", payload, timeout)


def ollama_available(config: dict[str, Any]) -> bool:
    if not config.get("OLLAMA_ENABLED", True):
        return False
    model = config.get("OLLAMA_MODEL", DEFAULT_MODEL)
    tag = model if ":" in model else f"{model}:latest"
    try:
        return any(entry.get("name") == tag for entry in _request(config, "/api/tags", 1)["models"]
                   if isinstance(entry, dict))
    except (OSError, ValueError, KeyError, TypeError):
        return False


def _call_ollama(config: dict[str, Any], messages: list[dict[str, str]],
                 max_tokens: int, *, structured: bool = False) -> str:
    if not config.get("OLLAMA_ENABLED", True):
        raise LLMError("The local model is switched off.")
    model = config.get("OLLAMA_MODEL", DEFAULT_MODEL)
    payload = {
        "model": model, "messages": messages, "stream": False,
        "options": {"temperature": 0.15, "num_predict": max_tokens, "num_ctx": 8192},
    }
    if structured:
        payload["format"] = "json"
    try:
        result = _request(config, "/api/chat", config.get("OLLAMA_TIMEOUT_SECONDS", 120), payload)
        text = result["message"]["content"]
        if not isinstance(text, str) or not text.strip():
            raise LLMError("Ollama returned an empty response.")
        return text.strip()
    except HTTPError as exc:
        if exc.code == 404:
            raise LLMError(f"Local model not installed. Run: ollama pull {model}") from exc
        raise LLMError(f"Ollama rejected the request (HTTP {exc.code}).") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise LLMError(
            "The local model is not running. Start DocuQuery with start.bat "
            "(or run python local_ai.py) so it can load its own model."
        ) from exc
    except (ValueError, KeyError, TypeError) as exc:
        raise LLMError("Ollama returned an invalid response.") from exc


def _openai_settings(config: dict[str, Any]) -> tuple[str, str]:
    base = str(config.get("OPENAI_BASE_URL") or DEFAULT_OPENAI_BASE).rstrip("/")
    return base, str(config.get("OPENAI_MODEL") or "").strip()


def _openai_candidates(config: dict[str, Any]) -> list[str]:
    """Configured URL first, then the common local server ports."""
    candidates = [_openai_settings(config)[0]]
    for port in (1234, 8080):
        base = f"http://127.0.0.1:{port}/v1"
        if base not in candidates:
            candidates.append(base)
    return candidates


def _openai_headers(config: dict[str, Any]) -> dict[str, str]:
    key = str(config.get("OPENAI_API_KEY") or "").strip()
    return {"Authorization": f"Bearer {key}"} if key else {}


def _models_at(base: str, config: dict[str, Any], timeout: float | None = None) -> list[str]:
    result = _http_json(f"{base}/models", None,
                        timeout or config.get("OPENAI_TIMEOUT_SECONDS", 2),
                        _openai_headers(config))
    return [str(item["id"]) for item in result.get("data", [])
            if isinstance(item, dict) and item.get("id")]


def resolve_openai_server(config: dict[str, Any]) -> tuple[str, list[str]] | None:
    """Return the first local server that answers, so the app finds it by itself."""
    for base in _openai_candidates(config):
        try:
            models = _models_at(base, config, 1)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
        if models:
            return base, models
    return None


def openai_available(config: dict[str, Any]) -> bool:
    """True when a local OpenAI-compatible server (LM Studio, llama.cpp, Jan) answers."""
    if str(config.get("LLM_BACKEND", "auto")).lower() == "ollama":
        return False
    return resolve_openai_server(config) is not None


def _select_backend(config: dict[str, Any]) -> str:
    choice = str(config.get("LLM_BACKEND", "auto")).strip().lower()
    if choice in {"ollama", "openai"}:
        return choice
    if ollama_available(config):
        return "ollama"
    if openai_available(config):
        return "openai"
    return "ollama"


def _call_openai(config: dict[str, Any], messages: list[dict[str, str]],
                 max_tokens: int, *, structured: bool = False) -> str:
    model = _openai_settings(config)[1]
    headers = _openai_headers(config)
    timeout = config.get("OPENAI_TIMEOUT_SECONDS", 120)
    resolved = resolve_openai_server(config)
    if resolved is None:
        raise LLMError(
            "No local model server answered. Start DocuQuery with start.bat "
            "(it runs its own model server), or start Ollama/LM Studio."
        )
    base, models = resolved
    payload: dict[str, Any] = {
        "messages": messages, "temperature": 0.15, "max_tokens": max_tokens, "stream": False,
    }
    if structured:
        payload["response_format"] = {"type": "json_object"}
    try:
        if not model:
            model = models[0]
        payload["model"] = model
        result = _http_json(f"{base}/chat/completions", payload, timeout, headers)
        text = result["choices"][0]["message"]["content"]
        if not isinstance(text, str) or not text.strip():
            raise LLMError("The local model returned an empty response.")
        return text.strip()
    except HTTPError as exc:
        raise LLMError(
            f"Local server at {base} rejected the request (HTTP {exc.code}). "
            "Check that a model is loaded."
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise LLMError(
            f"Cannot reach a local model server at {base}. Start LM Studio's local server "
            "(Developer tab -> Start Server), Ollama, or use start.bat."
        ) from exc
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        raise LLMError("The local model server returned an invalid response.") from exc


def _chat(config: dict[str, Any], messages: list[dict[str, str]], max_tokens: int,
          *, structured: bool = False) -> str:
    if _select_backend(config) == "openai":
        return _call_openai(config, messages, max_tokens, structured=structured)
    return _call_ollama(config, messages, max_tokens, structured=structured)


def model_status(config: dict[str, Any]) -> dict[str, Any]:
    """Report the backend that would serve the next request, for /api/health."""
    backend = _select_backend(config)
    if backend == "openai":
        base, model = _openai_settings(config)
        resolved = resolve_openai_server(config)
        if resolved:
            base, models = resolved
            model = model or models[0]
        return {"available": resolved is not None, "backend": "openai",
                "label": "Local model", "model": model, "base_url": base}
    model = config.get("OLLAMA_MODEL", DEFAULT_MODEL)
    running = ollama_available(config)
    if running:
        return {"available": True, "backend": "ollama",
                "label": "Local model (llama.cpp)", "model": model}
    # Nothing is serving yet: report the managed preset the user picked, not an Ollama tag.
    preferred = "Qwen2.5 1.5B Instruct (not loaded)"
    return {"available": False, "backend": "ollama",
            "label": "Model not loaded", "model": preferred}


def _parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if not match:
            raise LLMError("The model did not return a valid structured summary.") from None
        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise LLMError("The model returned malformed JSON for the summary.") from exc
    if not isinstance(value, dict):
        raise LLMError("The model summary must be a JSON object.")
    return value


def generate_structured_summary(context: str, config: dict[str, Any]) -> dict[str, str]:
    system = (
        "You are a careful scientific-paper reading assistant. Use only the supplied excerpts. "
        "Never invent details. Cite evidence with the page markers already shown, such as [p. 4]. "
        "When a detail is absent, say 'Not clearly stated in the retrieved text.'"
    )
    user = f"""Create a concise, useful summary of this scientific paper from the evidence below.
Return ONLY a valid JSON object with these exact string keys:
"overall_summary", "objective", "methodology", "dataset", "key_findings", "limitations", "conclusion".
Keep each field to 2-4 sentences. Include inline page citations (for example [p. 2]) wherever evidence supports a claim. Do not cite pages that are not present in the excerpts.

EVIDENCE:
{context}
"""
    raw = _chat(
        config,
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=int(config.get("SUMMARY_MAX_TOKENS") or 900),
        structured=True,
    )
    parsed = _parse_json_object(raw)
    keys = (
        "overall_summary", "objective", "methodology", "dataset",
        "key_findings", "limitations", "conclusion",
    )
    normalized: dict[str, str] = {}
    for key in keys:
        value = parsed.get(key, "Not clearly stated in the retrieved text.")
        normalized[key] = str(value).strip() if value is not None else "Not clearly stated in the retrieved text."
    return normalized


DETAIL_STYLES: dict[str, tuple[str, int]] = {
    "brief": ("Answer in at most 3 sentences.", 300),
    "balanced": (
        "Answer in 2-4 short paragraphs (roughly 120-250 words). Use bullet points when you list "
        "several findings.",
        700,
    ),
    "detailed": (
        "Write a thorough answer of roughly 300-450 words in short paragraphs or bullet points. "
        "Cover the key evidence, numbers, definitions and any caveats mentioned in the passages.",
        1100,
    ),
}


def answer_detail(config: dict[str, Any], detail: str | None = None) -> str:
    choice = (detail or config.get("ANSWER_DETAIL") or "balanced")
    choice = str(choice).strip().lower()
    return choice if choice in DETAIL_STYLES else "balanced"


_NON_ENGLISH_WORDS = {
    # Spanish / Portuguese
    "qué", "que", "cuál", "cual", "cómo", "como", "por", "para", "objetivo", "método",
    "resultados", "qual", "são", "não", "uma", "los", "las", "del", "resumen",
    # French
    "quel", "quelle", "comment", "pourquoi", "objectif", "méthode", "résultats", "avec",
    # German
    "wie", "warum", "ziel", "methode", "ergebnisse", "welche", "ist", "und",
    # Italian
    "quale", "perché", "obiettivo", "metodo", "risultati",
}


def looks_non_english(text: str) -> bool:
    """True when the question is probably not English (other script or foreign words)."""
    letters = [char for char in text if char.isalpha()]
    if not letters:
        return False
    non_latin = sum(1 for char in letters if ord(char) > 0x024F)
    if non_latin / len(letters) > 0.15:
        return True
    words = re.findall(r"[^\W\d_]+", (text or "").lower())
    hits = sum(1 for word in words if word in _NON_ENGLISH_WORDS)
    return hits >= 2


def translate_query(question: str, config: dict[str, Any]) -> str | None:
    """Translate a question into English so retrieval can match an English paper."""
    try:
        answer = _chat(
            config,
            [
                {"role": "system",
                 "content": "You are a translator. Translate the user's question into plain English. "
                            "Output only the translation, no quotes, no explanation."},
                {"role": "user", "content": question},
            ],
            max_tokens=120,
        )
    except LLMError:
        return None
    cleaned = answer.strip().strip('"').strip()
    return cleaned or None


def generate_questions(context: str, config: dict[str, Any], count: int = 8,
                       style: str = "exam") -> str:
    """Turn retrieved passages into exam-style questions the paper can answer."""
    max_tokens = int(config.get("SUMMARY_MAX_TOKENS") or 900)
    system = (
        "You are an exam-setter reading a scientific paper. Write questions that the supplied "
        "passages can actually answer. Never invent facts. After every question add the page "
        "marker of the passage it comes from, for example [p. 12]. Cite pages only in that "
        "form; never copy the paper's own reference numbers such as [33.31]."
    )
    if style == "mcq":
        system = (
            "You are an exam-setter reading a scientific paper. Write multiple-choice questions "
            "that the supplied passages can answer. Never invent facts. Use the passage's own "
            "page marker in the answer key, for example [p. 12]."
        )
        user = f"""Write {count} multiple-choice questions from these paper passages.

Format exactly like this:
1. <question>
   A) <option>
   B) <option>
   C) <option>
   D) <option>
   Answer: <letter> — <one short sentence why> [p. N]

Rules: exactly four options per question, only one correct, no introductions, no closing summary.

Paper passages:
{context}"""
        return _chat(
            config,
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=max_tokens,
        )

    user = f"""Write {count} questions from these paper passages.

Format exactly like this:
1. <question> [p. N]
2. <question> [p. N]

Mix the difficulty: {count - 3} short-answer questions (definitions, formulas, values, methods) and 3 longer questions (compare, explain why, derive, limitations). Do not answer the questions. Do not add an introduction or a summary at the end.

Paper passages:
{context}"""
    return _chat(
        config,
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=max_tokens,
    )


def _parse_question_list(text: str, count: int) -> list[str]:
    """Pull a clean list of questions out of whatever the model wrote."""
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    candidates: list[str] = []
    match = re.search(r"\[[\s\S]*\]", cleaned)
    if match:
        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError:
            value = None
        if isinstance(value, list):
            candidates = [str(item) for item in value]
    if not candidates:
        for line in cleaned.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            line = re.sub(r"^\s*(?:[-*•]|\d{1,2}[.)])\s*", "", line)
            line = line.strip().strip('"').strip("'").strip()
            if line:
                candidates.append(line)
    questions: list[str] = []
    seen: set[str] = set()
    for raw in candidates:
        question = re.sub(r"\s+", " ", str(raw)).strip().strip('"').strip()
        question = re.sub(r"\s*\[(?:p\.?\s*)?\d+\s*\]$", "", question).strip()
        if not question.endswith("?"):
            question = question.rstrip(".") + "?"
        if len(question) < 12 or len(question) > 160:
            continue
        key = question.lower()
        if key in seen:
            continue
        seen.add(key)
        questions.append(question)
        if len(questions) >= count:
            break
    if not questions:
        raise LLMError("The model did not return usable questions.")
    return questions


def suggest_questions(context: str, config: dict[str, Any], count: int = 8) -> list[str]:
    """Ask the local model what a reader should ask about *this* paper."""
    system = (
        "You help a reader explore one specific scientific paper. Write questions that the "
        "supplied passages can actually answer. Each question must mention something concrete "
        "from the passages: a dataset, a metric, a model name, a method, a number or a result. "
        "Never write generic questions like 'What is the objective?'. "
        "No numbering, no answers, no page markers, no Markdown."
    )
    user = f"""Write exactly {count} short questions a reader might ask about this paper.
Return ONLY a JSON array of strings, for example:
["How does the model handle long documents?", "What accuracy does the method reach on SQuAD?"]

Paper passages:
{context}"""
    text = _chat(
        config,
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=int(config.get("SUGGESTION_MAX_TOKENS") or 420),
    )
    return _parse_question_list(text, count)


def answer_from_context(question: str, context: str, config: dict[str, Any],
                        detail: str | None = None) -> str:
    style = answer_detail(config, detail)
    instruction, default_tokens = DETAIL_STYLES[style]
    max_tokens = int(config.get("ANSWER_MAX_TOKENS") or default_tokens)
    system = (
        "You answer questions about scientific papers using only the provided retrieved passages. "
        "Do not use outside knowledge or make up claims. Cite supporting page markers like [p. 7] "
        "and never copy the paper's own reference numbers such as [33.31]. "
        "Write full sentences and explain the reasoning in the passages before concluding. "
        "Some passages are Markdown tables or equations; read them carefully and state the numbers they contain. "
        "Answer in the same language the question is written in; if the question is in Hindi, reply in Hindi, "
        "and keep page markers such as [p. 7] unchanged. "
        "If the passages do not answer the question, say that the paper excerpts do not provide enough evidence."
    )
    user = f"""Question: {question}

Retrieved paper passages:
{context}

{instruction} Cite each important claim with the page marker(s) from the passages. Do not invent page numbers."""
    return _chat(
        config,
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=max_tokens,
    )
