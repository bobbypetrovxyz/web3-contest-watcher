"""Cantina source — bounties and competitions from cantina.xyz.

No public API; the opportunity pages are a Next.js app that embeds opportunity
objects in the RSC stream as (escaped) JSON. Each carries `id`, `name`, `kind`
(`public_bounty` / `private_bounty` / `public_contest` / ...), `status`
(`live` / `judging` / ...), `currencyCode`, `totalRewardPot`, `url`, and a nested
`timeframe` of `{start, end}` (ISO-8601; bounties have `end: null`).

One source, two pages (bounties + competitions), fetched together and merged
(de-duplicated by id, since the pages embed overlapping sets):
  - kind contains "contest"  -> kind="contest", start/end from timeframe (t24h)
  - otherwise (bounty)       -> kind="bounty", perpetual (no start; `new` only)

Note: we parse the server-embedded set (the top opportunities by reward). Items
loaded later client-side may not appear; this is best-effort like the other
HTML-scraped sources. Resilient: raises only if BOTH pages fail.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request

from ..models import Contest, iso_to_s
from .base import SourceError

_BOUNTIES_URL = "https://cantina.xyz/opportunities/bounties"
_COMP_URL = "https://cantina.xyz/opportunities/competitions"
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120 Safari/537.36"
)
# Statuses that mean the opportunity is over / not joinable.
_SKIP_STATUS = {"judging", "finished", "closed", "ended", "completed", "cancelled"}
_USD_CURRENCIES = {"USDC", "USDT", "DAI", "USD", "USDC.E", "BUSD"}


def _pot(amount, currency):
    try:
        val = float(amount)
    except (TypeError, ValueError):
        return None, None
    if val <= 0:
        return None, None
    cur = (currency or "").strip()
    raw = f"{val:,.0f} {cur}".strip()
    usd = val if cur.upper() in _USD_CURRENCIES else None
    return raw, usd


def _iter_opportunities(html: str) -> dict:
    """Extract embedded opportunity objects (dict id -> object)."""
    text = html.replace('\\"', '"')
    decoder = json.JSONDecoder()
    out: dict = {}
    idx = 0
    while True:
        brace = text.find("{", idx)
        if brace < 0:
            break
        try:
            obj, end = decoder.raw_decode(text, brace)
        except json.JSONDecodeError:
            idx = brace + 1
            continue
        if isinstance(obj, dict) and obj.get("id") and "timeframe" in obj and "status" in obj:
            out[obj["id"]] = obj
            idx = end
        else:
            idx = brace + 1
    return out


def parse_opportunities(htmls: list[str], now_ts: int) -> list[Contest]:
    """Normalize Cantina opportunity pages into Contest records.

    Skips over/judging opportunities and already-ended contests. Raises
    SourceError only if no opportunity objects are found at all.
    """
    merged: dict = {}
    for html in htmls:
        merged.update(_iter_opportunities(html))
    if not merged:
        raise SourceError("cantina: no opportunity objects found (format may have changed)")

    out: list[Contest] = []
    for o in merged.values():
        if (o.get("status") or "").lower() in _SKIP_STATUS:
            continue
        kind_raw = (o.get("kind") or "").lower()
        is_contest = "contest" in kind_raw
        tf = o.get("timeframe") or {}
        start_ts = iso_to_s(tf.get("start"))
        end_ts = iso_to_s(tf.get("end"))
        if is_contest and end_ts is not None and end_ts <= now_ts:
            continue  # already-ended contest
        pot_raw, pot_usd = _pot(o.get("totalRewardPot"), o.get("currencyCode"))
        out.append(
            Contest(
                id=f"cantina:{o['id']}",
                platform="Cantina",
                name=o.get("name") or "(untitled)",
                url=o.get("url") or "",
                pot_size_raw=pot_raw,
                pot_size_usd=pot_usd,
                start_ts=start_ts if is_contest else None,
                end_ts=end_ts if is_contest else None,
                invite_only=True if "private" in kind_raw else None,
                source="cantina",
                kind="contest" if is_contest else "bounty",
                # For perpetual bounties, surface when it went live ("Live since").
                listed_ts=None if is_contest else start_ts,
            )
        )
    return out


def _fetch_html(url: str, timeout: int) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        raise SourceError(f"cantina: fetch failed ({url}): {exc}") from exc


class CantinaSource:
    name = "cantina"

    def __init__(self, bounties_url: str = _BOUNTIES_URL, comp_url: str = _COMP_URL,
                 timeout: int = 30):
        self.bounties_url = bounties_url
        self.comp_url = comp_url
        self.timeout = timeout

    def fetch(self) -> list[Contest]:
        now_ts = int(time.time())
        htmls: list[str] = []
        errors: list[str] = []
        for label, url in (("bounties", self.bounties_url), ("competitions", self.comp_url)):
            try:
                htmls.append(_fetch_html(url, self.timeout))
            except SourceError as exc:
                errors.append(f"{label}: {exc}")
        if len(errors) == 2:
            raise SourceError("cantina: both pages failed — " + " | ".join(errors))
        if errors:
            print(f"[cantina] partial failure (other page OK): {errors[0]}", file=sys.stderr)
        return parse_opportunities(htmls, now_ts)
