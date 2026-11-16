from __future__ import annotations

from pathlib import Path

from llm_free_tier_router.config import Settings


def test_single_unified_key_enables_openrouter(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LLM_ROUTER_API_KEY", "router-secret")
    monkeypatch.setenv("LLM_ROUTER_PROVIDERS", "openrouter,groq")
    monkeypatch.setenv("LLM_ROUTER_DB_PATH", str(tmp_path / "usage.sqlite3"))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    settings = Settings.from_env(load_env_file=False)

    assert [item.name for item in settings.providers] == ["openrouter"]
    assert settings.providers[0].api_key == "router-secret"
