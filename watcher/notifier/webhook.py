"""Generic webhook notifier — POSTs a JSON payload to any URL.

Payload: {"subject": ..., "body": ..., "text": "<subject>\\n\\n<body>"}.
Set WEBHOOK_TOKEN to send an ``Authorization: Bearer <token>`` header.
Use this to integrate any channel not shipped as a built-in.
"""

from __future__ import annotations

from . import _http
from ._format import chat_text
from .base import NotifierError


class WebhookNotifier:
    def __init__(self, url: str, token: str = ""):
        self.url = url
        self.token = token

    def send(self, subject: str, body: str) -> None:
        if not self.url:
            raise NotifierError("Webhook notifier requires WEBHOOK_URL")
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else None
        payload = {"subject": subject, "body": body, "text": chat_text(subject, body)}
        _http.post_json(self.url, payload, headers=headers)
