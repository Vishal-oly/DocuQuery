from datetime import timedelta
from pathlib import Path
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


ROOT_DIR = Path(__file__).resolve().parents[1]


def _load_env_file(path=None) -> None:
    """Load key=value lines from the project .env file into os.environ.

    Runs as a fallback when python-dotenv is not installed, and only fills
    variables that are not already set in the environment.
    """
    env_path = Path(path) if path else ROOT_DIR / ".env"
    if not env_path.is_file():
        return
    try:
        lines = env_path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name and name not in os.environ:
            os.environ[name] = value


_load_env_file()


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


class Config:
    """Application settings. Secrets are read only from the server environment."""

    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "local-demo-key-change-before-deploy")
    MAX_CONTENT_LENGTH = _int_env("MAX_UPLOAD_MB", 40) * 1024 * 1024
    # Scanned pages read through the optional OCR add-on; 0 disables it.
    OCR_MAX_PAGES = _int_env("OCR_MAX_PAGES", 20)
    # Keep paper tables as Markdown chunks (needs the optional pdfplumber add-on).
    TABLE_EXTRACTION = os.getenv("TABLE_EXTRACTION", "true").lower() == "true"
    # How many questions the "Exam questions" / "MCQ quiz" chips generate.
    QUESTION_COUNT = _int_env("QUESTION_COUNT", 8)
    MCQ_COUNT = _int_env("MCQ_COUNT", 5)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"

    OLLAMA_ENABLED = os.getenv("OLLAMA_ENABLED", "true").lower() == "true"
    OLLAMA_PORT = _int_env("OLLAMA_PORT", 11434)
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b").strip()
    OLLAMA_TIMEOUT_SECONDS = _int_env("OLLAMA_TIMEOUT_SECONDS", 120)

    # auto = use Ollama if it has the model, else any local OpenAI-compatible server.
    LLM_BACKEND = os.getenv("LLM_BACKEND", "auto").strip().lower()
    OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:1234/v1").strip()
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "").strip()
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
    OPENAI_TIMEOUT_SECONDS = _int_env("OPENAI_TIMEOUT_SECONDS", 120)
    # Set by local_ai.py when it can hot-swap the model server.
    MANAGED_MODEL = os.getenv("DOCUQUERY_MANAGED_MODEL", "").strip().lower() == "true"

    LOCAL_DB_PATH = os.getenv("LOCAL_DB_PATH", str(ROOT_DIR / "instance" / "demo.sqlite3"))
    EMBEDDING_BACKEND = os.getenv("EMBEDDING_BACKEND", "hashing").strip().lower()
    EMBEDDING_MODEL = os.getenv(
        "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
    ).strip()
    EMBEDDING_DIMENSION = 384
    RAG_TOP_K = _int_env("RAG_TOP_K", 4)
    SUMMARY_CONTEXT_CHARS = _int_env("SUMMARY_CONTEXT_CHARS", 9000)
    ANSWER_CONTEXT_CHARS = _int_env("ANSWER_CONTEXT_CHARS", 12000)
    # brief | balanced | detailed — how long generated answers should be
    ANSWER_DETAIL = os.getenv("ANSWER_DETAIL", "balanced").strip().lower()
    ANSWER_MAX_TOKENS = _int_env("ANSWER_MAX_TOKENS", 0)
    SUMMARY_MAX_TOKENS = _int_env("SUMMARY_MAX_TOKENS", 900)
    MAX_QUESTION_CHARS = _int_env("MAX_QUESTION_CHARS", 1200)
