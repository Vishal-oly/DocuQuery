from datetime import timedelta
from pathlib import Path
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


ROOT_DIR = Path(__file__).resolve().parents[1]


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


class Config:
    """Application settings. Secrets are read only from the server environment."""

    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "local-demo-key-change-before-deploy")
    MAX_CONTENT_LENGTH = _int_env("MAX_UPLOAD_MB", 20) * 1024 * 1024
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"

    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
    GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b").strip()

    SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
    # Google Sign-In (Identity Services). Create an OAuth Client ID in Google Cloud
    # Console and paste just the client id here.
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    # This is a server-only key. Never put it in JavaScript or a public repo.
    SUPABASE_SERVICE_ROLE_KEY = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        or os.getenv("SUPABASE_KEY", "").strip()
    )

    LOCAL_DB_PATH = os.getenv("LOCAL_DB_PATH", str(ROOT_DIR / "instance" / "demo.sqlite3"))
    EMBEDDING_BACKEND = os.getenv("EMBEDDING_BACKEND", "hashing").strip().lower()
    EMBEDDING_MODEL = os.getenv(
        "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
    ).strip()
    EMBEDDING_DIMENSION = 384
    RAG_TOP_K = _int_env("RAG_TOP_K", 6)
    SUMMARY_CONTEXT_CHARS = _int_env("SUMMARY_CONTEXT_CHARS", 18000)
    MAX_QUESTION_CHARS = _int_env("MAX_QUESTION_CHARS", 1200)
