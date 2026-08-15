from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any, Iterable

from aiogram import Bot

from . import db

STABLE_FIELDS = {
    "id", "star_count", "upgrade_star_count", "is_limited", "is_sold_out", "is_premium",
    "total_count", "remaining_count", "personal_total_count", "personal_remaining_count",
    "background", "color", "variant", "publisher", "released_by", "sticker_file_id",
}


def _safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_safe(v) for v in value if _safe(v) is not None]
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in sorted(value.items()) if _safe(v) is not None and "file" not in str(k).lower()}
    if hasattr(value, "model_dump"):
        return _safe(value.model_dump(exclude_none=True))
    return None


def normalize_gift(gift: Any) -> dict[str, Any]:
    raw = _safe(gift)
    if not isinstance(raw, dict):
        raw = dict(gift)
    snap = {k: raw[k] for k in sorted(raw) if k in STABLE_FIELDS and raw.get(k) is not None}
    if "id" not in snap:
        raise ValueError("gift missing id")
    snap["id"] = str(snap["id"])
    return snap


def normalize_catalog(gifts: Iterable[Any]) -> dict[str, dict[str, Any]]:
    return {g["id"]: g for g in sorted((normalize_gift(x) for x in gifts), key=lambda x: x["id"])}


def fingerprint(event_type: str, gift_id: str, payload: dict[str, Any]) -> str:
    body = json.dumps({"type": event_type, "gift_id": gift_id, "payload": payload}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode()).hexdigest()


def _event(event_type: str, gift_id: str, payload: dict[str, Any], alertable: bool = True) -> tuple[str, str, dict, int]:
    return (fingerprint(event_type, gift_id, payload), event_type, payload, 1 if alertable else 0)


def diff_gift(old: dict, new: dict) -> list[tuple[str, str, dict, int]]:
    gid = new["id"]
    events = []
    for field in ("star_count", "upgrade_star_count", "total_count", "personal_total_count", "personal_remaining_count"):
        if old.get(field) != new.get(field):
            events.append(_event("CHANGE", gid, {"field": field, "old": old.get(field), "new": new.get(field)}))
    old_remaining, new_remaining = old.get("remaining_count"), new.get("remaining_count")
    if old_remaining != new_remaining:
        alert = not (isinstance(old_remaining, int) and isinstance(new_remaining, int) and new_remaining < old_remaining and new_remaining > 0)
        etype = "RESTOCK" if isinstance(old_remaining, int) and isinstance(new_remaining, int) and new_remaining > old_remaining else "SOLD_OUT" if new_remaining == 0 else "TELEMETRY"
        events.append(_event(etype, gid, {"field": "remaining_count", "old": old_remaining, "new": new_remaining}, alert))
    if bool(old.get("is_sold_out")) != bool(new.get("is_sold_out")):
        events.append(_event("SOLD_OUT" if new.get("is_sold_out") else "RESTOCK", gid, {"field": "is_sold_out", "old": old.get("is_sold_out"), "new": new.get("is_sold_out")}))
    ignored = {"remaining_count", "is_sold_out", "star_count", "upgrade_star_count", "total_count", "personal_total_count", "personal_remaining_count"}
    changed = {k: {"old": old.get(k), "new": new.get(k)} for k in sorted(set(old) | set(new)) if k not in ignored and old.get(k) != new.get(k)}
    if changed:
        events.append(_event("CHANGE", gid, {"fields": changed}))
    return events


def apply_catalog(conn, catalog: dict[str, dict[str, Any]]) -> list[int]:
    now = time.time()
    old = db.current_snapshots(conn)
    inserted: list[int] = []
    with db.transaction(conn):
        if not old:
            for gid, snap in catalog.items():
                conn.execute("INSERT OR REPLACE INTO gifts(id,snapshot,missing_count,updated_at) VALUES(?,?,0,?)", (gid, json.dumps(snap, sort_keys=True), now))
            conn.execute("INSERT OR REPLACE INTO health(key,value) VALUES('last_success',?)", (str(now),))
            return []
        for gid, snap in catalog.items():
            if gid not in old:
                events = [_event("NEW", gid, {"gift": snap})]
            else:
                events = diff_gift(old[gid], snap)
            for fp, etype, payload, alertable in events:
                cur = conn.execute("INSERT OR IGNORE INTO events(fingerprint,gift_id,event_type,payload,alertable,created_at) VALUES(?,?,?,?,?,?)", (fp, gid, etype, json.dumps(payload, sort_keys=True), alertable, now))
                if cur.rowcount:
                    inserted.append(cur.lastrowid)
            conn.execute("INSERT OR REPLACE INTO gifts(id,snapshot,missing_count,updated_at) VALUES(?,?,0,?)", (gid, json.dumps(snap, sort_keys=True), now))
        for gid in set(old) - set(catalog):
            row = conn.execute("SELECT missing_count FROM gifts WHERE id=?", (gid,)).fetchone()
            missing = (row["missing_count"] if row else 0) + 1
            if missing >= 2:
                payload = {"last_snapshot": old[gid]}
                fp = fingerprint("REMOVED", gid, payload)
                cur = conn.execute("INSERT OR IGNORE INTO events(fingerprint,gift_id,event_type,payload,alertable,created_at) VALUES(?,?,?,?,1,?)", (fp, gid, "REMOVED", json.dumps(payload, sort_keys=True), now))
                if cur.rowcount:
                    inserted.append(cur.lastrowid)
                conn.execute("DELETE FROM gifts WHERE id=?", (gid,))
            else:
                conn.execute("UPDATE gifts SET missing_count=?,updated_at=? WHERE id=?", (missing, now, gid))
        conn.execute("INSERT OR REPLACE INTO health(key,value) VALUES('last_success',?)", (str(now),))
    return inserted


async def fetch_catalog(bot: Bot) -> dict[str, dict[str, Any]]:
    gifts = await bot.get_available_gifts()
    items = getattr(gifts, "gifts", gifts)
    return normalize_catalog(items)


async def rebuild_baseline(conn, bot: Bot) -> None:
    catalog = await fetch_catalog(bot)  # network first, outside write txn
    now = time.time()
    with db.transaction(conn):
        conn.execute("DELETE FROM gifts")
        for gid, snap in catalog.items():
            conn.execute("INSERT INTO gifts(id,snapshot,missing_count,updated_at) VALUES(?,?,0,?)", (gid, json.dumps(snap, sort_keys=True), now))
        conn.execute("INSERT OR REPLACE INTO health(key,value) VALUES('last_success',?)", (str(now),))


async def watcher_loop(conn, bot: Bot) -> None:
    while True:
        if db.watcher_enabled(conn):
            catalog = await fetch_catalog(bot)
            apply_catalog(conn, catalog)
        await asyncio.sleep(db.poll_interval(conn))
