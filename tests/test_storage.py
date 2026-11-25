import pytest

from docuquery.storage import FileStorage, FileStorageError


def test_local_round_trip_and_delete(tmp_path):
    config = {"LOCAL_DB_PATH": str(tmp_path / "db.sqlite3")}
    info = FileStorage(config).save("abc-123", "paper.pdf", b"%PDF-data")
    assert info["storage"] == "local"
    storage = FileStorage(config)
    assert storage.exists(info["file_path"])
    assert storage.read(info["file_path"]) == b"%PDF-data"
    storage.delete_paper("abc-123")
    assert not storage.exists(info["file_path"])


def test_storage_rejects_path_traversal(tmp_path):
    storage = FileStorage({"LOCAL_DB_PATH": str(tmp_path / "db.sqlite3")})
    with pytest.raises(FileStorageError):
        storage.save("abc-123", "../paper.pdf", b"data")
    assert storage.read("../paper.pdf") is None
