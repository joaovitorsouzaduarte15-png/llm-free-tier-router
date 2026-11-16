"""Ordered, quota-aware fallback router."""

from __future__ import annotations

from dataclasses import dataclass

from .config import ProviderConfig, Settings
from .providers import Completion, ProviderClient, ProviderError
from .storage import UsageStore


class AllProvidersFailed(RuntimeError):
    def __init__(self, failures: list[str]):
        self.failures = failures
        super().__init__("All eligible providers failed: " + "; ".join(failures))


@dataclass
class Router:
    settings: Settings
    store: UsageStore
    clients: dict[str, ProviderClient] | None = None

    def _client(self, config: ProviderConfig) -> ProviderClient:
        if self.clients is not None and config.name in self.clients:
            return self.clients[config.name]
        return ProviderClient(
            config.name, config.api_key, config.base_url, self.settings.timeout,
            site_url=self.settings.openrouter_site_url,
            app_name=self.settings.openrouter_app_name,
        )

    def complete(self, messages: list[dict[str, str]], *, provider: str | None = None,
                 model: str | None = None) -> Completion:
        configs = list(self.settings.providers)
        if provider:
            configs = [config for config in configs if config.name == provider]
            if not configs:
                raise ValueError(f"Provider '{provider}' is not configured or has no API key")
        if not configs:
            raise ValueError("No providers are configured. Add an API key to .env or the environment.")

        failures: list[str] = []
        for config in configs:
            calls, _, _, _ = self.store.month_stats(config.name)
            if config.monthly_limit is not None and calls >= config.monthly_limit:
                failures.append(f"{config.name}: local monthly request cap reached")
                continue
            selected_model = model or config.model
            try:
                result = self._client(config).complete(messages, selected_model)
            except ProviderError as exc:
                self.store.record(config.name, selected_model, success=False, error_code=exc.code)
                failures.append(f"{config.name}: {exc.code} ({exc})")
                if exc.retryable:
                    continue
                break
            self.store.record(config.name, result.model, success=True,
                              prompt_tokens=result.prompt_tokens, completion_tokens=result.completion_tokens)
            return result
        raise AllProvidersFailed(failures)
