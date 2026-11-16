"""Environment-based application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROVIDER_DEFAULTS: dict[str, tuple[str, str]] = {
    "openrouter": ("openrouter/auto", "https://openrouter.ai/api/v1"),
    "groq": ("llama-3.3-70b-versatile", "https://api.groq.com/openai/v1"),
    "google": ("gemini-2.0-flash", "https://generativelanguage.googleapis.com/v1beta"),
    "anthropic": ("claude-3-5-haiku-latest", "https://api.anthropic.com/v1"),
    "openai": ("gpt-4o-mini", "https://api.openai.com/v1"),
}
DEFAULT_ORDER = ("openrouter", "groq", "google", "anthropic", "openai")


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    api_key: str
    model: str
    base_url: str
    monthly_limit: int | None = None


@dataclass(frozen=True)
class Settings:
    providers: tuple[ProviderConfig, ...]
    timeout: float
    db_path: Path
    openrouter_site_url: str | None = None
    openrouter_app_name: str | None = None

    @classmethod
    def from_env(cls, *, load_env_file: bool = True) -> "Settings":
        if load_env_file:
            load_dotenv()
        raw_order = os.getenv("LLM_ROUTER_PROVIDERS", ",".join(DEFAULT_ORDER))
        order = tuple(dict.fromkeys(item.strip().lower() for item in raw_order.split(",") if item.strip()))
        unknown = set(order).difference(PROVIDER_DEFAULTS)
        if unknown:
            raise ValueError(f"Unknown provider(s): {', '.join(sorted(unknown))}")

        configs: list[ProviderConfig] = []
        for name in order:
            model_default, base_url = PROVIDER_DEFAULTS[name]
            key_names = {
                "openrouter": ("OPENROUTER_API_KEY", "LLM_ROUTER_API_KEY"),
                "openai": ("OPENAI_API_KEY",),
                "anthropic": ("ANTHROPIC_API_KEY",),
                "google": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
                "groq": ("GROQ_API_KEY",),
            }[name]
            key = next((os.getenv(key_name, "").strip() for key_name in key_names if os.getenv(key_name, "").strip()), "")
            if not key:
                continue
            model = os.getenv(f"LLM_ROUTER_MODEL_{name.upper()}", model_default).strip()
            limit_text = os.getenv(f"LLM_ROUTER_MONTHLY_LIMIT_{name.upper()}", "").strip()
            try:
                limit = int(limit_text) if limit_text else None
                if limit is not None and limit < 0:
                    raise ValueError
            except ValueError as exc:
                raise ValueError(f"LLM_ROUTER_MONTHLY_LIMIT_{name.upper()} must be a non-negative integer") from exc
            configs.append(ProviderConfig(name, key, model, base_url, limit))

        try:
            timeout = float(os.getenv("LLM_ROUTER_TIMEOUT", "45"))
            if timeout <= 0:
                raise ValueError
        except ValueError as exc:
            raise ValueError("LLM_ROUTER_TIMEOUT must be a positive number") from exc
        default_db = Path.home() / ".local" / "share" / "llm-free-tier-router" / "usage.sqlite3"
        db_path = Path(os.getenv("LLM_ROUTER_DB_PATH", str(default_db))).expanduser()
        return cls(
            tuple(configs),
            timeout,
            db_path,
            os.getenv("LLM_ROUTER_OPENROUTER_SITE_URL") or None,
            os.getenv("LLM_ROUTER_OPENROUTER_APP_NAME") or None,
        )
