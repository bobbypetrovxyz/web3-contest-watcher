"""SQLite persistence: known contests, sent notifications, and meta markers.

The notifications table's composite primary key (contest_id, alert_type) is the
idempotency guard — each alert type fires at most once per contest, regardless
of how often the cron job runs.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager

from .models import Contest

_SCHEMA = """
CREATE TABLE IF NOT EXISTS contests (
    id            TEXT PRIMARY KEY,
    platform      TEXT,
    name          TEXT,
    url           TEXT,
    pot_size_raw  TEXT,
    pot_size_usd  REAL,
    sloc          TEXT,
    start_ts      INTEGER,
    end_ts        INTEGER,
    invite_only   INTEGER,
    language      TEXT,
    source        TEXT,
    kind          TEXT,
    first_seen_ts INTEGER,
    last_seen_ts  INTEGER,
    raw_json      TEXT
);

CREATE TABLE IF NOT EXISTS notifications (
    contest_id TEXT,
    alert_type TEXT,
    sent_ts    INTEGER,
    PRIMARY KEY (contest_id, alert_type)
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


class Store:
    def __init__(self, path: str):
        self.path = path
        with self._conn() as conn:
            conn.executescript(_SCHEMA)
            self._migrate(conn)

    @staticmethod
    def _migrate(conn) -> None:
        """Add columns introduced after the initial schema, for older DBs."""
        cols = {row[1] for row in conn.execute("PRAGMA table_info(contests)")}
        for col in ("source", "kind"):
            if col not in cols:
                conn.execute(f"ALTER TABLE contests ADD COLUMN {col} TEXT")

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ---- contests -------------------------------------------------------
    def is_empty(self) -> bool:
        with self._conn() as conn:
            (count,) = conn.execute("SELECT COUNT(*) FROM contests").fetchone()
        return count == 0

    def contest_exists(self, contest_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM contests WHERE id = ?", (contest_id,)
            ).fetchone()
        return row is not None

    def _row(self, c: Contest) -> tuple:
        return (
            c.id, c.platform, c.name, c.url, c.pot_size_raw, c.pot_size_usd,
            c.sloc, c.start_ts, c.end_ts,
            None if c.invite_only is None else int(c.invite_only),
            c.language, c.source, c.kind,
        )

    def upsert_contest(self, c: Contest, now_ts: int) -> None:
        """Insert a new contest or refresh an existing one's mutable fields."""
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO contests (
                    id, platform, name, url, pot_size_raw, pot_size_usd, sloc,
                    start_ts, end_ts, invite_only, language, source, kind,
                    first_seen_ts, last_seen_ts, raw_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    platform=excluded.platform,
                    name=excluded.name,
                    url=excluded.url,
                    pot_size_raw=excluded.pot_size_raw,
                    pot_size_usd=excluded.pot_size_usd,
                    sloc=excluded.sloc,
                    start_ts=excluded.start_ts,
                    end_ts=excluded.end_ts,
                    invite_only=excluded.invite_only,
                    language=excluded.language,
                    source=excluded.source,
                    kind=excluded.kind,
                    last_seen_ts=excluded.last_seen_ts,
                    raw_json=excluded.raw_json
                """,
                (*self._row(c), now_ts, now_ts, json.dumps(c.__dict__, default=str)),
            )

    def seed(self, contests: list[Contest], now_ts: int) -> int:
        """Record all contests as seen WITHOUT emitting 'new' alerts.

        Used on the first run (empty DB) or via --seed to avoid an email storm.
        """
        for c in contests:
            self.upsert_contest(c, now_ts)
        return len(contests)

    # ---- notifications --------------------------------------------------
    def already_notified(self, contest_id: str, alert_type: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM notifications WHERE contest_id = ? AND alert_type = ?",
                (contest_id, alert_type),
            ).fetchone()
        return row is not None

    def record_notification(self, contest_id: str, alert_type: str, now_ts: int) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO notifications (contest_id, alert_type, sent_ts) "
                "VALUES (?,?,?)",
                (contest_id, alert_type, now_ts),
            )

    # ---- meta (failure-email throttle) ----------------------------------
    def get_meta_int(self, key: str) -> int | None:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        try:
            return int(row[0])
        except (TypeError, ValueError):
            return None

    def set_meta_int(self, key: str, value: int) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value)),
            )

    # ---- per-source seeding ---------------------------------------------
    # When a brand-new source is enabled on an already-populated DB, all of its
    # listings would otherwise fire as `new`. We seed each source once (silently)
    # the first time we see it, tracked here, so only later additions alert.
    _SEEDED_KEY = "seeded_sources"

    def get_seeded_sources(self) -> set[str]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM meta WHERE key = ?", (self._SEEDED_KEY,)
            ).fetchone()
        if row is None:
            return set()
        try:
            return set(json.loads(row[0]))
        except (TypeError, ValueError):
            return set()

    def mark_sources_seeded(self, names) -> None:
        seeded = self.get_seeded_sources() | set(names)
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (self._SEEDED_KEY, json.dumps(sorted(seeded))),
            )
