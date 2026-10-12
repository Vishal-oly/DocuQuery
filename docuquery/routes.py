"""HTTP routes for the paper summarizer, including guest home and authentication."""

from datetime import datetime, timezone
from functools import wraps
import json
import re
import uuid

from itsdangerous import URLSafeTimedSerializer

from io import BytesIO

from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from .embeddings import EmbeddingError
from .pdf_processing import PDFProcessingError, parse_pdf_bytes
from .rag import answer_question, make_summary
from .repository import RepositoryError, UserExistsError

bp = Blueprint("main", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

TOKEN_MAX_AGE_SECONDS = 60 * 60 * 24 * 30  # 30 days


# ---------------------------------------------------------------------------
# Signed auth tokens (work where cookies are blocked, e.g. sandboxed iframes)
# ---------------------------------------------------------------------------

def _token_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="docuquery-auth-token")


def issue_token(user_id: str) -> str:
    return _token_serializer().dumps({"uid": str(user_id)})


def verify_token(token: str) -> str | None:
    try:
        data = _token_serializer().loads(token, max_age=TOKEN_MAX_AGE_SECONDS)
    except Exception:
        return None
    uid = str(data.get("uid") or "")
    return uid or None


# ---------------------------------------------------------------------------
# Session and auth helpers
# ---------------------------------------------------------------------------

def _session_id() -> str:
    user = _current_user()
    if user:
        return str(user["id"])
    if "research_session_id" not in session:
        session["research_session_id"] = str(uuid.uuid4())
        session.permanent = True
    return session["research_session_id"]


def _current_user() -> dict | None:
    """Signed-in user from an auth token (header or ?token=) or the cookie session."""
    token = ""
    auth_header = request.headers.get("Authorization", "")
    if auth_header[:7].lower() == "bearer ":
        token = auth_header[7:].strip()
    if not token:
        token = (request.args.get("token") or "").strip()
    if not token:
        token = (request.headers.get("X-Auth-Token") or "").strip()
    if token:
        user_id = verify_token(token)
        if user_id:
            try:
                user = _repository().get_user(user_id)
            except RepositoryError:
                user = None
            if user:
                public = _public_user(user)
                # Best effort: also set the cookie session where cookies are allowed.
                session["user"] = public
                session["research_session_id"] = str(user["id"])
                session.permanent = True
                return public
    return session.get("user")


def _public_user(user: dict) -> dict:
    hidden = {"password_hash", "reset_token", "reset_expires"}
    return {key: value for key, value in user.items() if key not in hidden}


def _storage():
    return current_app.extensions["paper_storage"]


def _sign_in(user: dict) -> None:
    """Mark the browser as signed in; papers become scoped to the account."""
    session.clear()
    session["user"] = _public_user(user)
    # The account id is a UUID, so it also works as the Supabase session scope.
    session["research_session_id"] = str(user["id"])
    session.permanent = True
    return issue_token(str(user["id"]))


def _repository():
    return current_app.extensions["paper_repository"]


def _embedder():
    return current_app.extensions["paper_embedder"]


def _public_paper(paper: dict) -> dict:
    """Do not return server-side session identifiers or storage paths to the browser."""
    public = {
        key: value
        for key, value in paper.items()
        if key not in ("session_id", "file_path")
    }
    public["has_file"] = bool(paper.get("file_path"))
    return public


def api_login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not _current_user():
            return jsonify({"error": "Please sign in to continue."}), 401
        return view(*args, **kwargs)

    return wrapped


def page_login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not _current_user():
            return redirect(url_for("main.login_page", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def _validate_credentials(name: str, email: str, password: str, registering: bool) -> list[str]:
    errors: list[str] = []
    if registering and not (2 <= len(name) <= 60):
        errors.append("Enter your name (2-60 characters).")
    if not email or len(email) > 254 or not EMAIL_RE.match(email):
        errors.append("Enter a valid email address.")
    if len(password) < 6:
        errors.append("Password must be at least 6 characters.")
    elif len(password) > 128:
        errors.append("Password is too long.")
    return errors


# ---------------------------------------------------------------------------
# Pages: guest home, login/register, and the protected workspace
# ---------------------------------------------------------------------------

@bp.get("/")
def home_page():
    return render_template("landing.html", user=_current_user())


@bp.get("/login")
def login_page():
    if _current_user():
        return redirect(url_for("main.workspace_page"))
    return render_template(
        "login.html",
        user=_current_user(),
        next=request.args.get("next", ""),
        mode=request.args.get("mode", "login"),
    )


@bp.get("/workspace")
@page_login_required
def workspace_page():
    return render_template("index.html", user=_current_user())


@bp.get("/summaries")
@page_login_required
def summaries_page():
    return render_template("summaries.html", user=_current_user())


@bp.get("/profile")
@page_login_required
def profile_page():
    return render_template("profile.html", user=_current_user())


@bp.get("/forgot")
def forgot_page():
    return render_template("forgot.html", user=_current_user())


# ---------------------------------------------------------------------------
# Auth JSON API
# ---------------------------------------------------------------------------

@bp.post("/api/register")
def register():
    body = request.get_json(silent=True) or {}
    name = str(body.get("name", "")).strip()
    email = str(body.get("email", "")).strip().lower()
    password = str(body.get("password", ""))

    errors = _validate_credentials(name, email, password, registering=True)
    if errors:
        return jsonify({"error": " ".join(errors)}), 400

    user = {
        "id": str(uuid.uuid4()),
        "name": name,
        "email": email,
        "password_hash": generate_password_hash(password),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        saved = _repository().save_user(user)
    except UserExistsError as exc:
        return jsonify({"error": str(exc)}), 409
    except RepositoryError as exc:
        return jsonify({"error": str(exc)}), 503

    _sign_in(saved)
    return jsonify({"user": _public_user(saved), "token": issue_token(str(saved["id"]))}), 201


@bp.post("/api/login")
def login():
    body = request.get_json(silent=True) or {}
    email = str(body.get("email", "")).strip().lower()
    password = str(body.get("password", ""))

    errors = _validate_credentials("", email, password, registering=False)
    if errors:
        return jsonify({"error": " ".join(errors)}), 400

    try:
        user = _repository().get_user_by_email(email)
    except RepositoryError as exc:
        return jsonify({"error": str(exc)}), 503

    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid email or password."}), 401

    _sign_in(user)
    return jsonify({"user": _public_user(user), "token": issue_token(str(user["id"]))}), 200


@bp.post("/api/logout")
def logout():
    session.clear()
    return jsonify({"logged_out": True}), 200


@bp.get("/api/me")
def me():
    user = _current_user()
    if not user:
        return jsonify({"error": "Please sign in to continue."}), 401
    return jsonify({"user": user}), 200


@bp.patch("/api/me")
@api_login_required
def update_me():
    body = request.get_json(silent=True) or {}
    name = str(body.get("name", "")).strip()
    if not (2 <= len(name) <= 60):
        return jsonify({"error": "Enter your name (2-60 characters)."}), 400
    user = _current_user()
    try:
        updated = _repository().update_user_name(user["id"], name)
    except RepositoryError as exc:
        return jsonify({"error": str(exc)}), 503
    if not updated:
        return jsonify({"error": "Account not found."}), 404
    _sign_in(updated)
    return jsonify({"user": _public_user(updated)}), 200


@bp.post("/api/me/password")
@api_login_required
def change_password():
    body = request.get_json(silent=True) or {}
    current_password = str(body.get("current_password", ""))
    new_password = str(body.get("new_password", ""))
    try:
        stored = _repository().get_user(_current_user()["id"])
    except RepositoryError as exc:
        return jsonify({"error": str(exc)}), 503
    if not stored or not check_password_hash(stored["password_hash"], current_password):
        return jsonify({"error": "Current password is incorrect."}), 401
    if len(new_password) < 6:
        return jsonify({"error": "New password must be at least 6 characters."}), 400
    if len(new_password) > 128:
        return jsonify({"error": "New password is too long."}), 400
    try:
        updated = _repository().update_user_password(
            _current_user()["id"], generate_password_hash(new_password)
        )
    except RepositoryError as exc:
        return jsonify({"error": str(exc)}), 503
    if not updated:
        return jsonify({"error": "Account not found."}), 404
    return jsonify({"updated": True}), 200


@bp.post("/api/forgot")
def forgot_password():
    body = request.get_json(silent=True) or {}
    email = str(body.get("email", "")).strip().lower()
    if not email or not EMAIL_RE.match(email):
        return jsonify({"error": "Enter a valid email address."}), 400
    try:
        user = _repository().get_user_by_email(email)
        if not user:
            # Do not reveal whether the account exists.
            return jsonify(
                {
                    "sent": True,
                    "notice": "If that account exists, a reset code was generated.",
                }
            ), 200
        token = f"{uuid.uuid4().int % 1_000_000:06d}"
        expires = datetime.now(timezone.utc).isoformat()
        _repository().set_reset_token(email, token, expires)
    except RepositoryError as exc:
        return jsonify({"error": str(exc)}), 503
    # Email delivery is not configured in this demo, so the code is returned to the page.
    return jsonify(
        {
            "sent": True,
            "reset_token": token,
            "notice": "Email delivery is not configured in this demo — use the reset code shown below.",
        }
    ), 200


@bp.post("/api/reset")
def reset_password():
    body = request.get_json(silent=True) or {}
    token = str(body.get("token", "")).strip()
    new_password = str(body.get("new_password", ""))
    if not token:
        return jsonify({"error": "Enter the reset code."}), 400
    if len(new_password) < 6:
        return jsonify({"error": "New password must be at least 6 characters."}), 400
    if len(new_password) > 128:
        return jsonify({"error": "New password is too long."}), 400
    try:
        user = _repository().get_user_by_reset_token(token)
    except RepositoryError as exc:
        return jsonify({"error": str(exc)}), 503
    if not user:
        return jsonify({"error": "Invalid or expired reset code."}), 400
    expires = user.get("reset_expires")
    if expires:
        try:
            issued = datetime.fromisoformat(expires)
            if (datetime.now(timezone.utc) - issued).total_seconds() > 900:
                return jsonify({"error": "Invalid or expired reset code."}), 400
        except ValueError:
            pass
    try:
        _repository().update_user_password(user["id"], generate_password_hash(new_password))
    except RepositoryError as exc:
        return jsonify({"error": str(exc)}), 503
    return jsonify({"reset": True}), 200


# ---------------------------------------------------------------------------
# Paper workspace JSON API
# ---------------------------------------------------------------------------

@bp.get("/api/health")
def health():
    config = current_app.config
    return jsonify(
        {
            "status": "ok",
            "database": _repository().mode,
            "llm_available": bool(config.get("GROQ_API_KEY")),
            "llm_model": config.get("GROQ_MODEL"),
            "embedding_backend": config.get("EMBEDDING_BACKEND"),
            "max_upload_mb": max(1, int(config.get("MAX_CONTENT_LENGTH", 20 * 1024 * 1024) / (1024 * 1024))),
        }
    )


@bp.get("/api/papers")
@api_login_required
def list_papers():
    try:
        papers = _repository().list_papers(_session_id())
        return jsonify({"papers": [_public_paper(paper) for paper in papers]})
    except RepositoryError as exc:
        return jsonify({"error": str(exc)}), 503


@bp.get("/api/papers/<paper_id>")
@api_login_required
def get_paper(paper_id: str):
    try:
        paper = _repository().get_paper(_session_id(), paper_id)
        if not paper:
            return jsonify({"error": "Paper not found in this account."}), 404
        return jsonify({"paper": _public_paper(paper)})
    except RepositoryError as exc:
        return jsonify({"error": str(exc)}), 503


@bp.post("/api/upload")
@api_login_required
def upload_pdf():
    upload = request.files.get("pdf")
    if not upload or not upload.filename:
        return jsonify({"error": "Choose a PDF file to upload."}), 400
    filename = secure_filename(upload.filename)
    if not filename or not filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files are supported."}), 400

    try:
        raw = upload.read()
        parsed = parse_pdf_bytes(raw, filename)
        embedder = _embedder()
        vectors = embedder.embed([chunk["content"] for chunk in parsed["chunks"]])
        if len(vectors) != len(parsed["chunks"]):
            raise EmbeddingError("The embedding model returned an unexpected number of vectors.")

        session_id = _session_id()
        paper_id = str(uuid.uuid4())
        try:
            stored = _storage().save(paper_id, filename, raw)
        except Exception as exc:  # storage problems should not block the demo flow
            current_app.logger.warning("Could not store the uploaded PDF: %s", exc)
            stored = {"file_path": "", "file_size": len(raw), "storage": "skipped"}
        paper = {
            "id": paper_id,
            "session_id": session_id,
            "title": parsed["title"],
            "filename": filename,
            "page_count": parsed["page_count"],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "summary": {},
            "file_path": stored.get("file_path", ""),
            "file_size": stored.get("file_size", len(raw)),
        }
        chunk_rows = []
        fallback_chunks = []
        for raw_chunk, embedding in zip(parsed["chunks"], vectors):
            row = {
                "id": str(uuid.uuid4()),
                "paper_id": paper_id,
                "session_id": session_id,
                "page_number": raw_chunk["page_number"],
                "section": raw_chunk["section"],
                "content": raw_chunk["content"],
                "embedding": embedding,
            }
            chunk_rows.append(row)
            fallback_chunks.append({**row, "similarity": 0.0})

        repository = _repository()
        repository.save_paper(paper)
        repository.save_chunks(chunk_rows)

        summary, sources = make_summary(
            repository,
            embedder,
            current_app.config,
            session_id,
            paper,
            fallback_chunks,
        )
        summary["sources"] = sources
        paper["summary"] = summary
        repository.update_summary(session_id, paper_id, summary)

        return jsonify(
            {
                "paper": _public_paper(paper),
                "summary": summary,
                "chunk_count": len(chunk_rows),
                "database": repository.mode,
                "text_char_count": parsed["text_char_count"],
            }
        ), 201
    except PDFProcessingError as exc:
        return jsonify({"error": str(exc)}), 400
    except (RepositoryError, EmbeddingError) as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception as exc:
        current_app.logger.exception("PDF upload failed")
        return jsonify({"error": f"Could not process this PDF: {exc}"}), 500


@bp.post("/api/papers/<paper_id>/ask")
@api_login_required
def ask_paper(paper_id: str):
    body = request.get_json(silent=True) or {}
    question = str(body.get("question", "")).strip()
    if not question:
        return jsonify({"error": "Enter a question about the paper."}), 400
    if len(question) > int(current_app.config.get("MAX_QUESTION_CHARS", 1200)):
        return jsonify({"error": "That question is too long. Please keep it under 1,200 characters."}), 400

    session_id = _session_id()
    try:
        paper = _repository().get_paper(session_id, paper_id)
        if not paper:
            return jsonify({"error": "Paper not found in this account."}), 404
        result = answer_question(
            _repository(), _embedder(), current_app.config, session_id, paper, question
        )
        return jsonify(result)
    except RepositoryError as exc:
        return jsonify({"error": str(exc)}), 503
    except EmbeddingError as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception as exc:
        current_app.logger.exception("Question answering failed")
        return jsonify({"error": f"Could not answer this question: {exc}"}), 500


@bp.delete("/api/papers/<paper_id>")
@api_login_required
def delete_paper(paper_id: str):
    try:
        paper = _repository().get_paper(_session_id(), paper_id)
        removed = _repository().delete_paper(_session_id(), paper_id)
        if not removed:
            return jsonify({"error": "Paper not found in this account."}), 404
        if paper and paper.get("file_path"):
            _storage().delete(paper["file_path"])
        _storage().delete_paper(paper_id)
        return jsonify({"deleted": True})
    except RepositoryError as exc:
        return jsonify({"error": str(exc)}), 503


SUMMARY_FIELD_LABELS = (
    ("overall_summary", "Overview"),
    ("objective", "Research objective"),
    ("methodology", "Methodology"),
    ("dataset", "Data & materials"),
    ("key_findings", "Key findings"),
    ("limitations", "Limitations"),
    ("conclusion", "Conclusion"),
)


def _summary_as_markdown(paper: dict) -> str:
    summary = paper.get("summary") or {}
    lines = [
        f"# Research brief — {paper.get('title') or 'Untitled paper'}",
        "",
        f"- **File:** {paper.get('filename') or 'paper.pdf'}",
        f"- **Pages:** {paper.get('page_count') or '—'}",
        f"- **Generated:** {paper.get('created_at') or ''}",
        f"- **Mode:** {summary.get('mode') or 'research brief'}",
        "",
    ]
    if summary.get("notice"):
        lines += [f"> {summary['notice']}", ""]
    for field, label in SUMMARY_FIELD_LABELS:
        lines += [f"## {label}", "", summary.get(field) or "Not clearly stated in the retrieved text.", ""]
    sources = summary.get("sources") or []
    if sources:
        lines += ["## Evidence trail", ""]
        for source in sources:
            lines.append(
                f"- **p. {source.get('page_number', 1)}** · {source.get('section', 'Paper excerpt')} — "
                f"{(source.get('excerpt') or '').strip()}"
            )
        lines.append("")
    lines.append("_Generated by DocuQuery — verify important claims in the original paper._")
    return "\n".join(lines)


@bp.get("/api/papers/<paper_id>/file")
@api_login_required
def get_paper_file(paper_id: str):
    try:
        paper = _repository().get_paper(_session_id(), paper_id)
    except RepositoryError as exc:
        return jsonify({"error": str(exc)}), 503
    if not paper:
        return jsonify({"error": "Paper not found in this account."}), 404
    data = _storage().read(paper.get("file_path", ""))
    if data is None:
        return jsonify({"error": "The original PDF is not stored for this paper."}), 404
    return send_file(
        BytesIO(data),
        mimetype="application/pdf",
        as_attachment=False,
        download_name=paper.get("filename") or "paper.pdf",
    )


@bp.get("/api/papers/<paper_id>/download")
@api_login_required
def download_summary(paper_id: str):
    fmt = (request.args.get("format") or "md").lower()
    if fmt not in ("md", "txt", "json"):
        return jsonify({"error": "Unsupported download format. Use md, txt, or json."}), 400
    try:
        paper = _repository().get_paper(_session_id(), paper_id)
    except RepositoryError as exc:
        return jsonify({"error": str(exc)}), 503
    if not paper:
        return jsonify({"error": "Paper not found in this account."}), 404

    stem = (paper.get("title") or "research-brief")[:60].strip().replace("/", "-")
    if fmt == "json":
        payload = json.dumps(
            {"paper": _public_paper(paper), "summary": paper.get("summary") or {}},
            indent=2,
        )
        return Response(
            payload,
            mimetype="application/json",
            headers={"Content-Disposition": f'attachment; filename="{stem}.json"'},
        )
    text = _summary_as_markdown(paper)
    if fmt == "txt":
        text = re.sub(r"[#*`>_]+", "", text)
    return Response(
        text,
        mimetype="text/plain" if fmt == "txt" else "text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{stem}.{fmt}"'},
    )


@bp.post("/api/papers/<paper_id>/summarize")
@api_login_required
def summarize_paper(paper_id: str):
    session_id = _session_id()
    try:
        paper = _repository().get_paper(session_id, paper_id)
        if not paper:
            return jsonify({"error": "Paper not found in this account."}), 404
        fallback = _repository().list_chunks(session_id, paper_id)
        summary, sources = make_summary(
            _repository(),
            _embedder(),
            current_app.config,
            session_id,
            paper,
            fallback,
        )
        summary["sources"] = sources
        paper["summary"] = summary
        _repository().update_summary(session_id, paper_id, summary)
        return jsonify({"paper": _public_paper(paper), "summary": summary})
    except RepositoryError as exc:
        return jsonify({"error": str(exc)}), 503
    except EmbeddingError as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception as exc:
        current_app.logger.exception("Summary generation failed")
        return jsonify({"error": f"Could not generate a summary: {exc}"}), 500
