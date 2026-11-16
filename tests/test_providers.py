from __future__ import annotations

import httpx

from llm_free_tier_router.providers import ProviderClient, ProviderError


def test_openai_compatible_response_normalization() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        assert request.headers["authorization"] == "Bearer secret"
        return httpx.Response(200, json={
            "model": "actual-model",
            "choices": [{"message": {"content": "Hello"}}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 3},
        })

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = ProviderClient("groq", "secret", "https://example.test/v1", 5, http_client=client).complete(
            [{"role": "user", "content": "Hi"}], "test-model"
        )
    assert (result.text, result.model, result.prompt_tokens, result.completion_tokens) == ("Hello", "actual-model", 2, 3)


def test_quota_errors_are_retryable_and_do_not_expose_key() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"code": "insufficient_quota", "message": "No quota"}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = ProviderClient("openai", "top-secret", "https://example.test/v1", 5, http_client=client)
        try:
            provider.complete([{"role": "user", "content": "Hi"}], "model")
        except ProviderError as error:
            assert error.retryable
            assert error.code == "quota_or_rate_limit"
            assert "top-secret" not in str(error)
        else:
            raise AssertionError("Expected ProviderError")
