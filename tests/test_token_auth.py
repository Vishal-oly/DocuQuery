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
            "LOCAL_DB_PATH": str(tmp_path / "token.sqlite3"),
        }
    )


def test_token_auth_works_without_cookies(tmp_path):
    """Auth tokens must work where cookies are blocked (sandboxed iframe previews)."""
    app = make_test_app(tmp_path)

    # Register with one client to obtain a token.
    client = app.test_client()
    registered = client.post(
        "/api/register",
        json={"name": "Aditi", "email": "aditi@example.com", "password": "secret123"},
    )
    assert registered.status_code == 201
    token = registered.get_json()["token"]
    assert token

    # A cookie-less client authenticated only by the Authorization header.
    cookie_less = app.test_client()
    assert cookie_less.get("/api/papers").status_code == 401
    papers = cookie_less.get("/api/papers", headers={"Authorization": f"Bearer {token}"})
    assert papers.status_code == 200
    assert papers.get_json()["papers"] == []

    upload = cookie_less.post(
        "/api/upload",
        data={"pdf": (BytesIO(SAMPLE_PDF.read_bytes()), "sample_scientific_article.pdf")},
        content_type="multipart/form-data",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert upload.status_code == 201, upload.get_json()

    # Page routes accept ?token= so full-page navigations work without cookies.
    page = cookie_less.get(f"/workspace?token={token}")
    assert page.status_code == 200
    assert "DocuQuery" in page.get_data(as_text=True)

    page = cookie_less.get(f"/summaries?token={token}")
    assert page.status_code == 200

    page = cookie_less.get(f"/profile?token={token}")
    assert page.status_code == 200

    # File downloads accept ?token= too (plain link navigations can't send headers).
    paper_id = upload.get_json()["paper"]["id"]
    document = cookie_less.get(f"/api/papers/{paper_id}/file?token={token}")
    assert document.status_code == 200
    assert document.data.startswith(b"%PDF-")

    # Query-param auth works as well as the header.
    via_query = cookie_less.get(f"/api/papers?token={token}")
    assert via_query.status_code == 200

    # Invalid tokens are rejected (fresh client so earlier cookie upgrades don't apply).
    fresh = app.test_client()
    bad = fresh.get("/api/papers", headers={"Authorization": "Bearer not-a-real-token"})
    assert bad.status_code == 401
    assert fresh.get("/workspace?token=not-a-real-token").status_code == 302


def test_login_returns_token_and_scope_matches_account(tmp_path):
    app = make_test_app(tmp_path)
    client = app.test_client()
    client.post(
        "/api/register",
        json={"name": "Asha", "email": "asha@example.com", "password": "secret123"},
    )
    upload = client.post(
        "/api/upload",
        data={"pdf": (BytesIO(SAMPLE_PDF.read_bytes()), "sample_scientific_article.pdf")},
        content_type="multipart/form-data",
    )
    paper_id = upload.get_json()["paper"]["id"]

    logged_out = client.post("/api/logout")
    assert logged_out.status_code == 200

    login = client.post(
        "/api/login", json={"email": "asha@example.com", "password": "secret123"}
    )
    assert login.status_code == 200
    token = login.get_json()["token"]
    assert token

    # The same account reached via token sees the same papers.
    cookie_less = app.test_client()
    papers = cookie_less.get("/api/papers", headers={"Authorization": f"Bearer {token}"})
    assert papers.status_code == 200
    assert [p["id"] for p in papers.get_json()["papers"]] == [paper_id]
