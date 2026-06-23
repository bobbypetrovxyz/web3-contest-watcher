"""Contest/bounty sources. Add a new site by implementing the Source protocol.

Enabled sources are selected via WATCHER_SOURCES (comma-separated names);
``build_sources`` instantiates them. Each source is fetched independently by the
runner, so one broken source never silences the others.
"""

from .base import Source, SourceError
from .cantina import CantinaSource
from .dailywarden import DailyWardenSource
from .discord import DiscordSource
from .immunefi import ImmunefiSource
from .sch import SchSource
from .sherlock import SherlockSource

__all__ = [
    "Source", "SourceError",
    "DailyWardenSource", "SherlockSource", "ImmunefiSource", "DiscordSource",
    "CantinaSource", "SchSource", "build_sources",
]


def build_sources(config) -> list[Source]:
    """Instantiate the sources named in config.sources (in order, de-duplicated)."""
    sources: list[Source] = []
    seen: set[str] = set()
    for raw in config.sources.split(","):
        name = raw.strip().lower()
        if not name or name in seen:
            continue
        seen.add(name)
        if name == "dailywarden":
            sources.append(DailyWardenSource(config.source_url))
        elif name == "sherlock":
            sources.append(SherlockSource())
        elif name == "immunefi":
            sources.append(ImmunefiSource())
        elif name == "cantina":
            sources.append(CantinaSource())
        elif name == "sch":
            sources.append(SchSource())
        elif name == "discord":
            sources.append(
                DiscordSource(config.discord_bot_token, config.discord_channel_ids)
            )
        else:
            raise SourceError(f"unknown source: {name!r} (check WATCHER_SOURCES)")
    if not sources:
        sources.append(DailyWardenSource(config.source_url))
    return sources
