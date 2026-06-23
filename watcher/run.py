"""One-shot entrypoint, invoked by cron every 8h.

Flow: fetch all enabled sources (failures isolated) -> seed any not-yet-seen
source silently -> detect new / t24h on the rest -> notify -> record.

Failure handling:
  - ALL sources fail (or all return empty) -> throttled failure alert, exit 1.
  - SOME sources fail -> alerts from the working ones still go out, plus a
    throttled per-source warning naming the broken one(s).
"""

from __future__ import annotations

import argparse
import sys
import time

from .config import FAILURE_EMAIL_THROTTLE_SECONDS, Config
from .digest import failure_alert, new_alert, source_failure_alert, t24h_alert
from .models import Contest
from .notifier import Notifier, build_notifier
from .sources import SourceError, build_sources
from .store import Store

_FAILURE_META_KEY = "last_failure_email_ts"


def due_for_t24h(c: Contest, now_ts: int, t24h_seconds: int) -> bool:
    secs = c.seconds_until_start(now_ts)
    return secs is not None and 0 < secs <= t24h_seconds


def detect(store: Store, contests: list[Contest], now_ts: int, t24h_seconds: int):
    """Return (new_contests, t24h_contests) based on current store state."""
    new_contests = [c for c in contests if not store.contest_exists(c.id)]
    t24h_contests = [
        c for c in contests
        if due_for_t24h(c, now_ts, t24h_seconds)
        and not store.already_notified(c.id, "t24h")
    ]
    return new_contests, t24h_contests


def process(
    store: Store,
    notifier: Notifier,
    contests: list[Contest],
    now_ts: int,
    t24h_seconds: int,
    dry_run: bool,
) -> dict:
    """Detect and deliver alerts. Persists state only when not a dry run."""
    new_contests, t24h_contests = detect(store, contests, now_ts, t24h_seconds)

    if not dry_run:
        for c in contests:
            store.upsert_contest(c, now_ts)

    for c in new_contests:
        subject, body = new_alert(c)
        notifier.send(subject, body)
        if not dry_run:
            store.record_notification(c.id, "new", now_ts)

    for c in t24h_contests:
        subject, body = t24h_alert(c)
        notifier.send(subject, body)
        if not dry_run:
            store.record_notification(c.id, "t24h", now_ts)

    return {"new": len(new_contests), "t24h": len(t24h_contests), "total": len(contests)}


def fetch_all(sources) -> tuple[list[Contest], list[tuple[str, str]], set[str]]:
    """Fetch every source independently. One failure never aborts the others.

    Returns (contests, failures, succeeded_names) where failures is a list of
    (source_name, error) and succeeded_names is the set of sources that fetched
    without error (even if they returned zero items).
    """
    contests: list[Contest] = []
    failures: list[tuple[str, str]] = []
    succeeded: set[str] = set()
    for s in sources:
        try:
            items = s.fetch()
        except SourceError as exc:
            failures.append((s.name, str(exc)))
            continue
        except Exception as exc:  # defensive: never let one source crash the run
            failures.append((s.name, f"unexpected error: {exc}"))
            continue
        succeeded.add(s.name)
        contests.extend(items)
    return contests, failures, succeeded


def dedupe_by_id(contests: list[Contest]) -> tuple[list[Contest], int]:
    """Drop cross-source duplicates (same id), keeping the first occurrence.

    Sources are merged in WATCHER_SOURCES order, so the earlier-listed source
    wins for a given id. Returns (deduped_list, dropped_count). Without this, two
    sources carrying the same listing (e.g. an aggregator and a native feed)
    would each fire a `new` alert for it in one run.
    """
    seen: set[str] = set()
    out: list[Contest] = []
    for c in contests:
        if c.id in seen:
            continue
        seen.add(c.id)
        out.append(c)
    return out, len(contests) - len(out)


def _send_throttled(
    store: Store, notifier: Notifier, meta_key: str,
    subject: str, body: str, now_ts: int,
) -> bool:
    """Send a message at most once per throttle window (keyed by meta_key)."""
    last = store.get_meta_int(meta_key)
    if last is not None and now_ts - last < FAILURE_EMAIL_THROTTLE_SECONDS:
        return False
    try:
        notifier.send(subject, body)
    except Exception as exc:  # don't mask the original failure
        print(f"[watcher] failed to send alert ({meta_key}): {exc}", file=sys.stderr)
        return False
    store.set_meta_int(meta_key, now_ts)
    return True


def maybe_send_failure(store: Store, notifier: Notifier, error: str, now_ts: int) -> bool:
    """Send the all-sources-failed alert at most once per throttle window."""
    subject, body = failure_alert(error)
    return _send_throttled(store, notifier, _FAILURE_META_KEY, subject, body, now_ts)


def warn_partial_failures(
    store: Store, notifier: Notifier, failures: list[tuple[str, str]], now_ts: int
) -> None:
    """Warn about sources that failed while others succeeded (per-source throttle)."""
    fresh = [
        (name, err) for name, err in failures
        if store.get_meta_int(f"last_source_fail:{name}") is None
        or now_ts - store.get_meta_int(f"last_source_fail:{name}") >= FAILURE_EMAIL_THROTTLE_SECONDS
    ]
    if not fresh:
        return
    subject, body = source_failure_alert(fresh)
    try:
        notifier.send(subject, body)
    except Exception as exc:
        print(f"[watcher] failed to send source warning: {exc}", file=sys.stderr)
        return
    for name, _ in fresh:
        store.set_meta_int(f"last_source_fail:{name}", now_ts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Web3 contest & bug-bounty watcher")
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Record all current contests as seen WITHOUT sending alerts.",
    )
    args = parser.parse_args(argv)

    config = Config.from_env()
    store = Store(config.db_path)
    notifier = build_notifier(config)
    sources = build_sources(config)
    now_ts = int(time.time())

    contests, failures, succeeded = fetch_all(sources)

    contests, dropped = dedupe_by_id(contests)
    if dropped:
        print(f"[watcher] deduped {dropped} cross-source duplicate listing(s).")

    # Every source failed (or none was enabled that worked): hard failure.
    if not succeeded:
        err = "; ".join(f"{n}: {e}" for n, e in failures) or "no sources produced data"
        sent = maybe_send_failure(store, notifier, err, now_ts)
        print(f"[watcher] ALL SOURCES FAILED: {err} (failure alert sent={sent})", file=sys.stderr)
        return 1

    # Sources succeeded but collectively returned nothing: treat as failure too.
    if not contests:
        sent = maybe_send_failure(store, notifier, "all sources returned 0 contests", now_ts)
        print(f"[watcher] EMPTY RESULT (failure alert sent={sent})", file=sys.stderr)
        if failures:
            warn_partial_failures(store, notifier, failures, now_ts)
        return 1

    # Dry run previews against current state and must never persist.
    if config.dry_run:
        result = process(store, notifier, contests, now_ts, config.t24h_seconds, True)
        print(
            f"[watcher] DRY RUN: {result['total']} contests; "
            f"{result['new']} new alert(s), {result['t24h']} t24h alert(s)."
        )
        return 0

    # Explicit --seed: record everything silently, mark all seen sources seeded.
    if args.seed:
        count = store.seed(contests, now_ts)
        store.mark_sources_seeded(succeeded)
        print(f"[watcher] seeded {count} contests from {sorted(succeeded)}; no alerts sent.")
        return 0

    # Per-source seeding: a source we've never recorded before (first run, or a
    # newly-enabled source) is seeded silently so its existing listings don't all
    # fire as `new`. Only already-seeded sources go through alert detection.
    seeded = store.get_seeded_sources()
    new_sources = succeeded - seeded
    if new_sources:
        to_seed = [c for c in contests if c.source in new_sources]
        store.seed(to_seed, now_ts)
        store.mark_sources_seeded(new_sources)
        print(f"[watcher] seeded {len(to_seed)} contests from new source(s) "
              f"{sorted(new_sources)}; no alerts for those.")

    to_process = [c for c in contests if c.source in seeded]
    result = process(
        store, notifier, to_process, now_ts, config.t24h_seconds, dry_run=False
    )
    print(
        f"[watcher] live: {result['total']} contests across {sorted(seeded)}; "
        f"{result['new']} new alert(s), {result['t24h']} t24h alert(s)."
    )

    if failures:
        warn_partial_failures(store, notifier, failures, now_ts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
