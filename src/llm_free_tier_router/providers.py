"""Provider HTTP adapters and normalized responses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx


@dataclass(frozen=True)
class Completion:
    text: str
    provider: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class ProviderError(Exception):
    def __init__(self, provider: str, message: str, *, code: str = "provider_error", retryable: bool = False):
        super().__init__(message)
        self.provider = provider
        self.code = code
        self.retryable = retryable


class ProviderClient:
    def __init__(self, name: str, api_key: str, base_url: str, timeout: float, *,
                 site_url: str | None = None, app_name: str | None = None,
                 http_client: httpx.Client | None = None):
        self.name = name
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.site_url = site_url
        self.app_name = app_name
        self.http_client = http_client

    def complete(self, messages: list[dict[str, str]], model: str) -> Completion:
        try:
            response = self._send(messages, model)
        except httpx.TimeoutException as exc:
            raise ProviderError(self.name, "Request timed out", code="timeout", retryable=True) from exc
        except httpx.TransportError as exc:
            raise ProviderError(self.name, "Network transport failed", code="network_error", retryable=True) from exc

        if response.is_error:
            self._raise_response_error(response)
        try:
            data = response.json()
            return self._normalize(data, model)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError(self.name, "Provider returned an unexpected response", code="invalid_response") from exc

    def _send(self, messages: list[dict[str, str]], model: str) -> httpx.Response:
        headers = {"Content-Type": "application/json"}
        if self.name == "anthropic":
            headers.update({"x-api-key": self.api_key, "anthropic-version": "2023-06-01"})
            system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
            body: dict[str, Any] = {
                "model": model, "max_tokens": 1024,
                "messages": [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"],
            }
            if system:
                body["system"] = system
            url = f"{self.base_url}/messages"
            return self._post(url, headers, body)

        if self.name == "google":
            contents = []
            system_parts = []
            for message in messages:
                if message["role"] == "system":
                    system_parts.append({"text": message["content"]})
                else:
                    role = "model" if message["role"] == "assistant" else "user"
                    contents.append({"role": role, "parts": [{"text": message["content"]}]})
            body = {"contents": contents, "generationConfig": {"maxOutputTokens": 1024}}
            if system_parts:
                body["systemInstruction"] = {"parts": system_parts}
            url = f"{self.base_url}/models/{quote(model, safe='')}:generateContent"
            return self._post(url, headers, body, params={"key": self.api_key})

        headers["Authorization"] = f"Bearer {self.api_key}"
        if self.name == "openrouter":
            if self.site_url:
                headers["HTTP-Referer"] = self.site_url
            if self.app_name:
                headers["X-Title"] = self.app_name
        body = {"model": model, "messages": messages, "max_tokens": 1024}
        return self._post(f"{self.base_url}/chat/completions", headers, body)

    def _post(self, url: str, headers: dict[str, str], body: dict[str, Any],
              params: dict[str, str] | None = None) -> httpx.Response:
        if self.http_client:
            return self.http_client.post(url, headers=headers, json=body, params=params, timeout=self.timeout)
        return httpx.post(url, headers=headers, json=body, params=params, timeout=self.timeout)

    def _raise_response_error(self, response: httpx.Response) -> None:
        status = response.status_code
        code = "http_error"
        message = f"HTTP {status}"
        try:
            payload = response.json()
            error = payload.get("error", payload)
            if isinstance(error, dict):
                provider_code = str(error.get("code", ""))
                provider_message = str(error.get("message", ""))
                if provider_code:
                    code = provider_code
                if provider_message:
                    message = provider_message[:300]
        except (ValueError, AttributeError):
            pass
        lower = f"{code} {message}".lower()
        quota = any(word in lower for word in ("insufficient_quota", "quota", "rate_limit", "rate limit"))
        retryable = quota or status in (401, 403, 408, 429) or status >= 500
        if quota:
            code = "quota_or_rate_limit"
        raise ProviderError(self.name, message, code=code, retryable=retryable)

    def _normalize(self, data: dict[str, Any], requested_model: str) -> Completion:
        if self.name == "anthropic":
            text = "".join(part.get("text", "") for part in data["content"] if part.get("type") == "text")
            usage = data.get("usage", {})
            return Completion(text, self.name, data.get("model", requested_model), usage.get("input_tokens"), usage.get("output_tokens"))
        if self.name == "google":
            candidate = data["candidates"][0]
            text = "".join(part.get("text", "") for part in candidate["content"]["parts"])
            usage = data.get("usageMetadata", {})
            return Completion(text, self.name, requested_model, usage.get("promptTokenCount"), usage.get("candidatesTokenCount"))
        choice = data["choices"][0]
        content = choice["message"].get("content", "")
        if isinstance(content, list):
            text = "".join(item.get("text", "") for item in content if isinstance(item, dict))
        else:
            text = str(content)
        usage = data.get("usage", {})
        return Completion(text, self.name, data.get("model", requested_model), usage.get("prompt_tokens"), usage.get("completion_tokens"))
