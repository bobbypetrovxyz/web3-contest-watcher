"""Relay-mode parsing of Discord messages (embed + plain-text shapes)."""

from __future__ import annotations

import json
from pathlib import Path

from watcher.sources.discord import parse_messages

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "discord_messages_sample.json"


def _msgs():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_relays_each_message_as_announcement():
    out = parse_messages(_msgs())
    assert len(out) == 2
    for c in out:
        assert c.id.startswith("discord:")
        assert c.source == "discord"
        assert c.kind == "announcement"
        assert c.start_ts is None, "announcements have no schedule (no t24h)"
        assert c.listed_ts is not None and c.listed_ts < 10_000_000_000


def test_embed_message_extraction():
    embed, _plain = parse_messages(_msgs())
    assert embed.platform == "Sherlock"               # from embed author
    assert embed.name == "New Contest: Acme Lending"  # from embed title
    assert embed.url == "https://audits.sherlock.xyz/contests/123"


def test_plaintext_message_extraction():
    _embed, plain = parse_messages(_msgs())
    assert plain.platform == "Code4rena"              # from message author
    assert plain.name.startswith("New audit competition")  # first line of content
    assert plain.url == "https://code4rena.com/audits/2026-06-acme"  # link from text


def test_empty_input():
    assert parse_messages([]) == []
