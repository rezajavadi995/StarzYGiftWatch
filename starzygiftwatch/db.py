from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import DEFAULT_INTERVAL, validate_interval

SCHEMA_VERSION = 1


def connect(path: str) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS gifts(id TEXT PRIMARY KEY, snapshot TEXT NOT NULL, missing_count INTEGER NOT NULL DEFAULT 0, updated_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS events(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              fingerprint TEXT NOT NULL UNIQUE,
              gift_id TEXT,
              event_type TEXT NOT NULL,
              payload TEXT NOT NULL,
              alertable INTEGER NOT NULL DEFAULT 1,
              sent_at REAL,
              attempts INTEGER NOT NULL DEFAULT 0,
              next_attempt_at REAL NOT NULL DEFAULT 0,
              created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS health(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """
    )
    conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version',?)", (str(SCHEMA_VERSION),))
    conn.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('watcher_enabled','1')")
    conn.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('poll_interval',?)", (str(DEFAULT_INTERVAL),))


def get_setting(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return None if row is None else row["value"]


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    with transaction(conn):
        conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, value))


def watcher_enabled(conn: sqlite3.Connection) -> bool:
    return get_setting(conn, "watcher_enabled") != "0"


def set_watcher_enabled(conn: sqlite3.Connection, enabled: bool) -> None:
    set_setting(conn, "watcher_enabled", "1" if enabled else "0")


def poll_interval(conn: sqlite3.Connection) -> int:
    return validate_interval(int(get_setting(conn, "poll_interval") or DEFAULT_INTERVAL))


def set_poll_interval(conn: sqlite3.Connection, seconds: int) -> None:
    set_setting(conn, "poll_interval", str(validate_interval(seconds)))


def current_snapshots(conn: sqlite3.Connection) -> dict[str, dict]:
    return {r["id"]: json.loads(r["snapshot"]) for r in conn.execute("SELECT id,snapshot FROM gifts")}


def pending_events(conn: sqlite3.Connection, now: float | None = None) -> list[sqlite3.Row]:
    now = time.time() if now is None else now
    return list(conn.execute("SELECT * FROM events WHERE alertable=1 AND sent_at IS NULL AND next_attempt_at<=? ORDER BY id", (now,)))


def mark_sent(conn: sqlite3.Connection, event_id: int) -> None:
    with transaction(conn):
        conn.execute("UPDATE events SET sent_at=? WHERE id=?", (time.time(), event_id))


def mark_retry(conn: sqlite3.Connection, event_id: int, delay: float) -> None:
    with transaction(conn):
        conn.execute("UPDATE events SET attempts=attempts+1,next_attempt_at=? WHERE id=?", (time.time() + delay, event_id))


def set_health(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO health(key,value) VALUES(?,?)", (key, value))


def set_health_many(conn: sqlite3.Connection, values: dict[str, str]) -> None:
    with transaction(conn):
        for key, value in values.items():
            set_health(conn, key, value)


def get_health(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM health WHERE key=?", (key,)).fetchone()
    return default if row is None else row["value"]


def record_runtime_status(conn: sqlite3.Connection, status: str, message: str = "") -> None:
    set_health_many(conn, {"runtime_status": status, "runtime_message": message, "runtime_updated_at": str(time.time())})


def record_poll_success(conn: sqlite3.Connection, gift_count: int, new_event_ids: list[int]) -> None:
    updates = {"last_success": str(time.time()), "gift_count": str(gift_count), "runtime_status": "OK", "runtime_message": ""}
    if new_event_ids:
        row = conn.execute("SELECT gift_id FROM events WHERE id=?", (new_event_ids[0],)).fetchone()
        if row:
            updates["last_new_gift_id"] = row["gift_id"] or ""
    set_health_many(conn, updates)


def record_poll_failure(conn: sqlite3.Connection, message: str) -> None:
    safe = message[:500]
    set_health_many(conn, {"last_error": safe, "last_error_at": str(time.time()), "runtime_status": "POLL_ERROR", "runtime_message": safe})


def needs_configuration(conn: sqlite3.Connection, bot_token: str, admin_id: int | None) -> bool:
    missing = []
    if not bot_token:
        missing.append("BOT_TOKEN")
    if not admin_id:
        missing.append("ADMIN_ID")
    if missing:
        record_runtime_status(conn, "NEEDS_CONFIGURATION", "missing " + ",".join(missing))
        return True
    return False
