import json

import pytest

from docuquery import model_registry as registry


def test_recommendation_follows_memory():
    assert registry.recommend_preset(4) == "small"
    assert registry.recommend_preset(8) == "default"
    assert registry.recommend_preset(16) == "large"
    assert registry.recommend_preset(0) == "default"


def test_models_dir_can_be_redirected(monkeypatch, tmp_path):
    monkeypatch.setenv("MODELS_DIR", str(tmp_path / "custom"))
    assert registry.models_dir() == tmp_path / "custom"
    assert registry.preset_path("small").parent == tmp_path / "custom"


def test_scan_finds_gguf_files_in_extra_folder(monkeypatch, tmp_path):
    library = tmp_path / "library"
    library.mkdir()
    model = library / "my-qwen.gguf"
    model.write_bytes(b"GGUF" + b"0" * (registry.MIN_GGUF_MB * 1024 * 1024))
    (library / "notes.txt").write_text("ignore me")
    small = library / "tiny.gguf"
    small.write_bytes(b"GGUF")

    monkeypatch.setenv("MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.setenv("EXTRA_MODEL_DIRS", str(library))

    options = {entry["label"]: entry for entry in registry.options()}
    assert "my-qwen" in options
    assert options["my-qwen"]["size_mb"] >= registry.MIN_GGUF_MB
    assert "tiny" not in options
    assert options["Qwen2.5 0.5B Instruct"]["downloaded"] is False


def test_selection_round_trip(monkeypatch, tmp_path):
    monkeypatch.setenv("MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.setenv("MODEL_SELECTION_FILE", str(tmp_path / "models" / "selected.json"))

    assert registry.read_selection() is None
    saved = registry.write_selection("preset", "small", "Qwen2.5 0.5B Instruct")
    assert saved["value"] == "small"
    assert json.loads((tmp_path / "models" / "selected.json").read_text())["value"] == "small"

    stored = registry.read_selection()
    assert stored["kind"] == "preset"
    assert registry.selected_id(stored) == "preset:small"
    assert registry.resolve_path(stored) == registry.preset_path("small")


def test_selection_rejects_unknown_values(monkeypatch, tmp_path):
    monkeypatch.setenv("MODELS_DIR", str(tmp_path / "models"))
    with pytest.raises(ValueError):
        registry.write_selection("preset", "gigantic")
    with pytest.raises(ValueError):
        registry.write_selection("file", str(tmp_path / "missing.gguf"))
    with pytest.raises(ValueError):
        registry.write_selection("cloud", "x")


def test_find_option_and_describe(monkeypatch, tmp_path):
    monkeypatch.setenv("MODELS_DIR", str(tmp_path / "models"))
    option = registry.find_option("preset:default")
    assert option["kind"] == "preset"
    assert registry.find_option("preset:nope") is None

    info = registry.describe({"OLLAMA_ENABLED": False, "LLM_BACKEND": "ollama"})
    assert info["recommended"] in registry.PRESETS
    assert info["current"]["available"] is False
    assert any(entry["recommended"] for entry in info["options"])


def test_ollama_blobs_are_offered_as_models(tmp_path, monkeypatch):
    from docuquery import model_registry

    blobs = tmp_path / "models" / "blobs"
    blobs.mkdir(parents=True)
    manifest = tmp_path / "models" / "manifests" / "registry.ollama.ai" / "library" / "qwen2.5" / "1.5b"
    manifest.parent.mkdir(parents=True)
    blob = blobs / "sha256-abc123"
    with open(blob, "wb") as handle:
        handle.truncate(200 * 1024 * 1024)
    manifest.write_text(
        '{"layers": [{"mediaType": "application/vnd.ollama.image.model",'
        ' "digest": "sha256:abc123", "size": 209715200}]}',
        encoding="utf-8",
    )
    monkeypatch.setenv("OLLAMA_MODELS", str(tmp_path / "models"))
    monkeypatch.setenv("MODELS_DIR", str(tmp_path / "empty"))

    found = model_registry.scan_ollama_models()
    assert found and found[0]["source"] == "Ollama"
    assert found[0]["label"].startswith("qwen2.5:1.5b")
    assert found[0]["path"].endswith("sha256-abc123")


class _FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload
        self._pos = 0
        self.headers = {"Content-Length": str(len(payload))}

    def read(self, size: int = -1) -> bytes:
        if self._pos >= len(self._payload):
            return b""
        end = len(self._payload) if size < 0 else self._pos + size
        chunk = self._payload[self._pos:end]
        self._pos = end
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_download_preset_writes_the_file(tmp_path, monkeypatch):
    from docuquery import model_registry

    monkeypatch.setenv("MODELS_DIR", str(tmp_path))
    monkeypatch.setattr(model_registry, "MIN_GGUF_MB", 1)
    payload = b"G" * (2 * 1024 * 1024)

    path = model_registry.download_preset(
        "small", opener=lambda request, timeout=60: _FakeResponse(payload))
    assert path.exists() and path.stat().st_size == len(payload)
    assert model_registry.download_status()["received"] > 0


def test_download_preset_falls_back_to_second_url(tmp_path, monkeypatch):
    from docuquery import model_registry

    monkeypatch.setenv("MODELS_DIR", str(tmp_path))
    monkeypatch.setattr(model_registry, "MIN_GGUF_MB", 1)
    calls = {"count": 0}

    def opener(request, timeout=60):
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError("primary mirror down")
        return _FakeResponse(b"G" * (2 * 1024 * 1024))

    path = model_registry.download_preset("small", opener=opener)
    assert calls["count"] == 2
    assert path.exists()


def test_start_download_rejects_unknown_preset():
    from docuquery import model_registry

    with pytest.raises(ValueError):
        model_registry.start_download("gigantic")


def test_display_label_strips_paths():
    from docuquery import model_registry

    assert model_registry._display_label("C:\\Users\\Vishal\\Downloads\\qwen.gguf") == "qwen"
    assert model_registry._display_label("Qwen2.5 1.5B Instruct") == "Qwen2.5 1.5B Instruct"
    assert model_registry._display_label("") == ""


class _HeaderResponse:
    def __init__(self, payload: bytes, headers: dict[str, str] | None = None):
        self._payload = payload
        self._pos = 0
        self.headers = {"Content-Length": str(len(payload))}
        self.headers.update(headers or {})

    def read(self, size: int = -1) -> bytes:
        if self._pos >= len(self._payload):
            return b""
        end = len(self._payload) if size < 0 else self._pos + size
        chunk = self._payload[self._pos:end]
        self._pos = end
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_link_download_saves_gguf_and_selects_it(tmp_path, monkeypatch):
    from docuquery import model_registry

    monkeypatch.setenv("MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.setenv("MODEL_SELECTION_FILE", str(tmp_path / "models" / "selected.json"))
    payload = b"GGUF" + b"\0" * (2 * 1024 * 1024)

    path = model_registry.download_custom(
        "https://huggingface.co/acme/tiny/resolve/main/Tiny-Q4_K_M.gguf",
        opener=lambda request, timeout=60: _HeaderResponse(payload),
    )
    assert path.name == "Tiny-Q4_K_M.gguf"
    assert path.parent == tmp_path / "models"
    assert path.stat().st_size == len(payload)
    assert not list((tmp_path / "models").glob("*.part"))


def test_link_download_uses_name_from_the_server(tmp_path, monkeypatch):
    from docuquery import model_registry

    monkeypatch.setenv("MODELS_DIR", str(tmp_path))
    path = model_registry.download_custom(
        "https://example.test/download?id=7",
        opener=lambda request, timeout=60: _HeaderResponse(
            b"GGUF" + b"\0" * (1024 * 1024),
            {"Content-Disposition": 'attachment; filename="My Model.gguf"'},
        ),
    )
    assert path.name == "My Model.gguf"


def test_link_download_rejects_html_and_missing_scheme(tmp_path, monkeypatch):
    from docuquery import model_registry

    monkeypatch.setenv("MODELS_DIR", str(tmp_path))
    with pytest.raises(OSError) as html_error:
        model_registry.download_custom(
            "https://example.test/page.gguf",
            opener=lambda request, timeout=60: _HeaderResponse(b"<html>not a model</html>"),
        )
    assert "did not return a GGUF file" in str(html_error.value)
    assert not list(tmp_path.glob("*.gguf")), "a rejected download must leave nothing behind"

    for bad in ("ftp://example.test/m.gguf", "file:///etc/passwd", "example.test/m.gguf", ""):
        with pytest.raises(ValueError):
            model_registry.download_custom(bad, opener=lambda request, timeout=60: None)


def test_link_download_keeps_the_file_inside_the_models_folder(tmp_path, monkeypatch):
    from docuquery import model_registry

    monkeypatch.setenv("MODELS_DIR", str(tmp_path / "models"))
    path = model_registry.download_custom(
        "https://example.test/../../evil.gguf",
        opener=lambda request, timeout=60: _HeaderResponse(b"GGUF" + b"\0" * (1024 * 1024)),
    )
    assert path.parent == tmp_path / "models"


def test_describe_reports_folder_and_free_space(tmp_path, monkeypatch):
    from docuquery import model_registry

    monkeypatch.setenv("MODELS_DIR", str(tmp_path / "models"))
    info = model_registry.describe({"OLLAMA_ENABLED": False, "LLM_BACKEND": "ollama"})
    assert info["models_dir"] == str(tmp_path / "models")
    assert info["free_space_mb"] > 0


def _raise_http(code: int):
    import urllib.error

    def opener(request, timeout=60):
        raise urllib.error.HTTPError("https://huggingface.co/x/y", code, "err", {}, None)

    return opener


def test_gated_model_link_gets_a_licence_message(tmp_path, monkeypatch):
    """google/gemma-2-2b style links need a licence acceptance and a token."""
    from docuquery import model_registry

    monkeypatch.setenv("MODELS_DIR", str(tmp_path))
    monkeypatch.delenv("HF_TOKEN", raising=False)
    with pytest.raises(OSError) as error:
        model_registry.download_custom(
            "https://huggingface.co/google/gemma-2-2b/resolve/main/model.gguf",
            opener=_raise_http(401),
        )
    text = str(error.value)
    assert "gated" in text and "HF_TOKEN" in text
    assert not list(tmp_path.glob("*.gguf"))


def test_missing_link_and_other_failures_are_explained(tmp_path, monkeypatch):
    from docuquery import model_registry

    monkeypatch.setenv("MODELS_DIR", str(tmp_path))
    with pytest.raises(OSError) as not_found:
        model_registry.download_custom("https://example.test/m.gguf", opener=_raise_http(404))
    assert "404" in str(not_found.value)


def test_original_safetensors_link_is_refused_before_downloading(tmp_path, monkeypatch):
    from docuquery import model_registry

    monkeypatch.setenv("MODELS_DIR", str(tmp_path))
    for url in (
        "https://huggingface.co/google/gemma-2-2b/resolve/main/model.safetensors",
        "https://huggingface.co/x/y/resolve/main/pytorch_model.bin",
    ):
        with pytest.raises(ValueError) as error:
            model_registry.download_custom(url, opener=lambda request, timeout=60: None)
        assert "GGUF" in str(error.value)
    with pytest.raises(ValueError):
        model_registry.start_custom_download(
            "https://huggingface.co/google/gemma-2-2b/resolve/main/model.safetensors"
        )


def test_hf_token_is_sent_only_to_huggingface(tmp_path, monkeypatch):
    from docuquery import model_registry

    monkeypatch.setenv("MODELS_DIR", str(tmp_path))
    monkeypatch.setenv("HF_TOKEN", "hf_test_token")
    seen: list[dict[str, str]] = []

    def opener(request, timeout=60):
        seen.append({key.lower(): value for key, value in request.header_items()})
        return _HeaderResponse(b"GGUF" + b"\0" * (1024 * 1024))

    model_registry.download_custom(
        "https://huggingface.co/bartowski/gemma-2-2b-it-GGUF/resolve/main/gemma-2-2b-it-Q4_K_M.gguf",
        opener=opener,
    )
    model_registry.download_custom("https://example.test/other.gguf", opener=opener)
    assert seen[0].get("authorization") == "Bearer hf_test_token"
    assert "authorization" not in seen[1]
