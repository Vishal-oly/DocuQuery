import io
from pathlib import Path

from docuquery import create_app

SAMPLE_PDF = Path(__file__).resolve().parents[1] / "examples" / "sample_scientific_article.pdf"


def _app(tmp_path):
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-key",
            "GROQ_API_KEY": "",
            "SUPABASE_URL": "",
            "SUPABASE_SERVICE_ROLE_KEY": "",
            "LOCAL_DB_PATH": str(tmp_path / "clear.sqlite3"),
        }
    )


def _register_and_login(client):
    response = client.post(
        "/api/register",
        json={"name": "Aditi", "email": "aditi@example.com", "password": "secret123"},
    )
    return response.get_json()["token"]


def _upload_dummy_pdf(client, token, name="paper.pdf"):
    return client.post(
        f"/api/upload?token={token}",
        data={"pdf": (io.BytesIO(SAMPLE_PDF.read_bytes()), name)},
        content_type="multipart/form-data",
    )


def test_clear_history_requires_login(tmp_path):
    app = _app(tmp_path)
    client = app.test_client()
    response = client.post("/api/me/clear-history")
    assert response.status_code == 401


def test_clear_history_removes_all_papers(tmp_path):
    app = _app(tmp_path)
    client = app.test_client()
    token = _register_and_login(client)

    for i in range(3):
        response = _upload_dummy_pdf(client, token, f"paper-{i}.pdf")
        assert response.status_code in (200, 201), response.get_json()

    assert len(client.get(f"/api/papers?token={token}").get_json()["papers"]) == 3

    response = client.post(f"/api/me/clear-history?token={token}")
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["deleted"] == 3

    assert client.get(f"/api/papers?token={token}").get_json()["papers"] == []

    # Idempotent: a second clear deletes nothing and still succeeds.
    again = client.post(f"/api/me/clear-history?token={token}")
    assert again.status_code == 200
    assert again.get_json()["deleted"] == 0


def test_clear_history_only_touches_own_papers(tmp_path):
    app = _app(tmp_path)
    client = app.test_client()
    token_a = _register_and_login(client)
    _upload_dummy_pdf(client, token_a, "a.pdf")

    client.post("/api/logout")
    client.post(
        "/api/register",
        json={"name": "Ravi", "email": "ravi@example.com", "password": "secret123"},
    )
    token_b = client.post(
        "/api/login", json={"email": "ravi@example.com", "password": "secret123"}
    ).get_json()["token"]
    _upload_dummy_pdf(client, token_b, "b.pdf")
    _upload_dummy_pdf(client, token_b, "b2.pdf")

    response = client.post(f"/api/me/clear-history?token={token_b}")
    assert response.get_json()["deleted"] == 2

    # Ravi is empty, Aditi still has her paper.
    assert client.get(f"/api/papers?token={token_b}").get_json()["papers"] == []
    assert len(client.get(f"/api/papers?token={token_a}").get_json()["papers"]) == 1
