"""Telegram notifier — sends via the Bot API.

Create a bot with @BotFather to get TELEGRAM_BOT_TOKEN, then obtain your
TELEGRAM_CHAT_ID (e.g. by messaging the bot and reading getUpdates).
"""

from __future__ import annotations

from . import _http
from ._format import chat_text
from .base import NotifierError


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send(self, subject: str, body: str) -> None:
        if not (self.bot_token and self.chat_id):
            raise NotifierError(
                "Telegram notifier requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID"
            )
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        _http.post_json(url, {"chat_id": self.chat_id, "text": chat_text(subject, body)})
