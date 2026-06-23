"""Smart Contract Hacking (SCH) aggregator source.

smartcontractshacking.com aggregates active audit contests + bug bounties across
platforms (HackenProof, Code4rena, CodeHawks, Cantina, Immunefi, ...). Its page
embeds every listing as `data-*` attributes on HTML elements — no API/pagination
needed:

  data-id, data-source (platform), data-name, data-status, data-type
  (audit_contest | bug_bounty), data-prize, data-max-bounty, data-start, data-end
  (ISO-8601), data-url (canonical platform URL), data-languages.

Value to us: SCH reaches platforms we can't scrape directly — notably HackenProof
(Cloudflare-gated; SCH solves that on its side) including its *bounties*, plus
Code4rena and CodeHawks. We therefore SKIP the platforms we already have richer
direct sources for (sherlock, cantina, immunefi) to avoid duplicate alerts that
wouldn't dedup (their direct ids are prefixed, not URL-based). HackenProof
listings use canonical URLs, so they dedup against dailywarden via run-level
id dedup.
"""

from __future__ import annotations

import html as _html
import re
import urllib.request

from ..models import Contest, iso_to_s, make_id, parse_pot_size
from .base import SourceError

_DEFAULT_URL = "https://smartcontractshacking.com/tools/web3-auditing-competitions-and-bug-bounties?status=active"
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120 Safari/537.36"
)
# Platforms we already cover with direct, richer sources (prefixed ids that would
# NOT dedup against SCH's URL-based ids) -> skip them here to avoid double alerts.
_SKIP_SOURCES = {"sherlock", "cantina", "immunefi"}
_DISPLAY = {
    "hackenproof": "HackenProof", "code4rena": "Code4rena", "codehawks": "CodeHawks",
    "sherlock": "Sherlock", "cantina": "Cantina", "immunefi": "Immunefi",
}
_LISTING_RE = re.compile(r'<[^>]*\bdata-name="[^"]*"[^>]*>')
_ATTR_RE = re.compile(r'(data-[a-z0-9-]+)="([^"]*)"')


def _amount(prize, max_bounty):
    p = parse_pot_size(prize) or 0
    m = parse_pot_size(max_bounty) or 0
    val = max(p, m)
    if val <= 0:
        return None, None
    return f"${val:,.0f}", val


def parse_listings(html: str, now_ts: int) -> list[Contest]:
    """Parse SCH `data-*` listing elements into Contest records.

    Skips platforms covered by direct sources, non-active rows, and ended
    contests. Raises SourceError if no listing elements are found.
    """
    tags = _LISTING_RE.findall(html)
    if not tags:
        raise SourceError("sch: no listing elements found (page format may have changed)")

    out: dict[str, Contest] = {}
    for tag in tags:
        a = {k: _html.unescape(v) for k, v in _ATTR_RE.findall(tag)}
        source = (a.get("data-source") or "").lower()
        if not source or source in _SKIP_SOURCES:
            continue
        if (a.get("data-status") or "").lower() not in ("", "active", "live", "upcoming"):
            continue
        url = (a.get("data-url") or "").strip()
        name = (a.get("data-name") or "").strip()
        if not (url and name):
            continue
        type_raw = (a.get("data-type") or "").lower()
        is_contest = "contest" in type_raw or "competition" in type_raw
        start_ts = iso_to_s(a.get("data-start"))
        end_ts = iso_to_s(a.get("data-end"))
        if is_contest and end_ts is not None and end_ts <= now_ts:
            continue  # ended contest
        pot_raw, pot_usd = _amount(a.get("data-prize"), a.get("data-max-bounty"))
        cid = make_id(url, source, name)  # canonical URL id -> dedups vs dailywarden
        if cid in out:
            continue
        out[cid] = Contest(
            id=cid,
            platform=_DISPLAY.get(source, source.title()),
            name=name,
            url=url,
            pot_size_raw=pot_raw,
            pot_size_usd=pot_usd,
            start_ts=start_ts if is_contest else None,
            end_ts=end_ts if is_contest else None,
            language=(a.get("data-languages") or None),
            source="sch",
            kind="contest" if is_contest else "bounty",
            listed_ts=None if is_contest else start_ts,
        )
    return list(out.values())


class SchSource:
    name = "sch"

    def __init__(self, url: str = _DEFAULT_URL, timeout: int = 30):
        self.url = url
        self.timeout = timeout

    def fetch(self) -> list[Contest]:
        import time
        req = urllib.request.Request(self.url, headers={"User-Agent": _USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                html = resp.read().decode("utf-8", errors="replace")
        except Exception as exc:
            raise SourceError(f"sch: fetch failed: {exc}") from exc
        return parse_listings(html, int(time.time()))
