"""Command-line interface."""

from __future__ import annotations

import argparse
import json
import sys

from .config import PROVIDER_DEFAULTS, Settings
from .router import AllProvidersFailed, Router
from .storage import UsageStore


def _build_router() -> tuple[Settings, Router]:
    settings = Settings.from_env()
    return settings, Router(settings, UsageStore(settings.db_path))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="llm-router", description="Route LLM requests with automatic provider fallback.")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="Send a single prompt")
    run.add_argument("prompt", help="Prompt text")
    run.add_argument("--system", help="Optional system instruction")
    run.add_argument("--provider", choices=sorted(PROVIDER_DEFAULTS), help="Use only this configured provider")
    run.add_argument("--model", help="Override the configured model for this request")
    run.add_argument("--json", action="store_true", help="Print a JSON response envelope")

    agent = commands.add_parser("agent", help="Start an interactive conversation")
    agent.add_argument("prompt", nargs="?", help="Optional initial prompt")
    agent.add_argument("--system", default="You are a helpful assistant.", help="System instruction")
    agent.add_argument("--provider", choices=sorted(PROVIDER_DEFAULTS), help="Use only this configured provider")
    agent.add_argument("--model", help="Override the configured model")

    commands.add_parser("status", help="Show configured providers and local usage")
    commands.add_parser("providers", help="List supported providers and default models")
    return parser


def _run_command(args: argparse.Namespace, router: Router) -> int:
    messages = []
    if args.system:
        messages.append({"role": "system", "content": args.system})
    messages.append({"role": "user", "content": args.prompt})
    result = router.complete(messages, provider=args.provider, model=args.model)
    if args.json:
        print(json.dumps({
            "text": result.text, "provider": result.provider, "model": result.model,
            "usage": {"prompt_tokens": result.prompt_tokens, "completion_tokens": result.completion_tokens},
        }, ensure_ascii=False))
    else:
        print(result.text)
        print(f"\n[{result.provider} / {result.model}]", file=sys.stderr)
    return 0


def _agent_command(args: argparse.Namespace, router: Router) -> int:
    messages = [{"role": "system", "content": args.system}]
    print("Interactive agent. Type /exit or press Ctrl-D to quit.")
    if args.prompt:
        pending = args.prompt
    else:
        pending = None
    while True:
        if pending is None:
            try:
                pending = input("you> ")
            except EOFError:
                print()
                return 0
        if pending.strip().lower() in {"/exit", "/quit"}:
            return 0
        if not pending.strip():
            pending = None
            continue
        messages.append({"role": "user", "content": pending})
        result = router.complete(messages, provider=args.provider, model=args.model)
        print(f"\n{result.text}\n[{result.provider} / {result.model}]\n")
        messages.append({"role": "assistant", "content": result.text})
        pending = None


def _status(settings: Settings, router: Router) -> None:
    configured = {config.name: config for config in settings.providers}
    print("Provider status (usage is local observation, not live provider quota):")
    for name in PROVIDER_DEFAULTS:
        config = configured.get(name)
        if config is None:
            print(f"- {name}: not configured (API key missing)")
            continue
        calls, successes, prompt_tokens, completion_tokens = router.store.month_stats(name)
        cap = f"{calls}/{config.monthly_limit} local requests" if config.monthly_limit is not None else f"{calls} local requests; remote quota unknown"
        state = "local cap reached" if config.monthly_limit is not None and calls >= config.monthly_limit else "available (key configured)"
        print(f"- {name}: {state}; model={config.model}; {cap}; successful={successes}; tokens={prompt_tokens + completion_tokens}")


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "providers":
        for name, (model, _) in PROVIDER_DEFAULTS.items():
            print(f"{name}: default model {model}")
        return 0
    try:
        settings, router = _build_router()
        if args.command == "status":
            _status(settings, router)
            return 0
        if args.command == "run":
            return _run_command(args, router)
        if args.command == "agent":
            return _agent_command(args, router)
    except (AllProvidersFailed, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
