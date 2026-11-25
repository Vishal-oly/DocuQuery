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
