"""Storage for uploaded PDF files: local disk + Supabase Storage cloud copy.

On platforms with a read-only or ephemeral filesystem (Render, Fly, Vercel),
the Supabase copy keeps every PDF reachable. Reads try local first and fall
back to Supabase; writes push to both whenever possible.
"""

from pathlib import Path
import shutil
from typing import Any


class FileStorageError(RuntimeError):
    pass


class FileStorage:
    """Keeps the original uploaded PDFs so users can view them later.

    Files live under ``<instance>/uploads/<paper_id>/<filename>`` locally and at
    ``<paper_id>/<filename>`` in the configured Supabase Storage bucket. The
    stored ``file_path`` is always the logical ``uploads/...`` form so records
    stay portable between deployment modes.
    """

    def __init__(self, config: dict[str, Any], supabase_client: Any = None):
        base = Path(config.get("LOCAL_DB_PATH") or "instance/demo.sqlite3")
        self.base_dir = base.parent
        self.root = self.base_dir / "uploads"
        self.client = supabase_client
        self.bucket = str(config.get("SUPABASE_STORAGE_BUCKET") or "papers")
        self.cloud_only = bool(config.get("SUPABASE_STORAGE_PRIMARY"))

    def _paper_dir(self, paper_id: str) -> Path:
        safe_id = "".join(ch for ch in str(paper_id) if ch.isalnum() or ch in "-_")
        if not safe_id:
            raise FileStorageError("Invalid paper id.")
        return self.root / safe_id

    @staticmethod
    def _object_key(file_path: str) -> str:
        """Map a stored ``uploads/<id>/<name>`` path to the bucket object key."""
        return file_path.removeprefix("uploads/").lstrip("/")

    # ------------------------------------------------------------------ write
    def save(self, paper_id: str, filename: str, data: bytes) -> dict[str, Any]:
        target_dir = self._paper_dir(paper_id)
        logical_path = f"uploads/{target_dir.name}/{filename}"
        info: dict[str, Any] = {
            "file_path": logical_path,
            "file_size": len(data),
            "storage": "none",
        }

        local_ok = False
        if not self.cloud_only:
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
                (target_dir / filename).write_bytes(data)
                local_ok = True
                info["storage"] = "local"
            except Exception:
                if not self.client:
                    raise FileStorageError("Could not store the uploaded file on disk.")
                # Cloud copy below becomes the primary store.

        if self.client:
            try:
                self.client.storage.from_(self.bucket).upload(
                    self._object_key(logical_path), data
                )
                info["storage"] = "local+supabase" if local_ok else "supabase"
            except Exception:
                if not local_ok:
                    raise FileStorageError(
                        "Could not store the uploaded file in Supabase Storage."
                    )
                # Local copy is enough to serve the file.
        if info["storage"] == "none":
            raise FileStorageError("Could not store the uploaded file: no storage available.")
        return info

    # ------------------------------------------------------------------- read
    def _resolve(self, file_path: str) -> Path | None:
        if not file_path:
            return None
        candidate = (self.base_dir / file_path).resolve()
        root = self.root.resolve()
        if candidate != root and root not in candidate.parents:
            return None
        return candidate

    def _download(self, file_path: str) -> bytes | None:
        if not self.client or not file_path:
            return None
        try:
            return bytes(self.client.storage.from_(self.bucket).download(self._object_key(file_path)))
        except Exception:
            return None

    def exists(self, file_path: str) -> bool:
        path = self._resolve(file_path)
        if path and path.is_file():
            return True
        return self._download(file_path) is not None

    def read(self, file_path: str) -> bytes | None:
        path = self._resolve(file_path)
        if path and path.is_file():
            return path.read_bytes()
        return self._download(file_path)

    # ----------------------------------------------------------------- delete
    def delete(self, file_path: str) -> None:
        path = self._resolve(file_path)
        if path:
            try:
                if path.is_file():
                    path.unlink()
                parent = path.parent
                if parent != self.root and parent.is_dir() and not any(parent.iterdir()):
                    parent.rmdir()
            except Exception:
                pass
        if self.client and file_path:
            try:
                self.client.storage.from_(self.bucket).remove([self._object_key(file_path)])
            except Exception:
                pass

    def delete_paper(self, paper_id: str) -> None:
        directory = self._paper_dir(paper_id)
        try:
            if directory.is_dir():
                shutil.rmtree(directory, ignore_errors=True)
        except Exception:
            pass
        if self.client:
            try:
                folder = directory.name
                entries = self.client.storage.from_(self.bucket).list(folder)
                keys = [f"{folder}/{entry.get('name')}" for entry in entries if entry.get("name")]
                if keys:
                    self.client.storage.from_(self.bucket).remove(keys)
            except Exception:
                pass
