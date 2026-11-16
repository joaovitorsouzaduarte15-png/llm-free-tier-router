"""Local usage ledger. Prompts, responses, and credentials are never persisted."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class UsageStore:
    def __init__(self, path: Path):
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            """CREATE TABLE IF NOT EXISTS usage (
                id INTEGER PRIMARY KEY,
                created_at TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                success INTEGER NOT NULL,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                error_code TEXT
            )"""
        )
        return connection

    def record(self, provider: str, model: str, *, success: bool,
               prompt_tokens: int | None = None, completion_tokens: int | None = None,
               error_code: str | None = None) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO usage (created_at, provider, model, success, prompt_tokens, completion_tokens, error_code) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (datetime.now(timezone.utc).isoformat(), provider, model, int(success), prompt_tokens, completion_tokens, error_code),
            )

    def month_stats(self, provider: str, *, now: datetime | None = None) -> tuple[int, int, int, int]:
        current = now or datetime.now(timezone.utc)
        month_prefix = current.astimezone(timezone.utc).strftime("%Y-%m-")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*), SUM(success), SUM(COALESCE(prompt_tokens, 0)), SUM(COALESCE(completion_tokens, 0)) FROM usage WHERE provider = ? AND created_at LIKE ?",
                (provider, month_prefix + "%"),
            ).fetchone()
        return tuple(int(value or 0) for value in row)
