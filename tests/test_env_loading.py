"""The app must read the project .env file even without python-dotenv."""

import os

from docuquery.config import _load_env_file


def test_env_fallback_parses_bom_quotes_and_comments(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_bytes(
        b"\xef\xbb\xbfDOCUQUERY_TEST_ENV=\"fallback_test\"\n"
        b"# comment line\n"
        b"MAX_UPLOAD_MB=50\n"
    )
    monkeypatch.delenv("DOCUQUERY_TEST_ENV", raising=False)
    monkeypatch.delenv("MAX_UPLOAD_MB", raising=False)

    _load_env_file(env_path)

    assert os.environ["DOCUQUERY_TEST_ENV"] == "fallback_test"
    assert os.environ["MAX_UPLOAD_MB"] == "50"


def test_env_fallback_never_overrides_shell_environment(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text('DOCUQUERY_TEST_ENV="from_file"\n')
    monkeypatch.setenv("DOCUQUERY_TEST_ENV", "from_shell")

    _load_env_file(env_path)

    assert os.environ["DOCUQUERY_TEST_ENV"] == "from_shell"


def test_env_fallback_missing_file_is_silent_noop(tmp_path):
    _load_env_file(tmp_path / "does-not-exist.env")
