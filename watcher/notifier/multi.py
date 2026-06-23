"""Fan-out notifier: deliver one alert to several channels.

Delivery semantics: every channel is attempted. Per-channel failures are
logged. The call raises only if *all* channels fail — so as long as one channel
succeeds, run.py records the alert as sent and won't re-send (avoiding a
duplicate storm on the working channels next run).
"""

from __future__ import annotations

import sys

from .base import Notifier, NotifierError


class MultiNotifier:
    def __init__(self, notifiers: list[Notifier]):
        self.notifiers = notifiers

    def send(self, subject: str, body: str) -> None:
        errors = []
        for n in self.notifiers:
            try:
                n.send(subject, body)
            except Exception as exc:  # noqa: BLE001 - isolate one channel's failure
                errors.append((type(n).__name__, exc))
                print(f"[watcher] channel {type(n).__name__} failed: {exc}", file=sys.stderr)
        if errors and len(errors) == len(self.notifiers):
            raise NotifierError(
                "all notification channels failed: "
                + "; ".join(f"{name}: {exc}" for name, exc in errors)
            )
