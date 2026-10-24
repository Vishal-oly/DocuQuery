from docuquery.storage import FileStorage, FileStorageError


class FakeBucket:
    def __init__(self):
        self.objects = {}

    def upload(self, key, data):
        self.objects[key] = bytes(data)

    def download(self, key):
        if key not in self.objects:
            raise KeyError(key)
        return self.objects[key]

    def remove(self, keys):
        for key in keys:
            self.objects.pop(key, None)

    def list(self, folder):
        prefix = folder + "/"
        names = [k[len(prefix):] for k in self.objects if k.startswith(prefix)]
        return [{"name": n} for n in names if "/" not in n]


class FakeStorage:
    def __init__(self):
        self.bucket = FakeBucket()

    def from_(self, name):
        return self.bucket


class FakeRepo:
    def __init__(self):
        self.storage = FakeStorage()


def make_storage(tmp_path, **config):
    conf = {"LOCAL_DB_PATH": str(tmp_path / "db.sqlite3"), **config}
    client = FakeRepo() if config.pop("with_client", True) else None
    return FileStorage(conf, client), client


def test_local_round_trip_without_cloud(tmp_path):
    storage, _ = make_storage(tmp_path, with_client=False)
    info = storage.save("abc-123", "paper.pdf", b"%PDF-data")
    assert info["storage"] == "local"
    assert storage.exists(info["file_path"])
    assert storage.read(info["file_path"]) == b"%PDF-data"
    storage.delete(info["file_path"])
    assert not storage.exists(info["file_path"])


def test_cloud_copy_is_uploaded_and_read_falls_back(tmp_path):
    storage, client = make_storage(tmp_path)
    info = storage.save("abc-123", "paper.pdf", b"%PDF-data")
    assert info["storage"] == "local+supabase"
    assert "abc-123/paper.pdf" in client.storage.bucket.objects

    # Simulate an ephemeral filesystem: local file disappears.
    storage.delete(info["file_path"])  # deletes local + cloud; re-upload cloud only
    client.storage.bucket.objects["abc-123/paper.pdf"] = b"%PDF-data"
    assert storage.read(info["file_path"]) == b"%PDF-data"
    assert storage.exists(info["file_path"])


def test_cloud_only_mode_skips_local_disk(tmp_path):
    storage, client = make_storage(tmp_path, SUPABASE_STORAGE_PRIMARY=True)
    info = storage.save("abc-123", "paper.pdf", b"%PDF-data")
    assert info["storage"] == "supabase"
    assert storage.read(info["file_path"]) == b"%PDF-data"
    storage.delete_paper("abc-123")
    assert storage.read(info["file_path"]) is None


def test_save_fails_only_when_no_store_available(tmp_path):
    storage, _ = make_storage(tmp_path, SUPABASE_STORAGE_PRIMARY=True, with_client=False)
    try:
        storage.save("abc-123", "paper.pdf", b"data")
    except FileStorageError:
        pass  # expected: no disk (cloud_only) and no client
    else:
        raise AssertionError("expected FileStorageError")
