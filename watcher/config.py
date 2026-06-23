"""Environment-driven configuration (cloud-portable: no hardcoded paths/secrets)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SOURCE_URL = "https://www.dailywarden.com/"
DEFAULT_T24H_SECONDS = 24 * 60 * 60
FAILURE_EMAIL_THROTTLE_SECONDS = 24 * 60 * 60


def _load_dotenv() -> None:
    """Best-effort .env loader (no third-party dependency).

    Looks for a .env file next to the project root and populates os.environ for
    keys that are not already set. Silently does nothing if absent.
    """
    for candidate in (Path.cwd() / ".env", Path(__file__).resolve().parent.parent / ".env"):
        if not candidate.is_file():
            continue
        for line in candidate.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)
        break


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Config:
    db_path: str
    source_url: str
    # Enabled sources: comma-separated names (dailywarden, sherlock, immunefi, discord).
    sources: str
    # Discord SOURCE (reading followed announcements): bot token + channel id list.
    discord_bot_token: str
    discord_channel_ids: str
    recipient: str
    # Channel selection: one or more comma-separated names, or a module:Class
    # plugin path. Channel-specific secrets are read by each notifier from env.
    notifier: str
    dry_run: bool
    t24h_seconds: int

    @classmethod
    def from_env(cls) -> "Config":
        _load_dotenv()
        default_db = str(Path(__file__).resolve().parent.parent / "watcher.db")
        return cls(
            db_path=os.environ.get("WATCHER_DB_PATH", default_db),
            source_url=os.environ.get("WATCHER_SOURCE_URL", DEFAULT_SOURCE_URL),
            sources=os.environ.get("WATCHER_SOURCES", "dailywarden").strip(),
            discord_bot_token=os.environ.get("DISCORD_BOT_TOKEN", ""),
            discord_channel_ids=os.environ.get("DISCORD_CHANNEL_IDS", ""),
            recipient=os.environ.get("WATCHER_RECIPIENT", ""),
            notifier=os.environ.get("WATCHER_NOTIFIER", "console").strip(),
            dry_run=_as_bool(os.environ.get("WATCHER_DRY_RUN"), False),
            t24h_seconds=int(os.environ.get("WATCHER_T24H_SECONDS", DEFAULT_T24H_SECONDS)),
        )
