
from docuquery import llm, rag


class FakeEmbedder:
    def embed(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]


class FakeRepo:
    def __init__(self, chunks):
        self.chunks = chunks

    def search_chunks(self, session_id, paper_id, vector, limit=4):
        return self.chunks[:limit]


PAPER = {"id": "p1", "filename": "paper.pdf"}


def test_answer_length_setting_controls_prompt_and_tokens(monkeypatch):
    seen = {}

    def fake_chat(config, messages, max_tokens, structured=False):
        seen["prompt"] = messages[-1]["content"]
        seen["max_tokens"] = max_tokens
        return "answer"

    monkeypatch.setattr(llm, "_chat", fake_chat)

    llm.answer_from_context("What is accuracy?", "Text [p. 1]", {}, detail="detailed")
    assert seen["max_tokens"] == 1100
    assert "300-450 words" in seen["prompt"]

    llm.answer_from_context("What is accuracy?", "Text [p. 1]", {}, detail="brief")
    assert seen["max_tokens"] == 300

    llm.answer_from_context("Q", "Text", {"ANSWER_MAX_TOKENS": 250}, detail="brief")
    assert seen["max_tokens"] == 250

    assert llm.answer_detail({}, "verbose") == "balanced"
    assert llm.answer_detail({"ANSWER_DETAIL": "detailed"}, None) == "detailed"


def test_answer_question_passes_detail_to_model(monkeypatch):
    captured = {}

    def fake_answer(question, context, config, detail=None):
        captured["detail"] = detail
        return "Generated answer [p. 2]."

    monkeypatch.setattr(rag, "answer_from_context", fake_answer)
    chunks = [{"content": "Some evidence text about accuracy.", "page_number": 2}]

    result = rag.answer_question(FakeRepo(chunks), FakeEmbedder(), {"RAG_TOP_K": 2},
                                 "session", PAPER, "How accurate is it?", "detailed")

    assert result["answer"] == "Generated answer [p. 2]."
    assert result["mode"] == "Local model RAG"
    assert captured["detail"] == "detailed"


def test_answer_question_defaults_to_config_style(monkeypatch):
    captured = {}

    def fake_answer(question, context, config, detail=None):
        captured["detail"] = detail
        return "ok"

    monkeypatch.setattr(rag, "answer_from_context", fake_answer)
    chunks = [{"content": "Evidence text.", "page_number": 1}]
    rag.answer_question(FakeRepo(chunks), FakeEmbedder(), {}, "s", PAPER, "q?")
    assert captured["detail"] is None
