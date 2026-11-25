from docuquery import rag


def test_sanitize_drops_reference_numbers_but_keeps_pages():
    raw = "The objective is scattering [33.31], [28.6] and phase shifts [p. 173]."
    assert rag.sanitize_answer(raw) == "The objective is scattering, and phase shifts [p. 173]."


def test_sanitize_collapses_duplicate_page_refs_and_spaces():
    assert rag.sanitize_answer("A [p. 4] [p. 4] B") == "A [p. 4] B"
    assert rag.sanitize_answer("value  ,  next") == "value, next"


def test_question_intent_detection():
    assert rag.wants_questions("give some questions from this pdf")
    assert rag.wants_questions("Generate 10 MCQ questions")
    assert rag.wants_questions("can you list exam questions?")
    assert not rag.wants_questions("What is the main objective of this paper?")
    assert not rag.wants_questions("What methods were used?")


def test_broad_question_detection():
    assert rag.is_broad_question("main objective")
    assert rag.is_broad_question("what is this paper about?")
    assert rag.is_broad_question("summarise the paper")
    assert not rag.is_broad_question("what accuracy did they report on page 4?")


class FakeRepository:
    def __init__(self, chunks):
        self._chunks = chunks

    def list_chunks(self, session_id, paper_id):
        return self._chunks

    def search_chunks(self, session_id, paper_id, vector, limit=4):
        return [dict(chunk, similarity=0.5) for chunk in self._chunks[:limit]]


def _chunks(count=20):
    return [
        {"id": f"c{index}", "page_number": index + 1, "section": "Body",
         "content": ("Passage number %d about quantum scattering, phase shifts and the time "
                    "evolution of wavefunctions in one dimension." % index),
         "kind": "text"}
        for index in range(count)
    ]


def test_intro_chunks_use_first_pages_and_abstract():
    repository = FakeRepository(_chunks())
    intro = rag._intro_chunks(repository, "s", "p")
    assert intro and all(int(chunk["page_number"]) <= 2 for chunk in intro)


def test_spread_chunks_covers_the_whole_paper():
    repository = FakeRepository(_chunks(40))
    spread = rag._spread_chunks(repository, "s", "p", limit=8)
    pages = [int(chunk["page_number"]) for chunk in spread]
    assert len(pages) == 8
    assert pages[0] == 1 and pages[-1] >= 32


def test_answer_question_uses_question_generator(monkeypatch):
    calls = {}

    def fake_questions(context, config, count=8, style="exam"):
        calls["count"] = count
        calls["style"] = style
        return "1. What is the scattering phase shift? [p. 3]"

    monkeypatch.setattr(rag, "generate_questions", fake_questions)
    monkeypatch.setattr(rag, "answer_from_context", lambda *a, **k: "should not be used")
    repository = FakeRepository(_chunks(12))
    result = rag.answer_question(
        repository, _FakeEmbedder(), {}, "s",
        {"id": "p", "filename": "paper.pdf"}, "give me some questions from this pdf",
    )
    assert calls["count"] == 8
    assert calls["style"] == "exam"
    assert result["mode"] == "Generated questions"
    assert "[p. 3]" in result["answer"]


def test_mcq_intent_uses_quiz_style(monkeypatch):
    calls = {}

    def fake_questions(context, config, count=5, style="exam"):
        calls.update(count=count, style=style)
        return "1. Question?\n   A) one\n   B) two\n   C) three\n   D) four\n   Answer: B — reason [p. 2]"

    monkeypatch.setattr(rag, "generate_questions", fake_questions)
    result = rag.answer_question(
        FakeRepository(_chunks(10)), _FakeEmbedder(), {}, "s",
        {"id": "p", "filename": "paper.pdf"},
        "Give me 5 multiple choice questions with four options each",
    )
    assert calls == {"count": 5, "style": "mcq"}
    assert result["mode"] == "Generated MCQ quiz"


def test_mcq_detection():
    assert rag.wants_mcq("give me mcqs from this paper")
    assert rag.wants_mcq("multiple-choice questions please")
    assert not rag.wants_mcq("give me exam questions")


def test_answer_question_adds_intro_chunks_for_broad_questions(monkeypatch):
    captured = {}

    def fake_answer(question, context, config, detail=None):
        captured["context"] = context
        return "Objective is ... [p. 1]"

    monkeypatch.setattr(rag, "answer_from_context", fake_answer)
    repository = FakeRepository(_chunks(12))
    rag.answer_question(
        repository, _FakeEmbedder(), {}, "s",
        {"id": "p", "filename": "paper.pdf"}, "main objective",
    )
    assert "Passage number 0" in captured["context"]


class _FakeEmbedder:
    def embed(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]


def test_fallback_answer_is_clean_and_actionable():
    from docuquery.llm import LLMError

    text = rag._fallback_answer(
        LLMError("The local model is not running."),
        [
            {"page_number": 2, "content": "2\nOpening remarks  These lecture notes are based on 3 courses in quantum mechanics."},
            {"page_number": 182, "content": "complete Bloch oscillations with frequency omega and the double well system."},
        ],
    )
    assert "OLLAMA" not in text
    assert "• p. 2 — “Opening remarks" in text
    assert "start.bat" in text


def test_excerpt_trims_at_sentence_boundary_and_drops_stray_page_number():
    long_text = "9 " + ("Alpha beta gamma. " * 40)
    excerpt = rag._excerpt({"content": long_text}, limit=120)
    assert not excerpt.startswith("9 ")
    assert excerpt.endswith(".")
    assert len(excerpt) <= 130


def test_looks_non_english_detects_scripts_and_foreign_words():
    from docuquery.llm import looks_non_english

    assert looks_non_english("मुख्य उद्देश्य क्या है?")
    assert looks_non_english("¿cuál es el objetivo principal?")
    assert not looks_non_english("What is the main objective of this paper?")
    assert not looks_non_english("How do the methods compare with the baselines?")


def test_non_english_question_is_translated_for_retrieval(monkeypatch):
    embedded = {}

    class RecordingEmbedder:
        def embed(self, texts):
            embedded["text"] = texts[0]
            return [[0.1, 0.2, 0.3] for _ in texts]

    monkeypatch.setattr(rag, "translate_query", lambda question, config: "what is the main objective")
    monkeypatch.setattr(rag, "answer_from_context", lambda *a, **k: "मुख्य उद्देश्य है ... [p. 1]")

    result = rag.answer_question(
        FakeRepository(_chunks(6)), RecordingEmbedder(), {}, "s",
        {"id": "p", "filename": "paper.pdf"}, "मुख्य उद्देश्य क्या है?",
    )
    assert embedded["text"] == "what is the main objective"
    assert "another language" in result["mode"]
    assert "मुख्य उद्देश्य" in result["answer"]


def test_english_question_is_not_translated(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("translate_query should not run for English questions")

    monkeypatch.setattr(rag, "translate_query", boom)
    monkeypatch.setattr(rag, "answer_from_context", lambda *a, **k: "answer [p. 2]")
    result = rag.answer_question(
        FakeRepository(_chunks(6)), _FakeEmbedder(), {}, "s",
        {"id": "p", "filename": "paper.pdf"}, "what methods were used?",
    )
    assert "another language" not in result["mode"]


def test_sanitize_keeps_figure_and_table_labels():
    cleaned = rag.sanitize_answer("See [Figure 3] and [Table 2] plus [33.31] at [p. 12].")
    assert "[Figure 3]" in cleaned
    assert "[Table 2]" in cleaned
    assert "[33.31]" not in cleaned
    assert "[p. 12]" in cleaned


def test_sanitize_strips_markdown_for_the_plain_text_bubble():
    cleaned = rag.sanitize_answer(
        "## Findings\n**Main idea:** uses **attention** [p. 3].\n- First point [p. 4]\n| --- | --- |\nUse `softmax`."
    )
    assert "**" not in cleaned and "`" not in cleaned and "##" not in cleaned
    assert "Main idea:" in cleaned
    assert "• First point [p. 4]" in cleaned
    assert "---" not in cleaned
