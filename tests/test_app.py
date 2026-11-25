from io import BytesIO
from pathlib import Path

from docuquery import create_app


SAMPLE_PDF = Path(__file__).resolve().parents[1] / "examples" / "sample_scientific_article.pdf"


def make_test_app(tmp_path):
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-key",
            "OLLAMA_ENABLED": False,
            "LOCAL_DB_PATH": str(tmp_path / "papers.sqlite3"),
        }
    )


def register_and_login(client, name="Reader", email="reader@example.com", password="secret123"):
    response = client.post(
        "/api/register",
        json={"name": name, "email": email, "password": password},
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()["user"]


def test_landing_health_and_auth_guards(tmp_path):
    client = make_test_app(tmp_path).test_client()

    home = client.get("/")
    assert home.status_code == 200
    page = home.get_data(as_text=True)
    assert "DocuQuery" in page
    assert "Login" in page
    assert "Register" in page

    protected = client.get("/workspace")
    assert protected.status_code == 302
    assert "/login" in protected.headers["Location"]

    assert client.get("/api/papers").status_code == 401
    assert client.get("/api/me").status_code == 401
    assert client.post("/api/upload", data={}, content_type="multipart/form-data").status_code == 401

    health = client.get("/api/health").get_json()
    assert health["database"] == "local SQLite demo"
    assert health["llm_available"] is False
    assert health["llm_backend"] in {"ollama", "openai"}


def test_workspace_login_flow_and_empty_library(tmp_path):
    app = make_test_app(tmp_path)
    client = app.test_client()
    user = register_and_login(client, name="Aditi", email="aditi@example.com")
    assert user["name"] == "Aditi"
    assert "password_hash" not in user

    workspace = client.get("/workspace")
    assert workspace.status_code == 200
    page = workspace.get_data(as_text=True)
    assert "DocuQuery" in page
    for section in ("Workspace", "Upload PDF", "Research Brief", "Evidence Trail", "Ask This Paper", "Paper Library"):
        assert section in page
    assert "Aditi" in page
    assert client.get("/api/papers").get_json()["papers"] == []
    assert client.get("/api/me").get_json()["user"]["email"] == "aditi@example.com"


def test_upload_rejects_missing_and_non_pdf_files(tmp_path):
    client = make_test_app(tmp_path).test_client()
    register_and_login(client)

    missing = client.post("/api/upload", data={}, content_type="multipart/form-data")
    assert missing.status_code == 400
    assert "Choose a PDF" in missing.get_json()["error"]

    invalid = client.post(
        "/api/upload",
        data={"pdf": (BytesIO(b"not a PDF document"), "paper.txt")},
        content_type="multipart/form-data",
    )
    assert invalid.status_code == 400
    assert "Only PDF" in invalid.get_json()["error"]


def test_upload_chat_and_account_scoping(tmp_path):
    app = make_test_app(tmp_path)
    client = app.test_client()
    register_and_login(client, name="Asha", email="asha@example.com")

    response = client.post(
        "/api/upload",
        data={"pdf": (BytesIO(SAMPLE_PDF.read_bytes()), "sample_scientific_article.pdf")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 201, response.get_json()
    payload = response.get_json()
    paper = payload["paper"]
    assert paper["title"].startswith("Demo Study")
    assert paper["page_count"] == 1
    assert "session_id" not in paper
    assert payload["chunk_count"] > 0
    assert payload["summary"]["mode"] == "extractive preview"
    assert payload["summary"]["sources"]

    answer = client.post(
        f"/api/papers/{paper['id']}/ask",
        json={"question": "What limitations does this example mention?"},
    )
    assert answer.status_code == 200
    assert answer.get_json()["sources"]

    # A different account cannot see this paper.
    other_browser = app.test_client()
    register_and_login(other_browser, name="Ravi", email="ravi@example.com")
    assert other_browser.get("/api/papers").get_json()["papers"] == []
    assert other_browser.get(f"/api/papers/{paper['id']}").status_code == 404
    assert other_browser.delete(f"/api/papers/{paper['id']}").status_code == 404

    # The same account keeps its papers across browser sessions.
    client.post("/api/logout")
    relogin = app.test_client()
    signed_in = relogin.post(
        "/api/login", json={"email": "asha@example.com", "password": "secret123"}
    )
    assert signed_in.status_code == 200
    papers = relogin.get("/api/papers").get_json()["papers"]
    assert len(papers) == 1

    removed = relogin.delete(f"/api/papers/{paper['id']}")
    assert removed.status_code == 200
    assert relogin.get("/api/papers").get_json()["papers"] == []


def test_landing_serves_bootstrap_locally(tmp_path):
    client = make_test_app(tmp_path).test_client()
    assert '/static/vendor/bootstrap.min.css' in client.get('/').get_data(as_text=True)
    assert client.get('/static/vendor/bootstrap.min.css').status_code == 200


def test_model_picker_lists_and_saves_choice(tmp_path, monkeypatch):
    monkeypatch.setenv("MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.setenv("MODEL_SELECTION_FILE", str(tmp_path / "models" / "selected.json"))
    client = make_test_app(tmp_path).test_client()

    assert client.get("/api/models").status_code == 401
    register_and_login(client, name="Model Fan", email="models@example.com")

    payload = client.get("/api/models").get_json()
    assert payload["recommended"] in {"small", "default", "large"}
    assert {option["id"] for option in payload["options"]} >= {"preset:small", "preset:default"}
    assert payload["current"]["available"] is False

    selected = client.post("/api/models/select", json={"id": "preset:small"})
    assert selected.status_code == 200
    assert selected.get_json()["selected_id"] == "preset:small"
    assert client.get("/api/models").get_json()["selected_id"] == "preset:small"

    assert client.post("/api/models/select", json={"id": "preset:huge"}).status_code == 400


def test_health_reports_optional_features(tmp_path):
    client = make_test_app(tmp_path).test_client()
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert "ocr_available" in payload
    assert "tables_available" in payload
    assert payload["llm_label"] in {"Local model (llama.cpp)", "Model not loaded", "Local model"}


def test_download_routes_are_wired(tmp_path, monkeypatch):
    from docuquery import model_registry

    client = make_test_app(tmp_path).test_client()
    register_and_login(client, email="downloader@example.com")
    login = client.post("/api/login", json={"email": "downloader@example.com", "password": "secret123"})
    headers = {"Authorization": f"Bearer {login.get_json()['token']}"}

    status = client.get("/api/models/download", headers=headers)
    assert status.status_code == 200
    assert status.get_json()["state"] in {"idle", "downloading", "done", "error"}

    started = {"called": False}

    def fake_start(preset):
        started["called"] = preset
        return {"state": "downloading", "id": preset}

    monkeypatch.setattr(model_registry, "start_download", fake_start)
    response = client.post("/api/models/download", json={"id": "preset:small"}, headers=headers)
    assert response.status_code == 202
    assert started["called"] == "small"
