# LLM Free Tier Router

A privacy-first Python CLI for sending prompts to OpenAI, Anthropic, Google Gemini, Groq, and OpenRouter. It tries providers in order and automatically falls back when a provider is rate-limited, out of quota, unavailable, or rejects its credentials.

> **Reality check on API keys and quotas:** each provider normally issues its own API key. For a genuinely single-key setup, use an OpenRouter key (`LLM_ROUTER_API_KEY`) and route through OpenRouter. Direct provider access requires that provider's own key. Most providers do not expose a consistent real-time quota API, so `status` reports locally observed usage and optional local request caps—not a claim about your provider's actual remaining balance.

## Highlights

- `run` for one-shot prompts and `agent` for an interactive conversation.
- Automatic provider fallback for rate limits (`429`), quota errors (including `insufficient_quota`), transient server/network errors, and authentication failures.
- Supports native OpenAI, Anthropic, Google Gemini, Groq, and OpenRouter chat APIs.
- Local-only usage ledger in SQLite; it stores timestamps, provider/model, token counts, and error categories—never prompts or responses.
- `status` shows configured providers, key availability, locally observed monthly calls, and optional local request caps.
- No telemetry, analytics, or third-party services beyond the selected LLM provider(s).

## Install

Python 3.10 or newer is required.

```bash
git clone https://github.com/joaovitorsouzaduarte15-png/llm-free-tier-router.git
cd llm-free-tier-router
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e .
cp .env.example .env
```

Edit `.env` and add a key. For a simple one-key setup, configure only OpenRouter:

```dotenv
LLM_ROUTER_API_KEY=your_openrouter_key
LLM_ROUTER_PROVIDERS=openrouter
```

The unified `LLM_ROUTER_API_KEY` is used as the OpenRouter key. Direct integrations use their standard provider-specific environment variable; this is required by those providers and cannot be replaced by one credential unless you use a gateway such as OpenRouter.

## Usage

```bash
# Send a prompt. The CLI prints the provider/model that answered.
llm-router run "Explain the CAP theorem in three sentences."

# Add system instructions and choose a model for the first available provider.
llm-router run "Write a haiku about compilers" --system "Be concise."

# Start an interactive conversation; type /exit or Ctrl-D to stop.
llm-router agent

# Inspect configuration and locally observed usage.
llm-router status
llm-router providers
```

Use `--json` with `run` for machine-readable output. `--model` overrides the model for the selected request. `--provider` restricts a request to one provider; by default the configured provider order is used.

```bash
llm-router run "Summarize this text" --provider groq --model llama-3.1-8b-instant --json
```

The agent accepts an optional initial prompt: `llm-router agent "Help me plan a study schedule"`. Conversation history is sent to the active provider for each turn. Do not enter secrets or sensitive data unless you are comfortable sending it to the configured provider.

## Providers and configuration

`LLM_ROUTER_PROVIDERS` is a comma-separated fallback order. Only providers with a configured key are eligible. The default order is `openrouter,groq,google,anthropic,openai`.

| Provider | API key environment variable | Default model |
| --- | --- | --- |
| OpenRouter | `OPENROUTER_API_KEY` or `LLM_ROUTER_API_KEY` | `openrouter/auto` |
| Groq | `GROQ_API_KEY` | `llama-3.3-70b-versatile` |
| Google Gemini | `GOOGLE_API_KEY` or `GEMINI_API_KEY` | `gemini-2.0-flash` |
| Anthropic | `ANTHROPIC_API_KEY` | `claude-3-5-haiku-latest` |
| OpenAI | `OPENAI_API_KEY` | `gpt-4o-mini` |

Provider model overrides use `LLM_ROUTER_MODEL_<PROVIDER>`, e.g. `LLM_ROUTER_MODEL_GROQ=llama-3.1-8b-instant`. For per-request order, set `LLM_ROUTER_PROVIDERS` in the environment before launching the CLI. `--provider` is useful for pinning a specific request.

Optional local request caps can be set as `LLM_ROUTER_MONTHLY_LIMIT_<PROVIDER>` (for example `LLM_ROUTER_MONTHLY_LIMIT_GROQ=500`). They count requests recorded by this installation during the current UTC month. They are **not** synchronized with provider billing or quota systems. When a local cap is reached, the router skips that provider and tries the next one.

Other settings:

- `LLM_ROUTER_TIMEOUT`: HTTP timeout in seconds (default `45`).
- `LLM_ROUTER_DB_PATH`: SQLite usage database path (default `~/.local/share/llm-free-tier-router/usage.sqlite3`).
- `LLM_ROUTER_OPENROUTER_SITE_URL` and `LLM_ROUTER_OPENROUTER_APP_NAME`: optional OpenRouter attribution headers.

See [`.env.example`](.env.example) for a complete configuration template.

## Fallback behavior

A request is attempted once against each eligible provider in configured order. The router moves on for rate limits, quota exhaustion, network/timeouts, server errors, and authentication errors. Other request errors are reported without repeatedly sending the same invalid request. A successful response stops the chain. If every provider fails, the CLI reports a concise summary without exposing API keys or storing full provider error bodies.

Fallback can incur separate charges or consume quota on another provider. Check the models, pricing, and terms for every enabled provider. Provider/model compatibility and availability can change over time.

## Privacy and security

- Prompts and responses are sent only to the provider that handles the request (and potentially the next provider if fallback occurs).
- The project does not send telemetry or collect analytics.
- The local SQLite ledger excludes prompt/response content and API keys.
- Keep `.env` private; never commit live keys. Revoke any key accidentally exposed.
- The CLI makes direct HTTPS requests to the configured provider APIs; OpenRouter requests go to OpenRouter.

## Development

```bash
python -m pip install -e '.[dev]'
pytest
ruff check .
```

Tests use mocked HTTP responses and temporary SQLite databases; they do not call live APIs.

## License

MIT. See [LICENSE](LICENSE).
