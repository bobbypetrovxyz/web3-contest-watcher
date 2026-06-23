"""dailywarden.com source.

The homepage is a Next.js page that embeds all contest data in a
``<script id="__NEXT_DATA__">`` JSON blob at
``props.pageProps.contests.flattened``. We parse that blob directly rather than
the ``/_next/data/<buildId>/index.json`` endpoint, because the buildId changes
on every deploy and that endpoint returned an incomplete set.
"""

from __future__ import annotations

import json
import re
import urllib.request

from ..models import Contest, make_id, ms_to_s, parse_pot_size
from .base import SourceError

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)
_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) web3-contest-watcher/1.0"


def parse_contests(html: str) -> list[Contest]:
    """Parse dailywarden homepage HTML into Contest records.

    Raises SourceError if the embedded data structure is missing/changed.
    """
    match = _NEXT_DATA_RE.search(html)
    if not match:
        raise SourceError("dailywarden: __NEXT_DATA__ script blob not found")

    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise SourceError(f"dailywarden: __NEXT_DATA__ is not valid JSON: {exc}") from exc

    # contests.flattened = UPCOMING contests, which carry start/end dates and
    # drive both the `new` and `t24h` alerts. The sibling `contestsWithTracking`
    # array holds already-running/judging/ended competitions with no start date
    # and is intentionally out of V1 scope.
    try:
        flattened = data["props"]["pageProps"]["contests"]["flattened"]
    except (KeyError, TypeError) as exc:
        raise SourceError(
            "dailywarden: props.pageProps.contests.flattened path missing "
            "(site format may have changed)"
        ) from exc

    if not isinstance(flattened, list):
        raise SourceError("dailywarden: contests.flattened is not a list")

    contests: list[Contest] = []
    for item in flattened:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        url = (item.get("url") or "").strip()
        platform = (item.get("platform") or "Unknown").strip()
        if not name and not url:
            continue
        invite = item.get("inviteOnly")
        contests.append(
            Contest(
                id=make_id(url, platform, name),
                platform=platform,
                name=name,
                url=url,
                description=(item.get("description") or "").strip(),
                pot_size_raw=item.get("potSize"),
                pot_size_usd=parse_pot_size(item.get("potSize")),
                sloc=item.get("sloc"),
                start_ts=ms_to_s(item.get("startDate")),
                end_ts=ms_to_s(item.get("endDate")),
                invite_only=None if invite is None else bool(invite),
                language=item.get("language"),
                source="dailywarden",
            )
        )
    return contests


class DailyWardenSource:
    name = "dailywarden"

    def __init__(self, url: str, timeout: int = 30):
        self.url = url
        self.timeout = timeout

    def fetch(self) -> list[Contest]:
        req = urllib.request.Request(self.url, headers={"User-Agent": _USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                html = resp.read().decode("utf-8", errors="replace")
        except Exception as exc:  # network errors, timeouts, HTTP errors
            raise SourceError(f"dailywarden: fetch failed: {exc}") from exc
        return parse_contests(html)
