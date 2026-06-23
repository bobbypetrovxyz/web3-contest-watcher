"""Parse the saved dailywarden fixture and validate the normalized output."""

from __future__ import annotations

from pathlib import Path

import pytest

from watcher.models import ms_to_s, parse_pot_size
from watcher.sources.base import SourceError
from watcher.sources.dailywarden import parse_contests

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "dailywarden_sample.html"


def test_fixture_parses_to_contests():
    html = FIXTURE.read_text(encoding="utf-8")
    contests = parse_contests(html)

    assert len(contests) > 0, "expected at least one contest from the fixture"

    for c in contests:
        assert c.id, "every contest needs a stable id"
        assert c.platform
        assert c.name or c.url
        # timestamps are epoch seconds (or None), never the raw millisecond values
        if c.start_ts is not None:
            assert c.start_ts < 10_000_000_000, "start_ts must be seconds, not ms"
        if c.pot_size_usd is not None:
            assert c.pot_size_usd >= 0


def test_upcoming_contests_have_start_times():
    # parse_contests reads contests.flattened = the UPCOMING contests, which
    # always carry start dates (these drive both the new and t24h alerts).
    # The captured fixture contains 4 such contests.
    html = FIXTURE.read_text(encoding="utf-8")
    contests = parse_contests(html)
    assert len(contests) == 4
    assert all(c.start_ts is not None for c in contests)
    assert all(c.platform for c in contests)


def test_parse_failure_raises_source_error():
    with pytest.raises(SourceError):
        parse_contests("<html><body>no next data here</body></html>")


def test_ms_to_s_and_pot_helpers():
    assert ms_to_s(1780617600000) == 1780617600
    assert ms_to_s(0) is None
    assert ms_to_s(None) is None
    assert parse_pot_size("$15000.0") == 15000.0
    assert parse_pot_size("$1,500") == 1500.0
    assert parse_pot_size("N/A") is None
    assert parse_pot_size(None) is None
