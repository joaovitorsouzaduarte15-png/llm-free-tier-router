from __future__ import annotations

from pathlib import Path

from llm_free_tier_router.config import ProviderConfig, Settings
from llm_free_tier_router.providers import Completion, ProviderError
from llm_free_tier_router.router import AllProvidersFailed, Router
from llm_free_tier_router.storage import UsageStore


class FakeClient:
    def __init__(self, result: Completion | ProviderError):
        self.result = result
        self.calls = 0

    def complete(self, messages: list[dict[str, str]], model: str) -> Completion:
        self.calls += 1
        if isinstance(self.result, ProviderError):
            raise self.result
        return self.result


def make_settings(path: Path) -> Settings:
    return Settings((
        ProviderConfig("openai", "key1", "model-a", "https://example.test/v1"),
        ProviderConfig("groq", "key2", "model-b", "https://example.test/v1"),
    ), 5, path)


def test_router_falls_back_and_records_only_usage(tmp_path: Path) -> None:
    first = FakeClient(ProviderError("openai", "rate limited", code="quota_or_rate_limit", retryable=True))
    second = FakeClient(Completion("ok", "groq", "model-b", 4, 2))
    store = UsageStore(tmp_path / "usage.sqlite3")
    router = Router(make_settings(tmp_path / "usage.sqlite3"), store, {"openai": first, "groq": second})

    result = router.complete([{"role": "user", "content": "private prompt"}])

    assert result.text == "ok"
    assert first.calls == second.calls == 1
    assert store.month_stats("openai")[0:2] == (1, 0)
    assert store.month_stats("groq") == (1, 1, 4, 2)
    database = (tmp_path / "usage.sqlite3").read_bytes()
    assert b"private prompt" not in database


def test_non_retryable_error_stops_fallback(tmp_path: Path) -> None:
    first = FakeClient(ProviderError("openai", "bad request", retryable=False))
    second = FakeClient(Completion("ok", "groq", "model-b"))
    router = Router(make_settings(tmp_path / "usage.sqlite3"), UsageStore(tmp_path / "usage.sqlite3"),
                    {"openai": first, "groq": second})

    try:
        router.complete([{"role": "user", "content": "hello"}])
    except AllProvidersFailed:
        pass
    else:
        raise AssertionError("Expected AllProvidersFailed")
    assert second.calls == 0
