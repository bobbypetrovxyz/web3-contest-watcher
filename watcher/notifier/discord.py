"""Discord notifier — posts to an incoming webhook URL."""

from __future__ import annotations

from . import _http
from ._format import chat_text
from .base import NotifierError


class DiscordNotifier:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, subject: str, body: str) -> None:
        if not self.webhook_url:
            raise NotifierError("Discord notifier requires DISCORD_WEBHOOK_URL")
        _http.post_json(self.webhook_url, {"content": chat_text(subject, body)})
