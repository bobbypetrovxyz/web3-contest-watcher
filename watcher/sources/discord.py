"""Discord source — relays announcements followed into your own server.

Setup (one-time, by the operator): create a Discord bot, enable the Message
Content Intent, add it to a server you control, and use Discord's "Follow"
feature to cross-post platform announcement channels into a channel there. This
source then polls that channel via the REST API.

It runs in RELAY mode: each new message becomes one `new` announcement alert
(kind="announcement"). Announcements are free-form, so there is no reliable
start date — hence no t24h. Title/url/description/platform are extracted
best-effort from the message content and any embeds.

Stateless like the other sources: it fetches the most recent N messages per
channel and relies on the store for idempotency/seeding. N is capped (see
`limit`); if more than N arrive between runs the oldest are missed — logged, not
silent.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request

from ..models import Contest, iso_to_s
from .base import SourceError

_API = "https://discord.com/api/v10"
_USER_AGENT = "web3-contest-watcher (https://github.com/, 1.0)"
_URL_RE = re.compile(r"https?://[^\s|>)\]]+")


def _first_url(message: dict) -> str:
    """Best-effort canonical link: embed url, else first link in text/embeds."""
    for e in message.get("embeds") or []:
        if e.get("url"):
            return e["url"]
    haystack = [message.get("content") or ""]
    for e in message.get("embeds") or []:
        haystack.append(e.get("description") or "")
        for f in e.get("fields") or []:
            haystack.append(str(f.get("value") or ""))
    for text in haystack:
        m = _URL_RE.search(text)
        if m:
            return m.group(0)
    return ""


def _platform(message: dict) -> str:
    """Best-effort source name: embed author/footer, else message author."""
    for e in message.get("embeds") or []:
        name = (e.get("author") or {}).get("name")
        if name:
            return name.strip()
        footer = (e.get("footer") or {}).get("text")
        if footer:
            return footer.strip()
    author = (message.get("author") or {}).get("username")
    return author.strip() if author else "Discord"


def _title(message: dict) -> str:
    for e in message.get("embeds") or []:
        if e.get("title"):
            return e["title"].strip()
    content = (message.get("content") or "").strip()
    if content:
        first_line = content.splitlines()[0].strip()
        return (first_line[:140] + "…") if len(first_line) > 140 else first_line
    return "(announcement)"


def _description(message: dict) -> str:
    for e in message.get("embeds") or []:
        if e.get("description"):
            return e["description"].strip()
    return (message.get("content") or "").strip()


def parse_messages(messages: list[dict]) -> list[Contest]:
    """Relay a list of Discord message dicts into announcement records."""
    out: list[Contest] = []
    for m in messages:
        mid = m.get("id")
        if not mid:
            continue
        out.append(
            Contest(
                id=f"discord:{mid}",
                platform=_platform(m),
                name=_title(m),
                url=_first_url(m),
                description=_description(m),
                start_ts=None,            # announcements have no reliable schedule
                listed_ts=iso_to_s(m.get("timestamp")),
                source="discord",
                kind="announcement",
            )
        )
    return out


class DiscordSource:
    name = "discord"

    def __init__(self, token: str, channel_ids: str, timeout: int = 30, limit: int = 100):
        self.token = token
        self.channel_ids = [c.strip() for c in channel_ids.split(",") if c.strip()]
        self.timeout = timeout
        self.limit = limit

    def _get_channel(self, channel_id: str) -> list[dict]:
        url = f"{_API}/channels/{channel_id}/messages?limit={self.limit}"
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bot {self.token}",
            "User-Agent": _USER_AGENT,
        })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
        except Exception as exc:
            raise SourceError(f"discord: fetch failed (channel {channel_id}): {exc}") from exc
        if not isinstance(data, list):
            raise SourceError(f"discord: unexpected response for channel {channel_id}")
        return data

    def fetch(self) -> list[Contest]:
        if not self.token:
            raise SourceError("discord: DISCORD_BOT_TOKEN not set")
        if not self.channel_ids:
            raise SourceError("discord: DISCORD_CHANNEL_IDS not set")

        messages: list[dict] = []
        errors: list[str] = []
        for cid in self.channel_ids:
            try:
                msgs = self._get_channel(cid)
            except SourceError as exc:
                errors.append(str(exc))
                continue
            if len(msgs) >= self.limit:
                print(f"[discord] channel {cid} returned the full {self.limit}-message "
                      f"page; older messages this run may be missed.", file=sys.stderr)
            messages.extend(msgs)

        if errors and len(errors) == len(self.channel_ids):
            raise SourceError("discord: all channels failed — " + " | ".join(errors))
        if errors:
            print(f"[discord] partial failure (other channels OK): {errors[0]}",
                  file=sys.stderr)
        return parse_messages(messages)
