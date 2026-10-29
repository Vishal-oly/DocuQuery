from io import BytesIO
from pathlib import Path

from docuquery import create_app


SAMPLE_PDF = Path(__file__).resolve().parents[1] / "examples" / "sample_scientific_article.pdf"


def make_test_app(tmp_path):
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-key",
            "GROQ_API_KEY": "",
            "SUPABASE_URL": "",
            "SUPABASE_SERVICE_ROLE_KEY": "",
            "LOCAL_DB_PATH": str(tmp_path / "features.sqlite3"),
        }
    )


def signed_in_client(tmp_path):
    app = make_test_app(tmp_path)
    client = app.test_client()
    client.post(
        "/api/register",
        json={"name": "Aditi", "email": "aditi@example.com", "password": "secret123"},
    )
    return app, client


def upload_sample(client):
    response = client.post(
        "/api/upload",
        data={"pdf": (BytesIO(SAMPLE_PDF.read_bytes()), "sample_scientific_article.pdf")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()


def test_pages_render_when_signed_in(tmp_path):
    _app, client = signed_in_client(tmp_path)
    for path, marker in (
        ("/summaries", "Research briefs"),
        ("/profile", "Uploaded files"),
    ):
        page = client.get(path)
        assert page.status_code == 200, path
        assert marker.lower() in page.get_data(as_text=True).lower()


def test_forgot_and_reset_password_flow(tmp_path):
    app, client = signed_in_client(tmp_path)
    client.post("/api/logout")

    page = client.get("/forgot")
    assert page.status_code == 200
    assert "Forgot your password" in page.get_data(as_text=True)

    forgot = client.post("/api/forgot", json={"email": "aditi@example.com"})
    assert forgot.status_code == 200
    token = forgot.get_json()["reset_token"]
    assert token and len(token) == 6

    # Unknown emails do not reveal existence.
    ghost = client.post("/api/forgot", json={"email": "ghost@example.com"})
    assert ghost.status_code == 200
    assert "reset_token" not in ghost.get_json()

    weak = client.post("/api/reset", json={"token": token, "new_password": "123"})
    assert weak.status_code == 400

    reset = client.post("/api/reset", json={"token": token, "new_password": "newpass123"})
    assert reset.status_code == 200

    old_login = client.post(
        "/api/login", json={"email": "aditi@example.com", "password": "secret123"}
    )
    assert old_login.status_code == 401
    new_login = client.post(
        "/api/login", json={"email": "aditi@example.com", "password": "newpass123"}
    )
    assert new_login.status_code == 200

    # The code is single-use.
    again = client.post("/api/reset", json={"token": token, "new_password": "other123"})
    assert again.status_code == 400


def test_upload_stores_file_and_summary_download(tmp_path):
    _app, client = signed_in_client(tmp_path)
    payload = upload_sample(client)
    paper = payload["paper"]
    assert paper["has_file"] is True
    assert paper["file_size"] > 0

    # View document returns the stored PDF.
    document = client.get(f"/api/papers/{paper['id']}/file")
    assert document.status_code == 200
    assert document.headers["Content-Type"] == "application/pdf"
    assert document.data.startswith(b"%PDF-")

    # Summary downloads in three formats.
    md = client.get(f"/api/papers/{paper['id']}/download?format=md")
    assert md.status_code == 200
    assert "Research brief" in md.get_data(as_text=True)
    assert "attachment" in md.headers["Content-Disposition"]

    txt = client.get(f"/api/papers/{paper['id']}/download?format=txt")
    assert txt.status_code == 200
    assert "##" not in txt.get_data(as_text=True)

    json_dl = client.get(f"/api/papers/{paper['id']}/download?format=json")
    assert json_dl.status_code == 200
    assert json_dl.get_json()["paper"]["id"] == paper["id"]

    bad = client.get(f"/api/papers/{paper['id']}/download?format=docx")
    assert bad.status_code == 400

    # Regenerate the brief.
    regen = client.post(f"/api/papers/{paper['id']}/summarize")
    assert regen.status_code == 200
    assert regen.get_json()["summary"]["mode"] == "extractive preview"

    # Delete removes the paper and its stored file.
    assert client.delete(f"/api/papers/{paper['id']}").status_code == 200
    assert client.get(f"/api/papers/{paper['id']}/file").status_code == 404


def test_profile_update_name_and_password(tmp_path):
    _app, client = signed_in_client(tmp_path)

    bad_name = client.patch("/api/me", json={"name": "A"})
    assert bad_name.status_code == 400

    renamed = client.patch("/api/me", json={"name": "Aditi Sharma"})
    assert renamed.status_code == 200
    assert renamed.get_json()["user"]["name"] == "Aditi Sharma"
    assert client.get("/api/me").get_json()["user"]["name"] == "Aditi Sharma"

    wrong = client.post(
        "/api/me/password",
        json={"current_password": "wrongpass", "new_password": "newpass123"},
    )
    assert wrong.status_code == 401

    weak = client.post(
        "/api/me/password",
        json={"current_password": "secret123", "new_password": "123"},
    )
    assert weak.status_code == 400

    ok = client.post(
        "/api/me/password",
        json={"current_password": "secret123", "new_password": "newpass123"},
    )
    assert ok.status_code == 200

    client.post("/api/logout")
    login = client.post(
        "/api/login", json={"email": "aditi@example.com", "password": "newpass123"}
    )
    assert login.status_code == 200


def test_other_account_cannot_access_files(tmp_path):
    app, client = signed_in_client(tmp_path)
    payload = upload_sample(client)
    paper_id = payload["paper"]["id"]

    other = app.test_client()
    other.post(
        "/api/register",
        json={"name": "Ravi", "email": "ravi@example.com", "password": "secret123"},
    )
    assert other.get(f"/api/papers/{paper_id}/file").status_code == 404
    assert other.get(f"/api/papers/{paper_id}/download?format=md").status_code == 404
    assert other.post(f"/api/papers/{paper_id}/summarize").status_code == 404


def test_groq_errors_are_classified_for_users():
    """Users must see WHY Groq failed (key missing, rate limit, offline)."""
    from docuquery.llm import LLMError, _call_groq

    # No key -> tells the user to configure .env
    try:
        _call_groq("", "m", [{"role": "user", "content": "hi"}])
    except LLMError as exc:
        assert "GROQ_API_KEY" in str(exc) and "not configured" in str(exc)
    else:
        raise AssertionError("expected LLMError")

    # Network failure -> internet hint (simulate via unreachable host)
    import groq as groq_module

    class FakeGroq:
        def __init__(self, api_key):
            raise ConnectionError("Failed to establish a new connection: [Errno -3] name resolution")

    original = groq_module.Groq
    groq_module.Groq = FakeGroq
    try:
        _call_groq("gsk_fake", "m", [{"role": "user", "content": "hi"}])
    except LLMError as exc:
        assert "internet" in str(exc).lower()
    else:
        raise AssertionError("expected LLMError")
    finally:
        groq_module.Groq = original
