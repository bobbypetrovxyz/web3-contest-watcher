"""Console notifier — prints alerts. Default for local dev and dry runs."""

from __future__ import annotations


class ConsoleNotifier:
    def send(self, subject: str, body: str) -> None:
        print("=" * 70)
        print(f"SUBJECT: {subject}")
        print("-" * 70)
        print(body)
        print("=" * 70)
