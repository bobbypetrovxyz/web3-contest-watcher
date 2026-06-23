"""Shared message formatting for chat-style channels (single text blob)."""

from __future__ import annotations


def chat_text(subject: str, body: str, limit: int = 1900) -> str:
    """Combine subject + body into one plain-text message, truncated to a
    length safe for chat platforms (Discord caps at 2000 chars, etc.).
    """
    text = f"{subject}\n\n{body}".strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"
