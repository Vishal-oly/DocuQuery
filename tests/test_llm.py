import json
from urllib.error import HTTPError, URLError

import pytest

from docuquery import llm


def test_local_chat_and_summary(monkeypatch):
    def request(config, path, timeout, payload):
        assert path == "/api/chat"
        assert payload["model"] == "qwen2.5:1.5b"
        assert payload["stream"] is False
        assert "[p. 2]" in payload["messages"][-1]["content"]
        content = "Evidence [p. 2]."
        if payload.get("format") == "json":
            content = json.dumps({"overall_summary": content})
        return {"message": {"content": content}}

    monkeypatch.setattr(llm, "_request", request)
    assert llm.generate_structured_summary("Text [p. 2]", {})["overall_summary"] == "Evidence [p. 2]."
    assert llm.answer_from_context("What?", "Text [p. 2]", {}) == "Evidence [p. 2]."


@pytest.mark.parametrize(("failure", "message"), [
    (HTTPError("http://127.0.0.1", 404, "missing", {}, None), "ollama pull"),
    (URLError("connection refused"), "start.bat"),
    (ValueError("bad JSON"), "invalid response"),
])
def test_ollama_errors(monkeypatch, failure, message):
    def request(*args):
        raise failure

    monkeypatch.setattr(llm, "_request", request)
    with pytest.raises(llm.LLMError, match=message):
        llm.answer_from_context("What?", "Text", {})
    assert not llm.ollama_available({})


def test_model_readiness_requires_installed_tag(monkeypatch):
    monkeypatch.setattr(llm, "_request", lambda *args: {"models": [{"name": "qwen2.5:1.5b"}]})
    assert llm.ollama_available({})
    assert not llm.ollama_available({"OLLAMA_MODEL": "qwen2.5:3b"})
    assert not llm.ollama_available({"OLLAMA_ENABLED": False})


def test_openai_backend_used_when_ollama_is_off(monkeypatch):
    calls = []

    def http(url, payload=None, timeout=120, headers=None):
        calls.append((url, payload, headers))
        if payload is None:
            return {"data": [{"id": "lmstudio-community/qwen2.5-1.5b-instruct"}]}
        return {"choices": [{"message": {"content": "Answer [p. 3]."}}]}

    monkeypatch.setattr(llm, "_http_json", http)
    config = {"OLLAMA_ENABLED": False, "LLM_BACKEND": "auto"}
    assert llm.answer_from_context("Q?", "Text [p. 3]", config) == "Answer [p. 3]."
    assert calls[-1][0] == "http://127.0.0.1:1234/v1/chat/completions"
    assert calls[-1][1]["model"] == "lmstudio-community/qwen2.5-1.5b-instruct"
    assert llm.model_status(config)["backend"] == "openai"


def test_openai_summary_requests_json_and_uses_env_model(monkeypatch):
    sent = {}

    def http(url, payload=None, timeout=120, headers=None):
        if payload is None:
            return {"data": [{"id": "other-model"}]}
        sent.update(payload, url=url)
        return {"choices": [{"message": {"content": '{"overall_summary": "Short [p. 1]"}'}}]}

    monkeypatch.setattr(llm, "_http_json", http)
    summary = llm.generate_structured_summary(
        "Text [p. 1]", {"LLM_BACKEND": "openai", "OPENAI_MODEL": "my-model"})
    assert summary["overall_summary"] == "Short [p. 1]"
    assert sent["response_format"] == {"type": "json_object"}
    assert sent["model"] == "my-model"


def test_explicit_ollama_backend_never_probes_openai(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("no HTTP expected")

    monkeypatch.setattr(llm, "_http_json", boom)
    assert llm._select_backend({"LLM_BACKEND": "ollama"}) == "ollama"


def test_unreachable_local_server_explains_what_to_start(monkeypatch):
    def http(*args, **kwargs):
        raise URLError("connection refused")

    monkeypatch.setattr(llm, "_http_json", http)
    with pytest.raises(llm.LLMError, match="local model server"):
        llm.answer_from_context("Q", "ctx", {"LLM_BACKEND": "openai", "OPENAI_MODEL": "m"})
    status = llm.model_status({"LLM_BACKEND": "openai"})
    assert status["backend"] == "openai"
    assert status["available"] is False


def test_app_finds_builtin_server_on_port_8080(monkeypatch):
    def http(url, payload=None, timeout=120, headers=None):
        if url.startswith("http://127.0.0.1:8080/v1/models"):
            return {"data": [{"id": "qwen2.5-1.5b-instruct"}]}
        raise URLError("nothing there")

    monkeypatch.setattr(llm, "_http_json", http)
    assert llm.openai_available({"LLM_BACKEND": "openai"})
    status = llm.model_status({"LLM_BACKEND": "openai"})
    assert status["model"] == "qwen2.5-1.5b-instruct"
    assert status["base_url"] == "http://127.0.0.1:8080/v1"
