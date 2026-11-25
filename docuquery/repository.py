"""Persistence layer: local SQLite."""

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
        self.db_path = str(config.get("LOCAL_DB_PATH", "instance/demo.sqlite3"))
        self.dimension = int(config.get("EMBEDDING_DIMENSION", 384))
        self.mode = "local SQLite demo"

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
                        kind TEXT NOT NULL DEFAULT 'text',
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
                chunk_columns = {
                    row["name"]
                    for row in connection.execute("PRAGMA table_info(paper_chunks)").fetchall()
                }
                if "kind" not in chunk_columns:
                    connection.execute(
                        "ALTER TABLE paper_chunks ADD COLUMN kind TEXT NOT NULL DEFAULT 'text'"
                    )
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
            raise RepositoryError(str(exc)) from exc

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM users WHERE email = ? LIMIT 1", (email,)
                ).fetchone()
            return self._user_from_row(dict(row)) if row else None
        except Exception as exc:
            raise RepositoryError(str(exc)) from exc

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM users WHERE id = ? LIMIT 1", (user_id,)
                ).fetchone()
            return self._user_from_row(dict(row)) if row else None
        except Exception as exc:
            raise RepositoryError(str(exc)) from exc

    def update_user_name(self, user_id: str, name: str) -> dict[str, Any] | None:
        try:
            with self._connect() as connection:
                connection.execute(
                    "UPDATE users SET name = ? WHERE id = ?", (name, user_id)
                )
            return self.get_user(user_id)
        except Exception as exc:
            raise RepositoryError(str(exc)) from exc

    def update_user_password(self, user_id: str, password_hash: str) -> bool:
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    "UPDATE users SET password_hash = ?, reset_token = NULL, reset_expires = NULL WHERE id = ?",
                    (password_hash, user_id),
                )
                return cursor.rowcount > 0
        except Exception as exc:
            raise RepositoryError(str(exc)) from exc

    def set_reset_token(self, email: str, token: str, expires: str) -> bool:
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    "UPDATE users SET reset_token = ?, reset_expires = ? WHERE email = ?",
                    (token, expires, email),
                )
                return cursor.rowcount > 0
        except Exception as exc:
            raise RepositoryError(str(exc)) from exc

    def get_user_by_reset_token(self, token: str) -> dict[str, Any] | None:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM users WHERE reset_token = ? LIMIT 1", (token,)
                ).fetchone()
            return self._user_from_row(dict(row)) if row else None
        except Exception as exc:
            raise RepositoryError(str(exc)) from exc

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
            raise RepositoryError(str(exc)) from exc

    def save_chunks(self, chunks: list[dict[str, Any]]) -> None:
        if not chunks:
            return
        try:
            with self._connect() as connection:
                connection.executemany(
                    "INSERT INTO paper_chunks (id, paper_id, session_id, page_number, section, content, kind, embedding) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        (
                            chunk["id"], chunk["paper_id"], chunk["session_id"],
                            int(chunk["page_number"]), chunk["section"], chunk["content"],
                            chunk.get("kind", "text"), json.dumps(chunk["embedding"]),
                        )
                        for chunk in chunks
                    ],
                )
        except Exception as exc:
            raise RepositoryError(str(exc)) from exc

    def update_summary(self, session_id: str, paper_id: str, summary: dict[str, Any]) -> None:
        try:
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
            raise RepositoryError(str(exc)) from exc

    def list_papers(self, session_id: str) -> list[dict[str, Any]]:
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT * FROM papers WHERE session_id = ? ORDER BY created_at DESC",
                    (session_id,),
                ).fetchall()
            return [self._paper_from_row(dict(row)) for row in rows]
        except Exception as exc:
            raise RepositoryError(str(exc)) from exc

    def get_paper(self, session_id: str, paper_id: str) -> dict[str, Any] | None:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM papers WHERE id = ? AND session_id = ? LIMIT 1",
                    (paper_id, session_id),
                ).fetchone()
            return self._paper_from_row(dict(row)) if row else None
        except Exception as exc:
            raise RepositoryError(str(exc)) from exc

    def search_chunks(
        self, session_id: str, paper_id: str, query_embedding: list[float], limit: int = 6
    ) -> list[dict[str, Any]]:
        try:

            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT id, paper_id, session_id, page_number, section, content, kind, embedding "
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
            raise RepositoryError(str(exc)) from exc

    def list_chunks(self, session_id: str, paper_id: str) -> list[dict[str, Any]]:
        """All chunks for a paper (without embeddings), ordered by page."""
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT id, paper_id, session_id, page_number, section, content, kind "
                    "FROM paper_chunks WHERE paper_id = ? AND session_id = ? ORDER BY page_number",
                    (paper_id, session_id),
                ).fetchall()
            return [dict(row) for row in rows]
        except Exception as exc:
            raise RepositoryError(str(exc)) from exc

    def delete_paper(self, session_id: str, paper_id: str) -> bool:
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    "DELETE FROM papers WHERE id = ? AND session_id = ?",
                    (paper_id, session_id),
                )
                return cursor.rowcount > 0
        except Exception as exc:
            raise RepositoryError(str(exc)) from exc

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
