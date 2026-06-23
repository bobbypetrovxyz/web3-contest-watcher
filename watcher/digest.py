"""Email subject/body composition for each alert type."""

from __future__ import annotations

from datetime import datetime, timezone

from .models import Contest


def _pot(c: Contest) -> str:
    return c.pot_size_raw or "N/A"


def _date(ts: int | None) -> str | None:
    if ts is None:
        return None
    return f"{datetime.fromtimestamp(ts, timezone.utc):%Y-%m-%d}"


def _contest_block(c: Contest) -> str:
    label = {"bounty": "Bounty  ", "announcement": "Title   "}.get(c.kind, "Contest ")
    lines = [
        f"Platform : {c.platform}",
        f"{label} : {c.name}",
    ]
    if c.kind != "announcement":  # announcements carry no prize
        lines.append(f"Prize    : {_pot(c)}")
    # "Starts"/"Ends" are contest-only; perpetual bounties have no schedule.
    if c.start_ts is not None:
        lines.append(f"Starts   : {c.start_human()}")
    if c.end_ts is not None:
        lines.append(f"Ends     : {c.end_human()}")
    if c.sloc:
        lines.append(f"SLOC     : {c.sloc}")
    lines.append(f"URL      : {c.url}")
    live = _date(c.listed_ts)
    if live:
        lines.append(f"Live since: {live}")
    updated = _date(c.updated_ts)
    if updated:
        lines.append(f"Updated  : {updated}")
    if c.invite_only:
        lines.append("Note     : invite-only")
    if c.description:
        desc = c.description.strip()
        if len(desc) > 500:
            desc = desc[:500] + "…"
        lines.append("")
        lines.append(desc)
    return "\n".join(lines)


_LABELS = {
    "bounty": ("New Bounty", "bug bounty was listed"),
    "announcement": ("New Announcement", "announcement was posted"),
}


def new_alert(c: Contest) -> tuple[str, str]:
    label, phrase = _LABELS.get(c.kind, ("New Contest", "security contest was listed"))
    # Announcements have no prize; keep the subject clean.
    suffix = "" if c.kind == "announcement" else f" ({_pot(c)})"
    subject = f"[{label}] {c.platform}: {c.name}{suffix}"
    body = f"A new web3 {phrase}:\n\n" + _contest_block(c)
    return subject, body


def t24h_alert(c: Contest) -> tuple[str, str]:
    subject = f"[Starting soon] {c.platform}: {c.name} starts within 24h"
    body = (
        "A contest you're watching starts within the next 24 hours:\n\n"
        + _contest_block(c)
    )
    return subject, body


def source_failure_alert(failed: list[tuple[str, str]]) -> tuple[str, str]:
    """Warning when SOME sources failed but others still produced alerts."""
    names = ", ".join(name for name, _ in failed)
    subject = f"[Watcher warning] source(s) failed: {names}"
    details = "\n".join(f"- {name}: {err}" for name, err in failed)
    body = (
        "The watcher ran, but one or more sources could not be fetched/parsed.\n"
        "Alerts from the working sources were still sent. The failing source(s) "
        "may have changed format or been unreachable:\n\n"
        f"{details}\n\n"
        "(Repeat warnings for the same source are suppressed for ~24h.)"
    )
    return subject, body


def failure_alert(error: str) -> tuple[str, str]:
    subject = "[Watcher error] contest watcher could not fetch/parse its source"
    body = (
        "The web3 contest watcher failed to retrieve contest data on its last run.\n"
        "This usually means the source website changed its format, or was "
        "unreachable. The deterministic parser needs attention.\n\n"
        f"Details: {error}\n\n"
        "(Further failure emails are suppressed for ~24h to avoid spam.)"
    )
    return subject, body
