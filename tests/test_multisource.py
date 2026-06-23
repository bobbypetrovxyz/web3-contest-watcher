"""Multi-source orchestration: failure isolation and per-source seeding."""

from __future__ import annotations

import pytest

import watcher.run as run
from watcher.config import Config
from watcher.models import Contest
from watcher.sources.base import SourceError


class FakeSource:
    def __init__(self, name, contests=None, error=None):
        self.name = name
        self._contests = contests or []
        self._error = error

    def fetch(self):
        if self._error is not None:
            raise self._error
        return list(self._contests)


class Cap:
    def __init__(self):
        self.sent = []

    def send(self, subject, body):
        self.sent.append((subject, body))


def contest(cid, source, name=None):
    return Contest(
        id=cid, platform=source.title(), name=name or cid,
        url=f"https://x/{cid}", source=source, kind="contest", start_ts=None,
    )


def _cfg(tmp_path):
    return Config(
        db_path=str(tmp_path / "multi.db"), source_url="x", sources="a,b",
        discord_bot_token="", discord_channel_ids="",
        recipient="", notifier="console", dry_run=False, t24h_seconds=86400,
    )


def _run(monkeypatch, cfg, sources, cap):
    monkeypatch.setattr(run.Config, "from_env", classmethod(lambda cls: cfg))
    monkeypatch.setattr(run, "build_sources", lambda c: sources)
    monkeypatch.setattr(run, "build_notifier", lambda c: cap)
    return run.main([])


# ---- fetch_all -----------------------------------------------------------
def test_fetch_all_isolates_failures():
    ok = FakeSource("a", [contest("a:1", "a")])
    bad = FakeSource("b", error=SourceError("boom"))
    contests, failures, succeeded = run.fetch_all([ok, bad])
    assert [c.id for c in contests] == ["a:1"]
    assert succeeded == {"a"}
    assert failures == [("b", "boom")]


def test_dedupe_by_id_keeps_first():
    items = [contest("x", "a"), contest("x", "b"), contest("y", "a")]
    out, dropped = run.dedupe_by_id(items)
    assert dropped == 1
    assert [c.id for c in out] == ["x", "y"]
    assert out[0].source == "a", "first occurrence (earlier source) wins"


def test_fetch_all_survives_unexpected_exception():
    boom = FakeSource("a", error=RuntimeError("kaboom"))
    contests, failures, succeeded = run.fetch_all([boom])
    assert contests == [] and succeeded == set()
    assert failures[0][0] == "a" and "kaboom" in failures[0][1]


# ---- per-source seeding --------------------------------------------------
def test_first_run_seeds_silently_then_alerts_on_new(monkeypatch, tmp_path):
    cfg = _cfg(tmp_path)

    # Run 1: both sources brand new -> seeded silently, no alerts.
    a = FakeSource("a", [contest("a:1", "a")])
    b = FakeSource("b", [contest("b:1", "b")])
    cap1 = Cap()
    assert _run(monkeypatch, cfg, [a, b], cap1) == 0
    assert cap1.sent == []

    # Run 2: source a lists a genuinely new contest -> exactly one alert.
    a2 = FakeSource("a", [contest("a:1", "a"), contest("a:2", "a")])
    b2 = FakeSource("b", [contest("b:1", "b")])
    cap2 = Cap()
    assert _run(monkeypatch, cfg, [a2, b2], cap2) == 0
    new_alerts = [s for s in cap2.sent if s[0].startswith("[New ")]
    assert len(new_alerts) == 1
    assert "a:2" in new_alerts[0][1], "the new alert should describe contest a:2"


def test_cross_source_duplicate_alerts_once(monkeypatch, tmp_path):
    cfg = _cfg(tmp_path)
    # Seed both sources first so the shared listing is genuinely "new" in run 2.
    _run(monkeypatch, cfg,
         [FakeSource("a", [contest("a:1", "a")]), FakeSource("b", [contest("b:1", "b")])],
         Cap())

    # Both sources now carry the SAME contest id -> must alert exactly once.
    a = FakeSource("a", [contest("a:1", "a"), contest("shared:1", "a", "Shared")])
    b = FakeSource("b", [contest("b:1", "b"), contest("shared:1", "b", "Shared")])
    cap = Cap()
    assert _run(monkeypatch, cfg, [a, b], cap) == 0
    new = [s for s in cap.sent if s[0].startswith("[New ")]
    assert len(new) == 1, "a cross-source duplicate must not double-alert"


def test_newly_added_source_does_not_storm(monkeypatch, tmp_path):
    cfg = _cfg(tmp_path)

    # Run 1: only source a exists and is seeded.
    cap1 = Cap()
    assert _run(monkeypatch, cfg, [FakeSource("a", [contest("a:1", "a")])], cap1) == 0
    assert cap1.sent == []

    # Run 2: source b is enabled for the first time with 3 existing listings.
    # Those must be seeded silently, NOT fired as 3 new alerts.
    b = FakeSource("b", [contest("b:1", "b"), contest("b:2", "b"), contest("b:3", "b")])
    cap2 = Cap()
    assert _run(monkeypatch, cfg, [FakeSource("a", [contest("a:1", "a")]), b], cap2) == 0
    assert [s for s in cap2.sent if s[0].startswith("[New ")] == []


# ---- failure behavior ----------------------------------------------------
def test_partial_failure_warns_but_still_processes(monkeypatch, tmp_path):
    cfg = _cfg(tmp_path)

    # Seed source a first (so later it can produce a real alert).
    assert _run(monkeypatch, cfg, [FakeSource("a", [contest("a:1", "a")])], Cap()) == 0

    # Now a has a new contest, b is broken -> one new alert + one warning.
    a = FakeSource("a", [contest("a:1", "a"), contest("a:2", "a")])
    b = FakeSource("b", error=SourceError("parser stale"))
    cap = Cap()
    assert _run(monkeypatch, cfg, [a, b], cap) == 0
    assert any(s[0].startswith("[New ") for s in cap.sent)
    assert any("fail" in s[0].lower() for s in cap.sent)


def test_all_sources_fail_returns_error(monkeypatch, tmp_path):
    cfg = _cfg(tmp_path)
    a = FakeSource("a", error=SourceError("down"))
    b = FakeSource("b", error=SourceError("down"))
    cap = Cap()
    assert _run(monkeypatch, cfg, [a, b], cap) == 1
    assert any("watcher" in s[0].lower() or "error" in s[0].lower() for s in cap.sent)
