from docuquery import create_app


def make_test_app(tmp_path):
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-key",
            "GROQ_API_KEY": "",
            "SUPABASE_URL": "",
            "SUPABASE_SERVICE_ROLE_KEY": "",
            "LOCAL_DB_PATH": str(tmp_path / "auth.sqlite3"),
        }
    )


def test_register_validation_errors(tmp_path):
    client = make_test_app(tmp_path).test_client()
    bad = client.post(
        "/api/register",
        json={"name": "A", "email": "not-an-email", "password": "123"},
    )
    assert bad.status_code == 400
    message = bad.get_json()["error"].lower()
    assert "name" in message
    assert "email" in message
    assert "password" in message


def test_register_duplicate_email_conflict(tmp_path):
    client = make_test_app(tmp_path).test_client()
    first = client.post(
        "/api/register",
        json={"name": "Aditi", "email": "aditi@example.com", "password": "secret123"},
    )
    assert first.status_code == 201
    second = client.post(
        "/api/register",
        json={"name": "Aditi Two", "email": "aditi@example.com", "password": "secret123"},
    )
    assert second.status_code == 409
    assert "already exists" in second.get_json()["error"]


def test_login_wrong_password_then_success(tmp_path):
    client = make_test_app(tmp_path).test_client()
    client.post(
        "/api/register",
        json={"name": "Aditi", "email": "aditi@example.com", "password": "secret123"},
    )
    client.post("/api/logout")

    wrong = client.post(
        "/api/login", json={"email": "aditi@example.com", "password": "wrongpass"}
    )
    assert wrong.status_code == 401
    assert "Invalid email or password" in wrong.get_json()["error"]

    unknown = client.post(
        "/api/login", json={"email": "ghost@example.com", "password": "secret123"}
    )
    assert unknown.status_code == 401

    ok = client.post(
        "/api/login", json={"email": "aditi@example.com", "password": "secret123"}
    )
    assert ok.status_code == 200
    assert ok.get_json()["user"]["name"] == "Aditi"
    assert client.get("/api/me").status_code == 200


def test_logout_clears_session(tmp_path):
    client = make_test_app(tmp_path).test_client()
    client.post(
        "/api/register",
        json={"name": "Aditi", "email": "aditi@example.com", "password": "secret123"},
    )
    assert client.get("/api/me").status_code == 200
    assert client.post("/api/logout").status_code == 200
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/papers").status_code == 401
    assert client.get("/workspace").status_code == 302


def test_login_page_renders_both_modes(tmp_path):
    client = make_test_app(tmp_path).test_client()
    page = client.get("/login").get_data(as_text=True)
    assert "Login to DocuQuery" in page
    assert "Create account" in page
    assert "Forgot password" in page

    register_page = client.get("/login?mode=register").get_data(as_text=True)
    assert "Create account" in register_page
