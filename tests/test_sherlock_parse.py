"""Parse the saved Sherlock API fixture and validate normalization + filtering."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from watcher.sources.base import SourceError
from watcher.sources.sherlock import parse_contests

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sherlock_contests_sample.json"


def _payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_fixture_parses_and_normalizes():
    # now_ts=0 keeps every contest (all ends_at are positive epochs).
    contests = parse_contests([_payload()], now_ts=0)
    assert len(contests) > 0
    for c in contests:
        assert c.id.startswith("sherlock:"), "ids must be namespaced per source"
        assert c.source == "sherlock"
        assert c.kind == "contest"
        assert c.platform == "Sherlock"
        assert c.name
        assert "audits.sherlock.xyz/contests/" in c.url
        if c.start_ts is not None:
            assert c.start_ts < 10_000_000_000, "start_ts must be epoch seconds"
        if c.pot_size_usd is not None:
            assert c.pot_size_usd >= 0


def test_finished_contests_are_filtered_out():
    # With a far-future "now", every contest has already ended -> none kept.
    contests = parse_contests([_payload()], now_ts=9_999_999_999)
    assert contests == []


def test_bad_payload_raises():
    with pytest.raises(SourceError):
        parse_contests([{"no_items": 1}], now_ts=0)
    with pytest.raises(SourceError):
        parse_contests([{"items": "not-a-list"}], now_ts=0)
