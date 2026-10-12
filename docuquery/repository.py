"""Persistence layer: Supabase/pgvector in production, SQLite for local demo mode."""

from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3
from typing import Any


class RepositoryError(RuntimeError):
    pass


class UserExistsError(RepositoryError):
    """Raised when registering with an email that already has an account."""


class Repository:
    def __init__(self, config: dict[str, Any]):
        self.url = config.get("SUPABASE_URL", "").strip()
        self.service_key = config.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        self.db_path = str(config.get("LOCAL_DB_PATH", "instance/demo.sqlite3"))
        self.dimension = int(config.get("EMBEDDING_DIMENSION", 384))
        self.client = None
        self.mode = "local SQLite demo"

        if self.url and self.service_key:
            try:
                from supabase import create_client
                self.client = create_client(self.url, self.service_key)
                self.mode = "Supabase pgvector"
            except Exception as exc:
                raise RepositoryError(f"Could not initialize Supabase client: {exc}") from exc
        else:
            self._initialize_local()

    def _connect(self):
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize_local(self) -> None:
        try:
            with self._connect() as connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        email TEXT NOT NULL UNIQUE,
                        password_hash TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        reset_token TEXT,
                        reset_expires TEXT
                    );
                    CREATE TABLE IF NOT EXISTS papers (
                        id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        title TEXT NOT NULL,
                        filename TEXT NOT NULL,
                        page_count INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        summary TEXT NOT NULL DEFAULT '{}',
                        file_path TEXT,
                        file_size INTEGER NOT NULL DEFAULT 0
                    );
                    CREATE INDEX IF NOT EXISTS papers_session_idx ON papers(session_id, created_at);
                    CREATE TABLE IF NOT EXISTS paper_chunks (
                        id TEXT PRIMARY KEY,
                        paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
                        session_id TEXT NOT NULL,
                        page_number INTEGER NOT NULL,
                        section TEXT NOT NULL,
                        content TEXT NOT NULL,
                        embedding TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS paper_chunks_paper_idx ON paper_chunks(paper_id, session_id);
                    """
                )
        except Exception as exc:
            raise RepositoryError(f"Could not initialize local SQLite storage: {exc}") from exc
        # Older demo databases may predate these columns; extend them in place.
        try:
            with self._connect() as connection:
                columns = {
                    row["name"]
                    for row in connection.execute("PRAGMA table_info(users)").fetchall()
                }
                if "reset_token" not in columns:
                    connection.execute("ALTER TABLE users ADD COLUMN reset_token TEXT")
                if "reset_expires" not in columns:
                    connection.execute("ALTER TABLE users ADD COLUMN reset_expires TEXT")
                paper_columns = {
                    row["name"]
                    for row in connection.execute("PRAGMA table_info(papers)").fetchall()
                }
                if "file_path" not in paper_columns:
                    connection.execute("ALTER TABLE papers ADD COLUMN file_path TEXT")
                if "file_size" not in paper_columns:
                    connection.execute(
                        "ALTER TABLE papers ADD COLUMN file_size INTEGER NOT NULL DEFAULT 0"
                    )
        except Exception as exc:
            raise RepositoryError(f"Could not upgrade local SQLite storage: {exc}") from exc

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _decode_summary(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else {}
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}

    def save_user(self, user: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "password_hash": user["password_hash"],
            "created_at": user.get("created_at") or self._now(),
        }
        try:
            if self.client:
                self.client.table("users").insert(payload).execute()
                return self._user_from_row(payload)
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO users (id, name, email, password_hash, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        payload["id"], payload["name"], payload["email"],
                        payload["password_hash"], payload["created_at"],
                    ),
                )
            return self._user_from_row(payload)
        except Exception as exc:
            message = str(exc).lower()
            if "duplicate" in message or "unique" in message:
                raise UserExistsError("An account with this email already exists.") from exc
            raise RepositoryError(self._explain_remote(exc)) from exc

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        try:
            if self.client:
                result = (
                    self.client.table("users")
                    .select("id,name,email,password_hash,created_at")
                    .eq("email", email)
                    .limit(1)
                    .execute()
                )
                rows = result.data or []
                return self._user_from_row(rows[0]) if rows else None
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM users WHERE email = ? LIMIT 1", (email,)
                ).fetchone()
            return self._user_from_row(dict(row)) if row else None
        except Exception as exc:
            raise RepositoryError(self._explain_remote(exc)) from exc

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        try:
            if self.client:
                result = (
                    self.client.table("users")
                    .select("id,name,email,password_hash,created_at")
                    .eq("id", user_id)
                    .limit(1)
                    .execute()
                )
                rows = result.data or []
                return self._user_from_row(rows[0]) if rows else None
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM users WHERE id = ? LIMIT 1", (user_id,)
                ).fetchone()
            return self._user_from_row(dict(row)) if row else None
        except Exception as exc:
            raise RepositoryError(self._explain_remote(exc)) from exc

    def update_user_name(self, user_id: str, name: str) -> dict[str, Any] | None:
        try:
            if self.client:
                result = (
                    self.client.table("users")
                    .update({"name": name})
                    .eq("id", user_id)
                    .select("id,name,email,password_hash,created_at")
                    .execute()
                )
                rows = result.data or []
                return self._user_from_row(rows[0]) if rows else None
            with self._connect() as connection:
                connection.execute(
                    "UPDATE users SET name = ? WHERE id = ?", (name, user_id)
                )
            return self.get_user(user_id)
        except Exception as exc:
            raise RepositoryError(self._explain_remote(exc)) from exc

    def update_user_password(self, user_id: str, password_hash: str) -> bool:
        try:
            if self.client:
                result = (
                    self.client.table("users")
                    .update({"password_hash": password_hash, "reset_token": None, "reset_expires": None})
                    .eq("id", user_id)
                    .select("id")
                    .execute()
                )
                return bool(result.data)
            with self._connect() as connection:
                cursor = connection.execute(
                    "UPDATE users SET password_hash = ?, reset_token = NULL, reset_expires = NULL WHERE id = ?",
                    (password_hash, user_id),
                )
                return cursor.rowcount > 0
        except Exception as exc:
            raise RepositoryError(self._explain_remote(exc)) from exc

    def set_reset_token(self, email: str, token: str, expires: str) -> bool:
        try:
            if self.client:
                result = (
                    self.client.table("users")
                    .update({"reset_token": token, "reset_expires": expires})
                    .eq("email", email)
                    .select("id")
                    .execute()
                )
                return bool(result.data)
            with self._connect() as connection:
                cursor = connection.execute(
                    "UPDATE users SET reset_token = ?, reset_expires = ? WHERE email = ?",
                    (token, expires, email),
                )
                return cursor.rowcount > 0
        except Exception as exc:
            raise RepositoryError(self._explain_remote(exc)) from exc

    def get_user_by_reset_token(self, token: str) -> dict[str, Any] | None:
        try:
            if self.client:
                result = (
                    self.client.table("users")
                    .select("id,name,email,password_hash,created_at,reset_expires")
                    .eq("reset_token", token)
                    .limit(1)
                    .execute()
                )
                rows = result.data or []
                return self._user_from_row(rows[0]) if rows else None
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM users WHERE reset_token = ? LIMIT 1", (token,)
                ).fetchone()
            return self._user_from_row(dict(row)) if row else None
        except Exception as exc:
            raise RepositoryError(self._explain_remote(exc)) from exc

    @classmethod
    def _user_from_row(cls, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row.get("id"),
            "name": row.get("name") or "",
            "email": row.get("email") or "",
            "password_hash": row.get("password_hash") or "",
            "created_at": row.get("created_at"),
            "reset_token": row.get("reset_token"),
            "reset_expires": row.get("reset_expires"),
        }

    def save_paper(self, paper: dict[str, Any]) -> None:
        payload = {
            "id": paper["id"],
            "session_id": paper["session_id"],
            "title": paper["title"],
            "filename": paper["filename"],
            "page_count": int(paper["page_count"]),
            "created_at": paper.get("created_at") or self._now(),
            "summary": paper.get("summary") or {},
            "file_path": paper.get("file_path") or "",
            "file_size": int(paper.get("file_size") or 0),
        }
        try:
            if self.client:
                self.client.table("papers").insert(payload).execute()
                return
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO papers (id, session_id, title, filename, page_count, created_at, summary, file_path, file_size) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        payload["id"], payload["session_id"], payload["title"], payload["filename"],
                        payload["page_count"], payload["created_at"], json.dumps(payload["summary"]),
                        payload["file_path"], payload["file_size"],
                    ),
                )
        except Exception as exc:
            raise RepositoryError(self._explain_remote(exc)) from exc

    def save_chunks(self, chunks: list[dict[str, Any]]) -> None:
        if not chunks:
            return
        try:
            if self.client:
                batch_size = 100
                for start in range(0, len(chunks), batch_size):
                    self.client.table("paper_chunks").insert(chunks[start : start + batch_size]).execute()
                return
            with self._connect() as connection:
                connection.executemany(
                    "INSERT INTO paper_chunks (id, paper_id, session_id, page_number, section, content, embedding) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [
                        (
                            chunk["id"], chunk["paper_id"], chunk["session_id"],
                            int(chunk["page_number"]), chunk["section"], chunk["content"],
                            json.dumps(chunk["embedding"]),
                        )
                        for chunk in chunks
                    ],
                )
        except Exception as exc:
            raise RepositoryError(self._explain_remote(exc)) from exc

    def update_summary(self, session_id: str, paper_id: str, summary: dict[str, Any]) -> None:
        try:
            if self.client:
                result = (
                    self.client.table("papers")
                    .update({"summary": summary})
                    .eq("id", paper_id)
                    .eq("session_id", session_id)
                    .select("id")
                    .execute()
                )
                if not result.data:
                    raise RepositoryError("Paper not found in this session.")
                return
            with self._connect() as connection:
                cursor = connection.execute(
                    "UPDATE papers SET summary = ? WHERE id = ? AND session_id = ?",
                    (json.dumps(summary), paper_id, session_id),
                )
                if cursor.rowcount == 0:
                    raise RepositoryError("Paper not found in this session.")
        except RepositoryError:
            raise
        except Exception as exc:
            raise RepositoryError(self._explain_remote(exc)) from exc

    def list_papers(self, session_id: str) -> list[dict[str, Any]]:
        try:
            if self.client:
                result = (
                    self.client.table("papers")
                    .select("id,session_id,title,filename,page_count,created_at,summary")
                    .eq("session_id", session_id)
                    .order("created_at", desc=True)
                    .execute()
                )
                return [self._paper_from_row(row) for row in (result.data or [])]
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT * FROM papers WHERE session_id = ? ORDER BY created_at DESC",
                    (session_id,),
                ).fetchall()
            return [self._paper_from_row(dict(row)) for row in rows]
        except Exception as exc:
            raise RepositoryError(self._explain_remote(exc)) from exc

    def get_paper(self, session_id: str, paper_id: str) -> dict[str, Any] | None:
        try:
            if self.client:
                result = (
                    self.client.table("papers")
                    .select("id,session_id,title,filename,page_count,created_at,summary")
                    .eq("id", paper_id)
                    .eq("session_id", session_id)
                    .limit(1)
                    .execute()
                )
                rows = result.data or []
                return self._paper_from_row(rows[0]) if rows else None
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM papers WHERE id = ? AND session_id = ? LIMIT 1",
                    (paper_id, session_id),
                ).fetchone()
            return self._paper_from_row(dict(row)) if row else None
        except Exception as exc:
            raise RepositoryError(self._explain_remote(exc)) from exc

    def search_chunks(
        self, session_id: str, paper_id: str, query_embedding: list[float], limit: int = 6
    ) -> list[dict[str, Any]]:
        try:
            if self.client:
                result = self.client.rpc(
                    "match_paper_chunks",
                    {
                        "query_embedding": query_embedding,
                        "match_session_id": session_id,
                        "match_paper_id": paper_id,
                        "match_count": int(limit),
                    },
                ).execute()
                return [dict(row) for row in (result.data or [])]

            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT id, paper_id, session_id, page_number, section, content, embedding "
                    "FROM paper_chunks WHERE paper_id = ? AND session_id = ?",
                    (paper_id, session_id),
                ).fetchall()
            ranked = []
            for row in rows:
                item = dict(row)
                vector = json.loads(item.pop("embedding", "[]"))
                score = self._cosine(query_embedding, vector)
                item["similarity"] = score
                ranked.append(item)
            ranked.sort(key=lambda item: item["similarity"], reverse=True)
            return ranked[: max(1, min(int(limit), 20))]
        except Exception as exc:
            raise RepositoryError(self._explain_remote(exc)) from exc

    def list_chunks(self, session_id: str, paper_id: str) -> list[dict[str, Any]]:
        """All chunks for a paper (without embeddings), ordered by page."""
        try:
            if self.client:
                result = (
                    self.client.table("paper_chunks")
                    .select("id,paper_id,session_id,page_number,section,content")
                    .eq("paper_id", paper_id)
                    .eq("session_id", session_id)
                    .order("page_number")
                    .execute()
                )
                return [dict(row) for row in (result.data or [])]
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT id, paper_id, session_id, page_number, section, content "
                    "FROM paper_chunks WHERE paper_id = ? AND session_id = ? ORDER BY page_number",
                    (paper_id, session_id),
                ).fetchall()
            return [dict(row) for row in rows]
        except Exception as exc:
            raise RepositoryError(self._explain_remote(exc)) from exc

    def delete_paper(self, session_id: str, paper_id: str) -> bool:
        try:
            if self.client:
                result = (
                    self.client.table("papers")
                    .delete()
                    .eq("id", paper_id)
                    .eq("session_id", session_id)
                    .select("id")
                    .execute()
                )
                return bool(result.data)
            with self._connect() as connection:
                cursor = connection.execute(
                    "DELETE FROM papers WHERE id = ? AND session_id = ?",
                    (paper_id, session_id),
                )
                return cursor.rowcount > 0
        except Exception as exc:
            raise RepositoryError(self._explain_remote(exc)) from exc

    @classmethod
    def _paper_from_row(cls, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row.get("id"),
            "session_id": row.get("session_id"),
            "title": row.get("title") or "Untitled paper",
            "filename": row.get("filename") or "paper.pdf",
            "page_count": int(row.get("page_count") or 0),
            "created_at": row.get("created_at"),
            "summary": cls._decode_summary(row.get("summary")),
            "file_path": row.get("file_path") or "",
            "file_size": int(row.get("file_size") or 0),
        }

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        if not left or len(left) != len(right):
            return 0.0
        dot = sum(float(a) * float(b) for a, b in zip(left, right))
        left_norm = math.sqrt(sum(float(a) ** 2 for a in left))
        right_norm = math.sqrt(sum(float(b) ** 2 for b in right))
        if not left_norm or not right_norm:
            return 0.0
        return dot / (left_norm * right_norm)

    def _explain_remote(self, error: Exception) -> str:
        message = str(error)
        if self.client:
            return (
                "Supabase request failed. Check your URL/service-role key and run "
                "schema/supabase.sql in the Supabase SQL Editor. Details: " + message
            )
        return "Local storage error: " + message
