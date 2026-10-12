"""Storage for uploaded PDF files: local disk (always) + optional Supabase Storage."""

from pathlib import Path
import shutil
from typing import Any


class FileStorageError(RuntimeError):
    pass


class FileStorage:
    """Keeps the original uploaded PDFs so users can view them later.

    Files live under ``<instance>/uploads/<paper_id>/<filename>``. When a Supabase
    client is configured, a copy is also pushed to the ``papers`` storage bucket.
    The local copy is the reliable fallback used by the View Document flow.
    """

    def __init__(self, config: dict[str, Any], supabase_client: Any = None):
        base = Path(config.get("LOCAL_DB_PATH") or "instance/demo.sqlite3")
        self.base_dir = base.parent
        self.root = self.base_dir / "uploads"
        self.client = supabase_client
        self.bucket = str(config.get("SUPABASE_STORAGE_BUCKET") or "papers")

    def _paper_dir(self, paper_id: str) -> Path:
        safe_id = "".join(ch for ch in str(paper_id) if ch.isalnum() or ch in "-_")
        if not safe_id:
            raise FileStorageError("Invalid paper id.")
        return self.root / safe_id

    def save(self, paper_id: str, filename: str, data: bytes) -> dict[str, Any]:
        try:
            target_dir = self._paper_dir(paper_id)
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / filename
            target.write_bytes(data)
        except Exception as exc:
            raise FileStorageError(f"Could not store the uploaded file: {exc}") from exc

        info = {
            "file_path": f"uploads/{target_dir.name}/{filename}",
            "file_size": len(data),
            "storage": "local",
        }
        if self.client:
            try:
                self.client.storage.from_(self.bucket).upload(
                    f"{target_dir.name}/{filename}", data
                )
                info["storage"] = "local+supabase"
            except Exception:
                # Supabase Storage is optional; the local copy is enough to serve the file.
                pass
        return info

    def _resolve(self, file_path: str) -> Path | None:
        if not file_path:
            return None
        candidate = (self.base_dir / file_path).resolve()
        root = self.root.resolve()
        if candidate != root and root not in candidate.parents:
            return None
        return candidate

    def exists(self, file_path: str) -> bool:
        path = self._resolve(file_path)
        return bool(path and path.is_file())

    def read(self, file_path: str) -> bytes | None:
        path = self._resolve(file_path)
        if not path or not path.is_file():
            return None
        return path.read_bytes()

    def delete(self, file_path: str) -> None:
        path = self._resolve(file_path)
        if not path:
            return
        try:
            if path.is_file():
                path.unlink()
            parent = path.parent
            if parent != self.root and parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
        except Exception:
            pass

    def delete_paper(self, paper_id: str) -> None:
        directory = self._paper_dir(paper_id)
        try:
            if directory.is_dir():
                shutil.rmtree(directory, ignore_errors=True)
        except Exception:
            pass
