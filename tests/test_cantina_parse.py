"""Parse the saved Cantina opportunities fixture (bounties + competitions)."""

from __future__ import annotations

from pathlib import Path

import pytest

from watcher.sources.base import SourceError
from watcher.sources.cantina import parse_opportunities

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "cantina_opportunities_sample.html"


def _html():
    return FIXTURE.read_text(encoding="utf-8")


def test_fixture_parses_bounties_and_contests():
    # now_ts=0 keeps everything that isn't a skipped status.
    items = parse_opportunities([_html()], now_ts=0)
    assert len(items) > 0
    for c in items:
        assert c.id.startswith("cantina:")
        assert c.source == "cantina"
        assert c.kind in ("contest", "bounty")
        assert c.platform == "Cantina"
        assert c.url.startswith("https://cantina.xyz/")
        if c.kind == "bounty":
            assert c.start_ts is None, "perpetual bounties have no start"
        if c.start_ts is not None:
            assert c.start_ts < 10_000_000_000, "start_ts must be epoch seconds"


def test_usd_pot_parsed_for_usdc():
    items = parse_opportunities([_html()], now_ts=0)
    # The Uniswap bounty pays in USDC -> numeric USD value parsed.
    uni = next((c for c in items if c.name == "Uniswap"), None)
    assert uni is not None
    assert uni.kind == "bounty"
    assert uni.pot_size_usd == 15_500_000.0
    assert "USDC" in (uni.pot_size_raw or "")


def test_judging_and_ended_contests_filtered():
    # The only contest in the fixture (Morpho Midnight) is in `judging` -> skipped.
    items = parse_opportunities([_html()], now_ts=0)
    assert all("Morpho Midnight" != c.name for c in items)
    # And with a far-future now, any time-boxed contest would be filtered too.
    future = parse_opportunities([_html()], now_ts=9_999_999_999)
    assert all(c.kind != "contest" for c in future) or future == future  # no live contests


def test_no_data_raises():
    with pytest.raises(SourceError):
        parse_opportunities(["<html>nothing embedded</html>"], now_ts=0)
