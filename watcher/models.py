"""Normalized data model shared across sources, store, and notifier."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone


def iso_to_s(value) -> int | None:
    """Convert an ISO-8601 timestamp (e.g. '2026-04-09T17:00:00.000Z') to epoch
    seconds. Returns None for missing/unparseable values.
    """
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def ms_to_s(value) -> int | None:
    """Convert an epoch-milliseconds value to epoch seconds.

    Returns None for missing/zero values (e.g. perpetual bounties with no start).
    """
    try:
        ms = int(value)
    except (TypeError, ValueError):
        return None
    if ms <= 0:
        return None
    return ms // 1000


_MONEY_RE = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")


def parse_pot_size(raw) -> float | None:
    """Parse a pot-size string like '$15000.0' or '$1,500' into a float.

    Returns None when no numeric amount is present (e.g. 'N/A', None, '').
    """
    if raw is None:
        return None
    match = _MONEY_RE.search(str(raw))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def make_id(url: str | None, platform: str, name: str) -> str:
    """Stable identifier for a contest.

    Prefers the canonical URL (unique per contest). Falls back to a hash of
    platform+name when a URL is missing.
    """
    if url:
        return url.strip()
    digest = hashlib.sha1(f"{platform}::{name}".encode("utf-8")).hexdigest()[:16]
    return f"{platform.lower()}:{digest}"


@dataclass
class Contest:
    id: str
    platform: str
    name: str
    url: str
    description: str = ""
    pot_size_raw: str | None = None
    pot_size_usd: float | None = None
    sloc: str | None = None
    start_ts: int | None = None  # epoch seconds UTC, or None for no scheduled start
    end_ts: int | None = None
    invite_only: bool | None = None
    language: str | None = None
    source: str = "dailywarden"
    # "contest" = time-boxed (has a start; eligible for t24h alerts).
    # "bounty"  = perpetual (no start; only ever produces `new` alerts).
    kind: str = "contest"
    # Display-only provenance (epoch seconds): when the program first went live
    # and when its scope/rewards were last updated. Shown in alerts when present.
    listed_ts: int | None = None
    updated_ts: int | None = None

    def seconds_until_start(self, now_ts: int) -> int | None:
        if self.start_ts is None:
            return None
        return self.start_ts - now_ts

    @staticmethod
    def _fmt(ts: int) -> str:
        dt_utc = datetime.fromtimestamp(ts, timezone.utc)
        dt_local = dt_utc.astimezone()
        return f"{dt_utc:%Y-%m-%d %H:%M UTC} ({dt_local:%Y-%m-%d %H:%M %Z})"

    def start_human(self) -> str:
        """Render the start time in both UTC and local time for emails."""
        if self.start_ts is None:
            return "no scheduled start (perpetual)"
        return self._fmt(self.start_ts)

    def end_human(self) -> str:
        """Render the end time in both UTC and local time. '' when no end."""
        if self.end_ts is None:
            return ""
        return self._fmt(self.end_ts)
