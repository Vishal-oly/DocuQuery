"""Paper-specific "Try asking" suggestions."""

from io import BytesIO
from pathlib import Path

from docuquery import create_app
from docuquery.rag import _fallback_questions

SAMPLE_PDF = Path(__file__).resolve().parents[1] / "examples" / "sample_scientific_article.pdf"


def make_client(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "LOCAL_DB_PATH": str(tmp_path / "demo.sqlite3"),
            "SECRET_KEY": "test",
            "OLLAMA_ENABLED": False,
        }
    )
    client = app.test_client()
    client.post(
        "/api/register",
        json={"name": "Suggest Tester", "email": "suggest@example.com", "password": "secret123"},
    )
    token = client.post(
        "/api/login", json={"email": "suggest@example.com", "password": "secret123"}
    ).get_json()["token"]
    return client, {"Authorization": f"Bearer {token}"}


def upload(client, headers):
    response = client.post(
        "/api/upload",
        data={"pdf": (BytesIO(SAMPLE_PDF.read_bytes()), "sample.pdf")},
        content_type="multipart/form-data",
        headers=headers,
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()["paper"]


def test_suggestions_are_paper_specific_and_get_consumed(tmp_path):
    client, headers = make_client(tmp_path)
    paper = upload(client, headers)

    payload = client.get(f"/api/papers/{paper['id']}/suggestions", headers=headers).get_json()
    questions = payload["questions"]
    assert questions, payload
    assert all(question.endswith("?") for question in questions)
    # Questions are seeded during the upload itself, so the chat card has them at once.
    assert payload["cached"] is True
    # No model in tests, so nothing better is coming: no need for the UI to poll.
    assert payload["ready"] is True

    # Second call is served from the stored list, not regenerated.
    again = client.get(f"/api/papers/{paper['id']}/suggestions", headers=headers).get_json()
    assert again["cached"] is True
    assert again["questions"] == questions

    asked = questions[0]
    answer = client.post(
        f"/api/papers/{paper['id']}/ask", json={"question": asked}, headers=headers
    )
    assert answer.status_code == 200, answer.get_json()

    after = client.get(f"/api/papers/{paper['id']}/suggestions", headers=headers).get_json()
    assert asked not in after["questions"]
    assert after["asked"] == 1
    assert len(after["questions"]) == len(questions) - 1


def test_suggestions_require_a_known_paper(tmp_path):
    client, headers = make_client(tmp_path)
    missing = client.get("/api/papers/not-a-paper/suggestions", headers=headers)
    assert missing.status_code == 404
    assert "not found" in missing.get_json()["error"].lower()


def test_fallback_questions_use_the_paper_content():
    chunks = [
        {
            "content": "We train BERT on the SQuAD dataset and reach 91.4% accuracy with attention pooling. " * 4,
            "page_number": 2,
            "section": "Results",
        },
        {
            "content": "The main limitation is the long training time of the transformer pipeline. " * 3,
            "page_number": 5,
            "section": "Limitations",
        },
    ]
    questions = _fallback_questions(chunks, {"title": "Page-Aware Retrieval for Scientific Papers"})
    assert questions
    assert len(questions) == len(set(questions))
    assert any("91.4" in q or "accuracy" in q.lower() for q in questions)
    assert any("Limitations" in q for q in questions)
    assert all(q.endswith("?") for q in questions)


def test_background_pass_upgrades_questions_when_a_model_answers(tmp_path, monkeypatch):
    """With a model running, the placeholder list is replaced without blocking the upload."""
    import threading as real_threading
    from types import SimpleNamespace

    from docuquery import rag, routes

    class ImmediateThread:
        def __init__(self, target=None, name=None, daemon=None):
            self._target = target

        def start(self):
            self._target()

    monkeypatch.setattr(
        routes,
        "threading",
        SimpleNamespace(Lock=real_threading.Lock, Thread=ImmediateThread),
    )
    monkeypatch.setattr(routes, "_model_reachable", lambda config: True)
    better = [
        "How does the page-aware retriever keep every citation on the right page?",
        "What accuracy does the demo study report for its retrieval step?",
    ]
    monkeypatch.setattr(rag, "model_questions", lambda *args, **kwargs: list(better))

    client, headers = make_client(tmp_path)
    paper = upload(client, headers)

    payload = client.get(f"/api/papers/{paper['id']}/suggestions", headers=headers).get_json()
    assert payload["questions"] == better
    assert payload["ready"] is True
