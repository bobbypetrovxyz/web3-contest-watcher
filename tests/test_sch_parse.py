"""Parse the saved SCH aggregator fixture (data-* embedded listings)."""

from __future__ import annotations

from pathlib import Path

import pytest

from watcher.sources.base import SourceError
from watcher.sources.sch import parse_listings, _SKIP_SOURCES

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sch_active_sample.html"


def _html():
    return FIXTURE.read_text(encoding="utf-8")


def test_fixture_parses_listings():
    items = parse_listings(_html(), now_ts=0)
    assert len(items) > 0
    for c in items:
        assert c.source == "sch"
        assert c.kind in ("contest", "bounty")
        assert c.url.startswith("http")
        assert c.platform
        if c.kind == "bounty":
            assert c.start_ts is None
        if c.start_ts is not None:
            assert c.start_ts < 10_000_000_000


def test_skips_directly_covered_platforms():
    # SCH overlaps sherlock/cantina/immunefi; those must be skipped (we have
    # direct sources) so they don't double-alert.
    items = parse_listings(_html(), now_ts=0)
    sources_seen = {c.platform.lower() for c in items}
    for skipped in _SKIP_SOURCES:
        assert skipped not in sources_seen, f"{skipped} should be skipped"


def test_includes_hackenproof_with_canonical_url():
    # The whole point: HackenProof comes through, with canonical URLs that dedup
    # against dailywarden (id == the hackenproof.com URL).
    items = parse_listings(_html(), now_ts=0)
    hp = [c for c in items if c.platform == "HackenProof"]
    assert hp, "expected HackenProof listings from SCH"
    for c in hp:
        assert "hackenproof.com" in c.url
        assert c.id == c.url  # make_id uses the canonical URL -> dedups vs dailywarden


def test_ended_contests_filtered():
    future = parse_listings(_html(), now_ts=9_999_999_999)
    assert all(c.kind != "contest" for c in future)


def test_no_data_raises():
    with pytest.raises(SourceError):
        parse_listings("<html>no listings</html>", now_ts=0)
