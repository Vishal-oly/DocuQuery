"""Google Sign-In verification for ID tokens from Google Identity Services."""

import json
import urllib.parse
import urllib.request


GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo?id_token={token}"
VALID_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


class GoogleAuthError(RuntimeError):
    """Raised when a Google credential cannot be accepted."""


def verify_google_credential(token: str, client_id: str, timeout: float = 5.0) -> dict:
    """Verify a Google ID token and return its claims.

    The token is checked against Google's tokeninfo endpoint (signature, expiry,
    audience and issuer are validated server-side by Google).
    """
    if not client_id:
        raise GoogleAuthError(
            "Google sign-in is not configured. Set GOOGLE_CLIENT_ID in .env (see README)."
        )
    if not token:
        raise GoogleAuthError("Missing Google credential.")
    try:
        url = GOOGLE_TOKENINFO_URL.format(token=urllib.parse.quote(token, safe=""))
        with urllib.request.urlopen(url, timeout=timeout) as response:
            claims = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise GoogleAuthError(f"Could not verify the Google credential: {exc}") from exc

    if claims.get("iss") not in VALID_ISSUERS:
        raise GoogleAuthError("Invalid Google credential issuer.")
    if str(claims.get("aud") or "") != str(client_id):
        raise GoogleAuthError("Google credential was issued for a different application.")
    if str(claims.get("email_verified", "")).lower() not in ("true", "1"):
        raise GoogleAuthError("Google account email is not verified.")
    email = str(claims.get("email") or "").strip()
    if not email:
        raise GoogleAuthError("Google credential has no email address.")
    return claims
