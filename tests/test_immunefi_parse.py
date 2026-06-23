"""Parse the saved Immunefi explore fixture and validate bounty normalization."""

from __future__ import annotations

from pathlib import Path

import pytest

from watcher.sources.base import SourceError
from watcher.sources.immunefi import parse_bounties, parse_competitions

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
BOUNTY_FIXTURE = FIXTURES / "immunefi_explore_sample.html"
COMP_FIXTURE = FIXTURES / "immunefi_competition_sample.html"


def test_fixture_parses_to_bounties():
    html = BOUNTY_FIXTURE.read_text(encoding="utf-8")
    bounties = parse_bounties(html)

    assert len(bounties) > 50, "expected the full embedded board, not a handful"
    ids = {b.id for b in bounties}
    assert len(ids) == len(bounties), "ids must be unique (deduped by slug)"

    for b in bounties:
        assert b.id.startswith("immunefi:")
        assert b.source == "immunefi"
        assert b.kind == "bounty"
        assert b.platform == "Immunefi"
        assert b.start_ts is None, "perpetual bounties have no scheduled start"
        assert b.url.startswith("https://immunefi.com/bug-bounty/")
        if b.pot_size_usd is not None:
            assert b.pot_size_usd >= 0


def test_bounty_name_uses_project_field():
    bounties = parse_bounties(BOUNTY_FIXTURE.read_text(encoding="utf-8"))
    by_id = {b.id: b for b in bounties}
    # The `project` field carries the real display name ("LayerZero"), not the slug.
    assert by_id["immunefi:layerzero"].name == "LayerZero"


def test_bounty_carries_listed_and_updated_dates():
    bounties = parse_bounties(BOUNTY_FIXTURE.read_text(encoding="utf-8"))
    by_id = {b.id: b for b in bounties}
    y = by_id["immunefi:yearnfinance"]
    # 'Live since' (launchDate) and 'Last updated' (updatedDate), as epoch seconds.
    assert y.listed_ts is not None and y.listed_ts < 10_000_000_000
    assert y.updated_ts is not None and y.updated_ts < 10_000_000_000
    assert y.updated_ts >= y.listed_ts


def test_competitions_parse_with_dates():
    html = COMP_FIXTURE.read_text(encoding="utf-8")
    # now_ts=0 keeps every competition (all endDates are positive epochs).
    comps = parse_competitions(html, now_ts=0)
    assert len(comps) > 0
    for c in comps:
        assert c.id.startswith("immunefi:comp:")
        assert c.source == "immunefi"
        assert c.kind == "contest", "competitions are time-boxed contests"
        assert c.url.startswith("https://immunefi.com/audit-competition/")
        if c.start_ts is not None:
            assert c.start_ts < 10_000_000_000, "start_ts must be epoch seconds"
        if c.end_ts is not None:
            assert c.end_ts < 10_000_000_000


def test_finished_competitions_filtered_out():
    html = COMP_FIXTURE.read_text(encoding="utf-8")
    assert parse_competitions(html, now_ts=9_999_999_999) == []


def test_no_data_raises():
    with pytest.raises(SourceError):
        parse_bounties("<html><body>nothing embedded here</body></html>")
    with pytest.raises(SourceError):
        parse_competitions("<html><body>nothing here</body></html>", now_ts=0)
