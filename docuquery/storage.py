"""Store uploaded PDFs on local disk alongside the SQLite database."""

from pathlib import Path
import shutil
from typing import Any


class FileStorageError(RuntimeError):
    pass


class FileStorage:
    def __init__(self, config: dict[str, Any]):
        base = Path(config.get("LOCAL_DB_PATH") or "instance/demo.sqlite3")
        self.base_dir = base.parent
        self.root = self.base_dir / "uploads"

    def _paper_dir(self, paper_id: str) -> Path:
        safe_id = "".join(ch for ch in str(paper_id) if ch.isalnum() or ch in "-_")
        if not safe_id:
            raise FileStorageError("Invalid paper id.")
        return self.root / safe_id

    def save(self, paper_id: str, filename: str, data: bytes) -> dict[str, Any]:
        target_dir = self._paper_dir(paper_id)
        logical_path = f"uploads/{target_dir.name}/{filename}"
        target = self._resolve(logical_path)
        if not target or target.parent != target_dir.resolve() or not filename or Path(filename).name != filename:
            raise FileStorageError("Invalid PDF filename.")
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        except OSError as exc:
            raise FileStorageError("Could not store the uploaded file on disk.") from exc
        return {"file_path": logical_path, "file_size": len(data), "storage": "local"}

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
        return path.read_bytes() if path and path.is_file() else None

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
    def delete_paper(self, paper_id: str) -> None:
        directory = self._paper_dir(paper_id)
        try:
            if directory.is_dir():
                shutil.rmtree(directory, ignore_errors=True)
        except Exception:
            pass
