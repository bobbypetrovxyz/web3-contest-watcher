"""Notification channels and the factory that selects them from config.

WATCHER_NOTIFIER accepts:
  - a built-in name: console | smtp | gmail | discord | slack | telegram | webhook
  - several, comma-separated, to fan out: "discord,telegram,smtp"
  - a custom "module:Class" path to load your own Notifier (read its own env)

Each channel reads its own env vars (see .env.example). A dry run always uses
the console notifier so nothing is actually delivered.
"""

from __future__ import annotations

import importlib
import os

from ..config import Config
from .base import Notifier, NotifierError
from .console import ConsoleNotifier
from .discord import DiscordNotifier
from .email_smtp import SmtpNotifier
from .multi import MultiNotifier
from .slack import SlackNotifier
from .telegram import TelegramNotifier
from .webhook import WebhookNotifier

__all__ = [
    "Notifier", "NotifierError", "ConsoleNotifier", "SmtpNotifier",
    "DiscordNotifier", "SlackNotifier", "TelegramNotifier", "WebhookNotifier",
    "MultiNotifier", "build_notifier",
]

_BUILTINS = {"console", "smtp", "gmail", "discord", "slack", "telegram", "webhook"}


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _build_one(name: str, config: Config) -> Notifier:
    raw = name.strip()
    key = raw.lower()
    if key == "console":
        return ConsoleNotifier()
    if key in ("smtp", "gmail"):
        return SmtpNotifier(
            host=_env("SMTP_HOST", "smtp.gmail.com"),
            port=int(_env("SMTP_PORT", "465")),
            user=_env("SMTP_USER"),
            password=_env("SMTP_PASS"),
            recipient=config.recipient,
        )
    if key == "discord":
        return DiscordNotifier(_env("DISCORD_WEBHOOK_URL"))
    if key == "slack":
        return SlackNotifier(_env("SLACK_WEBHOOK_URL"))
    if key == "telegram":
        return TelegramNotifier(_env("TELEGRAM_BOT_TOKEN"), _env("TELEGRAM_CHAT_ID"))
    if key == "webhook":
        return WebhookNotifier(_env("WEBHOOK_URL"), _env("WEBHOOK_TOKEN"))
    # Custom plugin: "package.module:ClassName" (no-arg constructor; reads env).
    if ":" in raw:
        module_path, _, class_name = raw.partition(":")
        try:
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
        except (ImportError, AttributeError) as exc:
            raise NotifierError(f"could not load custom notifier {raw!r}: {exc}") from exc
        return cls()
    raise NotifierError(f"unknown notifier: {raw!r}")


def build_notifier(config: Config) -> Notifier:
    if config.dry_run:
        return ConsoleNotifier()
    names = [n for n in config.notifier.split(",") if n.strip()]
    if not names:
        return ConsoleNotifier()
    notifiers = [_build_one(n, config) for n in names]
    return notifiers[0] if len(notifiers) == 1 else MultiNotifier(notifiers)
