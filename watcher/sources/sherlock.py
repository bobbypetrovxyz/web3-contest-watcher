"""Sherlock audit-contest source.

Sherlock exposes a clean public JSON API at
``https://mainnet-contest.sherlock.xyz/contests`` (paginated). Each item carries
``starts_at``/``ends_at`` as epoch **seconds**, plus ``status``, ``title``,
``rewards``/``prize_pool``, ``short_description`` and ``id``. Contests are
time-boxed, so they get a ``start_ts`` and are eligible for t24h alerts.

We fetch a few pages (newest first) and keep only contests that have not yet
ended — finished/judging entries are not joinable and are filtered out.
"""

from __future__ import annotations

import json
import time
import urllib.request

from ..models import Contest
from .base import SourceError

_DEFAULT_URL = "https://mainnet-contest.sherlock.xyz/contests"
_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) web3-contest-watcher/1.0"
_CONTEST_URL = "https://audits.sherlock.xyz/contests/{id}"


def _to_int(value) -> int | None:
    """Sherlock timestamps are already epoch seconds; guard missing/zero."""
    try:
        secs = int(value)
    except (TypeError, ValueError):
        return None
    return secs if secs > 0 else None


def parse_contests(payloads: list[dict], now_ts: int) -> list[Contest]:
    """Normalize Sherlock API page payloads into Contest records.

    Keeps only contests that have not yet ended (``ends_at`` in the future or
    absent). Raises SourceError if the payload shape is unrecognizable.
    """
    contests: list[Contest] = []
    for page in payloads:
        if not isinstance(page, dict) or "items" not in page:
            raise SourceError("sherlock: response missing 'items' (API format changed)")
        items = page["items"]
        if not isinstance(items, list):
            raise SourceError("sherlock: 'items' is not a list")
        for item in items:
            if not isinstance(item, dict):
                continue
            cid = item.get("id")
            title = (item.get("title") or "").strip()
            if cid is None or not title:
                continue
            end_ts = _to_int(item.get("ends_at"))
            # Skip already-finished contests (not joinable).
            if end_ts is not None and end_ts <= now_ts:
                continue
            rewards = item.get("rewards") or item.get("prize_pool")
            pot_raw = None
            pot_usd = None
            if rewards is not None:
                try:
                    pot_usd = float(rewards)
                    pot_raw = f"${pot_usd:,.0f}"
                except (TypeError, ValueError):
                    pot_raw = str(rewards)
            contests.append(
                Contest(
                    id=f"sherlock:{cid}",
                    platform="Sherlock",
                    name=title,
                    url=_CONTEST_URL.format(id=cid),
                    description=(item.get("short_description") or "").strip(),
                    pot_size_raw=pot_raw,
                    pot_size_usd=pot_usd,
                    start_ts=_to_int(item.get("starts_at")),
                    end_ts=end_ts,
                    invite_only=bool(item.get("private")) if "private" in item else None,
                    source="sherlock",
                    kind="contest",
                )
            )
    return contests


class SherlockSource:
    name = "sherlock"

    def __init__(self, url: str = _DEFAULT_URL, timeout: int = 30, max_pages: int = 3):
        self.url = url
        self.timeout = timeout
        self.max_pages = max_pages

    def _get(self, page: int) -> dict:
        sep = "&" if "?" in self.url else "?"
        url = f"{self.url}{sep}page={page}"
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
        except Exception as exc:
            raise SourceError(f"sherlock: fetch failed (page {page}): {exc}") from exc
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise SourceError(f"sherlock: invalid JSON (page {page}): {exc}") from exc

    def fetch(self) -> list[Contest]:
        now_ts = int(time.time())
        payloads: list[dict] = []
        for page in range(1, self.max_pages + 1):
            data = self._get(page)
            payloads.append(data)
            if not data.get("has_next"):
                break
        return parse_contests(payloads, now_ts)
