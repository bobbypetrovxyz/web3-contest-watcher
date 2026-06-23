"""Source plugin seam.

A Source fetches a remote listing and returns normalized Contest records.
Adding a new contest site (V2) = implementing this protocol in a new module.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..models import Contest


class SourceError(Exception):
    """Raised when a source cannot fetch or parse its listing.

    run.py treats this (and an empty result) as a failure → failure email.
    """


@runtime_checkable
class Source(Protocol):
    name: str

    def fetch(self) -> list[Contest]:
        ...
