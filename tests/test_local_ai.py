import socket
import zipfile


import local_ai


def test_model_ready_rejects_small_or_foreign_files(tmp_path):
    tiny = tmp_path / "tiny.gguf"
    tiny.write_bytes(b"GGUF")
    assert not local_ai.model_ready(tiny)

    fake = tmp_path / "fake.gguf"
    fake.write_bytes(b"NOTG" + b"0" * (local_ai.MIN_MODEL_BYTES + 1))
    assert not local_ai.model_ready(fake)


def test_extract_runtime_keeps_files_inside_target(tmp_path):
    archive = tmp_path / "llama.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("llama-server.exe", "binary")
        bundle.writestr("ggml.dll", "binary")
        bundle.writestr("../escape.txt", "nope")

    target = tmp_path / "runtime"
    written = local_ai.extract_runtime(archive, target)

    assert written == 2
    assert (target / "llama-server.exe").is_file()
    assert not (tmp_path / "escape.txt").exists()
    assert local_ai.find_server_exe(target) == target / "llama-server.exe"


def test_find_server_exe_in_nested_folder(tmp_path):
    nested = tmp_path / "bin" / "llama-server.exe"
    nested.parent.mkdir(parents=True)
    nested.write_bytes(b"exe")
    assert local_ai.find_server_exe(tmp_path) == nested


def test_free_port_returns_a_bindable_port():
    port = local_ai.free_port(0)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))


def test_write_env_file_never_overwrites_user_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(local_ai, "ROOT", tmp_path)
    local_ai.write_env_file(8080)
    content = (tmp_path / ".env").read_text()
    assert "OPENAI_BASE_URL=http://127.0.0.1:8080/v1" in content

    (tmp_path / ".env").write_text("OPENAI_MODEL=mine\n")
    local_ai.write_env_file(9090)
    assert (tmp_path / ".env").read_text() == "OPENAI_MODEL=mine\n"


def test_backend_config_reports_status_without_network(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "ollama")
    monkeypatch.setenv("OLLAMA_ENABLED", "false")
    status = local_ai.backend_config()
    assert status["backend"] == "ollama"
    assert status["available"] is False


def test_server_command_shape(tmp_path):
    exe = tmp_path / "llama-server.exe"
    model = tmp_path / "m.gguf"
    command = local_ai.server_command(exe, model, 8080, threads=4)
    assert command[:3] == [str(exe), "-m", str(model)]
    assert "--port" in command and "8080" in command
    assert "-ngl" not in command
    assert local_ai.server_command(exe, model, 8080, gpu=True, threads=4)[-2:] == ["-ngl", "99"]


def test_model_presets_have_distinct_files():
    names = {local_ai.preset_path(p).name for p in local_ai.PRESETS}
    assert len(names) == len(local_ai.PRESETS)
    assert "0.5b" in local_ai.preset_path("small").name
    assert "3b" in local_ai.preset_path("large").name


def test_model_url_override_wins(monkeypatch):
    monkeypatch.setenv("LOCAL_AI_MODEL_URL", "http://example.invalid/mine.gguf")
    assert local_ai.configured_model_urls("small") == ("http://example.invalid/mine.gguf",)


def test_choose_model_prefers_flags_then_saved_choice(monkeypatch, tmp_path):
    import argparse

    monkeypatch.setenv("MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.setenv("MODEL_SELECTION_FILE", str(tmp_path / "models" / "selected.json"))

    choice, origin = local_ai.choose_model(argparse.Namespace(model="small", model_path=None))
    assert choice == {"kind": "preset", "value": "small"}
    assert origin == "command line"

    model = tmp_path / "extra.gguf"
    choice, _ = local_ai.choose_model(argparse.Namespace(model=None, model_path=str(model)))
    assert choice == {"kind": "file", "value": str(model)}

    local_ai.registry.write_selection("preset", "large", "Qwen2.5 3B Instruct")
    choice, origin = local_ai.choose_model(argparse.Namespace(model=None, model_path=None))
    assert choice["kind"] == "preset" and choice["value"] == "large"
    assert origin == "your saved choice"

    monkeypatch.setenv("LOCAL_AI_PRESET", "small")
    choice, origin = local_ai.choose_model(argparse.Namespace(model=None, model_path=None))
    assert choice == {"kind": "preset", "value": "small"}
    assert origin == "LOCAL_AI_PRESET"
    monkeypatch.delenv("LOCAL_AI_PRESET")

    (tmp_path / "models" / "selected.json").unlink()
    choice, origin = local_ai.choose_model(argparse.Namespace(model=None, model_path=None))
    assert origin == "automatic pick"
    assert choice["value"] in local_ai.PRESETS


def test_resolve_choice_accepts_downloaded_file_and_rejects_missing(monkeypatch, tmp_path):
    real = tmp_path / "real.gguf"
    real.write_bytes(b"GGUF" + b"0" * (local_ai.MIN_MODEL_BYTES + 1))
    assert local_ai.resolve_choice({"kind": "file", "value": str(real)}) == real
    assert local_ai.resolve_choice({"kind": "file", "value": str(tmp_path / "nope.gguf")}) is None
    assert local_ai.resolve_choice(None) is None
