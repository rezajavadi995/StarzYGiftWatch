from __future__ import annotations

import asyncio
import json
import logging
import random

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter

from . import db

LOGGER = logging.getLogger(__name__)


def retry_delay(attempt: int, retry_after: float | None = None, *, cap: float = 300.0) -> float:
    if retry_after is not None:
        return max(0.0, float(retry_after))
    return min(cap, 2 ** min(attempt, 8)) + random.uniform(0, 1)


def format_event(row) -> str:
    payload = json.loads(row["payload"])
    return f"StarzYGiftWatch {row['event_type']} gift={row['gift_id']}\n{json.dumps(payload, sort_keys=True, ensure_ascii=False)[:3000]}"


async def deliver_pending_once(conn, bot: Bot, admin_id: int | None) -> int:
    if not admin_id:
        return 0
    sent = 0
    for row in db.pending_events(conn):
        try:
            await bot.send_message(admin_id, format_event(row))
        except TelegramRetryAfter as exc:
            LOGGER.warning("Alert delivery rate limited for event %s; retrying in %.1fs", row["id"], float(exc.retry_after))
            db.mark_retry(conn, row["id"], retry_delay(row["attempts"] + 1, exc.retry_after))
        except Exception as exc:
            delay = retry_delay(row["attempts"] + 1)
            LOGGER.warning("Alert delivery failed for event %s; retrying in %.1fs: %s", row["id"], delay, type(exc).__name__)
            db.mark_retry(conn, row["id"], delay)
        else:
            db.mark_sent(conn, row["id"])
            sent += 1
    return sent


async def alert_loop(conn, bot: Bot, admin_id: int | None) -> None:
    failures = 0
    while True:
        try:
            await deliver_pending_once(conn, bot, admin_id)
            failures = 0
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            failures += 1
            delay = retry_delay(failures)
            LOGGER.exception("Alert worker loop error; continuing in %.1fs: %s", delay, type(exc).__name__)
            await asyncio.sleep(delay)
