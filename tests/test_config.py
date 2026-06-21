import pytest

from dawg_mcp.config import DEFAULT_BASE_URL, Config


def test_from_env_requires_api_key(monkeypatch):
    monkeypatch.delenv("DAWG_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="DAWG_API_KEY"):
        Config.from_env()


def test_from_env_defaults(monkeypatch):
    monkeypatch.setenv("DAWG_API_KEY", "abc")
    for var in (
        "DAWG_BASE_URL", "DAWG_PROVISION_TIMEOUT", "DAWG_POLL_INTERVAL",
        "DAWG_MAX_SESSIONS", "DAWG_SNAPSHOT_MAX_CHARS",
    ):
        monkeypatch.delenv(var, raising=False)
    cfg = Config.from_env()
    assert cfg.api_key == "abc"
    assert cfg.base_url == DEFAULT_BASE_URL
    assert cfg.max_sessions == 4
    assert cfg.snapshot_max_chars == 60000


def test_from_env_overrides(monkeypatch):
    monkeypatch.setenv("DAWG_API_KEY", "abc")
    monkeypatch.setenv("DAWG_BASE_URL", "https://staging.example.com/")
    monkeypatch.setenv("DAWG_MAX_SESSIONS", "2")
    cfg = Config.from_env()
    assert cfg.base_url == "https://staging.example.com"  # trailing slash stripped
    assert cfg.max_sessions == 2
