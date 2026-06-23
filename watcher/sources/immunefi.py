"""Immunefi source: perpetual bug bounties + time-boxed audit competitions.

Immunefi has no public JSON API; its pages are Next.js apps that embed program
data in the RSC stream as (escaped) JSON. We unescape one level and pull each
program object out with a JSON decoder.

One source, two surfaces (fetched together, merged):
  - /bug-bounty/        : perpetual bounties     (kind="bounty", no start; `new` only)
  - /audit-competition/ : time-boxed competitions (kind="contest", launchDate/endDate
                          -> start_ts/end_ts; t24h-eligible)

If one surface fails to parse but the other works, we return what we have and
log the failure; only if BOTH surfaces fail does fetch() raise SourceError. This
parses embedded markup rather than an API, so it is more fragile than
Sherlock/dailywarden.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.request

from ..models import Contest, iso_to_s
from .base import SourceError

_BASE = "https://immunefi.com"
_BOUNTY_URL = "https://immunefi.com/bug-bounty/"
_COMP_URL = "https://immunefi.com/audit-competition/"
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120 Safari/537.36"
)

_OBJ_START = re.compile(r'\{"contentfulId"')


def _iter_programs(html: str):
    """Yield each embedded program object (dict) from an Immunefi page."""
    text = html.replace('\\"', '"')
    decoder = json.JSONDecoder()
    for m in _OBJ_START.finditer(text):
        try:
            obj, _ = decoder.raw_decode(text, m.start())
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("slug"):
            yield obj


def _name(obj: dict) -> str:
    project = (obj.get("project") or "").strip()
    if project:
        return project
    slug = obj.get("slug", "")
    return slug.replace("-", " ").replace("_", " ").strip().title() or slug


def _pot(obj: dict):
    amount = obj.get("maxBounty") or obj.get("rewardsPool")
    try:
        usd = float(amount)
    except (TypeError, ValueError):
        return None, None
    if usd <= 0:
        return None, None
    return f"${usd:,.0f}", usd


def parse_bounties(html: str) -> list[Contest]:
    """Parse the bug-bounty board into perpetual bounty records."""
    out: dict[str, Contest] = {}
    for obj in _iter_programs(html):
        url = obj.get("url") or ""
        if not url.startswith("/bug-bounty/"):
            continue
        slug = obj["slug"]
        if slug in out:
            continue
        pot_raw, pot_usd = _pot(obj)
        out[slug] = Contest(
            id=f"immunefi:{slug}",
            platform="Immunefi",
            name=_name(obj),
            url=_BASE + url,
            pot_size_raw=pot_raw,
            pot_size_usd=pot_usd,
            start_ts=None,  # perpetual bounty
            invite_only=bool(obj["inviteOnly"]) if "inviteOnly" in obj else None,
            source="immunefi",
            kind="bounty",
            listed_ts=iso_to_s(obj.get("launchDate")),
            updated_ts=iso_to_s(obj.get("updatedDate")),
        )
    if not out:
        raise SourceError(
            "immunefi: no bounty objects found in page (embedding may have changed)"
        )
    return list(out.values())


def parse_competitions(html: str, now_ts: int) -> list[Contest]:
    """Parse audit competitions into time-boxed contest records.

    Keeps only competitions that have not yet ended. Uses ``launchDate`` as the
    start and ``endDate`` as the end (both ISO-8601). Raises SourceError if no
    competition objects are present at all (format changed).
    """
    found_any = False
    out: dict[str, Contest] = {}
    for obj in _iter_programs(html):
        url = obj.get("url") or ""
        if not url.startswith("/audit-competition/"):
            continue
        found_any = True
        slug = obj["slug"]
        if slug in out:
            continue
        end_ts = iso_to_s(obj.get("endDate"))
        if end_ts is not None and end_ts <= now_ts:
            continue  # already finished
        pot_raw, pot_usd = _pot(obj)
        out[slug] = Contest(
            id=f"immunefi:comp:{slug}",
            platform="Immunefi",
            name=_name(obj),
            url=_BASE + url,
            pot_size_raw=pot_raw,
            pot_size_usd=pot_usd,
            start_ts=iso_to_s(obj.get("launchDate")),
            end_ts=end_ts,
            invite_only=bool(obj["inviteOnly"]) if "inviteOnly" in obj else None,
            source="immunefi",
            kind="contest",
            updated_ts=iso_to_s(obj.get("updatedDate")),
        )
    if not found_any:
        raise SourceError(
            "immunefi: no audit-competition objects found (embedding may have changed)"
        )
    return list(out.values())


def _fetch_html(url: str, timeout: int) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        raise SourceError(f"immunefi: fetch failed ({url}): {exc}") from exc


class ImmunefiSource:
    """Fetches both Immunefi surfaces and returns the merged list.

    Resilient: a failure on one surface is logged and the other's results are
    still returned; SourceError is raised only when BOTH surfaces fail.
    """

    name = "immunefi"

    def __init__(self, bounty_url: str = _BOUNTY_URL, comp_url: str = _COMP_URL,
                 timeout: int = 30):
        self.bounty_url = bounty_url
        self.comp_url = comp_url
        self.timeout = timeout

    def fetch(self) -> list[Contest]:
        now_ts = int(time.time())
        contests: list[Contest] = []
        errors: list[str] = []

        try:
            contests.extend(parse_bounties(_fetch_html(self.bounty_url, self.timeout)))
        except SourceError as exc:
            errors.append(f"bounties: {exc}")

        try:
            contests.extend(
                parse_competitions(_fetch_html(self.comp_url, self.timeout), now_ts)
            )
        except SourceError as exc:
            errors.append(f"competitions: {exc}")

        if len(errors) == 2:
            raise SourceError("immunefi: both surfaces failed — " + " | ".join(errors))
        if errors:
            print(f"[immunefi] partial failure (other surface OK): {errors[0]}",
                  file=sys.stderr)
        return contests
