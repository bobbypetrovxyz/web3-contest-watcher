"""Alert detection, idempotency, seeding, and dry-run behavior with injected time."""

from __future__ import annotations

import pytest

from watcher.models import Contest
from watcher.run import process
from watcher.store import Store

NOW = 1_000_000  # fixed injected "now" (epoch seconds)
HOUR = 3600
DAY = 24 * HOUR


class CapturingNotifier:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    def send(self, subject: str, body: str) -> None:
        self.sent.append((subject, body))


def make_contest(cid: str, start_offset: int | None) -> Contest:
    start = None if start_offset is None else NOW + start_offset
    return Contest(
        id=cid, platform="Code4rena", name=f"Contest {cid}",
        url=f"https://example.com/{cid}", start_ts=start,
    )


@pytest.fixture
def store(tmp_path):
    return Store(str(tmp_path / "test.db"))


def test_new_alert_fires_once(store):
    notifier = CapturingNotifier()
    contests = [make_contest("a", None), make_contest("b", 5 * DAY)]

    r1 = process(store, notifier, contests, NOW, DAY, dry_run=False)
    assert r1["new"] == 2
    assert len([s for s in notifier.sent if s[0].startswith("[New ")]) == 2

    # Second run: nothing new (idempotent via upsert + contest_exists).
    notifier2 = CapturingNotifier()
    r2 = process(store, notifier2, contests, NOW, DAY, dry_run=False)
    assert r2["new"] == 0
    assert notifier2.sent == []


def test_t24h_window(store):
    notifier = CapturingNotifier()
    contests = [
        make_contest("soon", 12 * HOUR),   # within 24h -> due
        make_contest("far", 2 * DAY),      # >24h -> not due
        make_contest("past", -1 * HOUR),   # already started -> not due
        make_contest("perpetual", None),   # no start -> not due
    ]
    r = process(store, notifier, contests, NOW, DAY, dry_run=False)
    assert r["t24h"] == 1
    t24h_subjects = [s for s in notifier.sent if "Starting soon" in s[0]]
    assert len(t24h_subjects) == 1


def test_t24h_idempotent_across_runs(store):
    contests = [make_contest("soon", 6 * HOUR)]

    n1 = CapturingNotifier()
    assert process(store, n1, contests, NOW, DAY, dry_run=False)["t24h"] == 1

    n2 = CapturingNotifier()
    assert process(store, n2, contests, NOW, DAY, dry_run=False)["t24h"] == 0
    assert n2.sent == []


def test_seed_suppresses_new_alerts(store):
    contests = [make_contest("a", 5 * DAY), make_contest("b", None)]
    store.seed(contests, NOW)

    notifier = CapturingNotifier()
    r = process(store, notifier, contests, NOW, DAY, dry_run=False)
    assert r["new"] == 0
    assert notifier.sent == []


def test_dry_run_does_not_persist(store):
    notifier = CapturingNotifier()
    contests = [make_contest("a", 6 * HOUR)]

    r = process(store, notifier, contests, NOW, DAY, dry_run=True)
    # Alerts are previewed...
    assert r["new"] == 1 and r["t24h"] == 1
    assert len(notifier.sent) == 2
    # ...but nothing is written to the store.
    assert store.contest_exists("a") is False
    assert store.already_notified("a", "t24h") is False
