"""Notifier plugin seam.

A Notifier delivers an alert to one channel. Built-in channels are selected by
the WATCHER_NOTIFIER env var; custom channels can be loaded via a
``module:Class`` value (see build_notifier). A future MCP server, if an agent
ever orchestrates channel choice, would wrap this same interface.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class NotifierError(Exception):
    """Raised when a channel is misconfigured or delivery fails."""


@runtime_checkable
class Notifier(Protocol):
    def send(self, subject: str, body: str) -> None:
        ...
