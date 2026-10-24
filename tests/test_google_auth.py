from docuquery import create_app
from docuquery import routes as routes_module
from docuquery.google_auth import GoogleAuthError


def make_test_app(tmp_path, google_client_id="test-client-id.apps.googleusercontent.com"):
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-key",
            "GROQ_API_KEY": "",
            "SUPABASE_URL": "",
            "SUPABASE_SERVICE_ROLE_KEY": "",
            "GOOGLE_CLIENT_ID": google_client_id,
            "LOCAL_DB_PATH": str(tmp_path / "google.sqlite3"),
        }
    )


def patch_verify(monkeypatch, claims=None, error=None):
    def fake_verify(token, client_id, timeout=5.0):
        if error:
            raise GoogleAuthError(error)
        return claims or {}

    monkeypatch.setattr(routes_module, "verify_google_credential", fake_verify)


def test_google_login_not_configured(tmp_path):
    app = make_test_app(tmp_path, google_client_id="")
    client = app.test_client()
    response = client.post("/api/auth/google", json={"credential": "whatever"})
    assert response.status_code == 400
    assert "not configured" in response.get_json()["error"]


def test_google_login_creates_account_and_signs_in(tmp_path, monkeypatch):
    app = make_test_app(tmp_path)
    client = app.test_client()
    patch_verify(
        monkeypatch,
        claims={
            "email": "aditi@gmail.com",
            "name": "Aditi Sharma",
            "email_verified": "true",
        },
    )
    response = client.post("/api/auth/google", json={"credential": "fake-id-token"})
    assert response.status_code == 200, response.get_json()
    payload = response.get_json()
    assert payload["user"]["email"] == "aditi@gmail.com"
    assert payload["user"]["name"] == "Aditi Sharma"
    assert "password_hash" not in payload["user"]
    assert payload["token"]

    # Signed in right away.
    assert client.get("/api/me").get_json()["user"]["email"] == "aditi@gmail.com"

    # Second Google sign-in joins the SAME account (no duplicate user).
    again = client.post("/api/auth/google", json={"credential": "fake-id-token"})
    assert again.status_code == 200
    assert again.get_json()["user"]["id"] == payload["user"]["id"]


def test_google_login_joins_existing_email_account(tmp_path, monkeypatch):
    app = make_test_app(tmp_path)
    client = app.test_client()
    # Existing email/password account.
    registered = client.post(
        "/api/register",
        json={"name": "Aditi", "email": "aditi@gmail.com", "password": "secret123"},
    )
    user_id = registered.get_json()["user"]["id"]
    client.post("/api/logout")

    patch_verify(
        monkeypatch,
        claims={"email": "aditi@gmail.com", "name": "Aditi G", "email_verified": "true"},
    )
    response = client.post("/api/auth/google", json={"credential": "tok"})
    assert response.status_code == 200
    assert response.get_json()["user"]["id"] == user_id


def test_google_login_rejects_bad_claims(tmp_path, monkeypatch):
    app = make_test_app(tmp_path)
    client = app.test_client()

    patch_verify(monkeypatch, error="Could not verify the Google credential: boom")
    bad = client.post("/api/auth/google", json={"credential": "bad"})
    assert bad.status_code == 400

    # email_verified=false is rejected inside verify_google_credential; emulate via error path.
    patch_verify(monkeypatch, error="Google account email is not verified.")
    unverified = client.post("/api/auth/google", json={"credential": "bad"})
    assert unverified.status_code == 400
    assert "verified" in unverified.get_json()["error"]

    empty = client.post("/api/auth/google", json={})
    assert empty.status_code in (400, 503)


def test_google_button_visible_when_configured(tmp_path, monkeypatch):
    app = make_test_app(tmp_path)
    client = app.test_client()
    patch_verify(monkeypatch, claims={"email": "a@b.com", "name": "A", "email_verified": "true"})
    page = client.get("/login").get_data(as_text=True)
    # The Google widget container + GIS script are present (Google renders the button itself).
    assert "g_id_signin" in page
    assert "accounts.google.com/gsi/client" in page
    assert "onGoogleCredential" in page


def test_google_button_hidden_when_not_configured(tmp_path):
    app = make_test_app(tmp_path, google_client_id="")
    client = app.test_client()
    page = client.get("/login").get_data(as_text=True)
    assert "accounts.google.com/gsi/client" not in page
    assert "GOOGLE_CLIENT_ID" in page  # hint shown instead
