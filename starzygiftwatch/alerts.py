from __future__ import annotations

import asyncio
import json
import random

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter

from . import db


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
            db.mark_retry(conn, row["id"], float(exc.retry_after))
        except Exception:
            delay = min(300, 2 ** min(row["attempts"] + 1, 8)) + random.uniform(0, 1)
            db.mark_retry(conn, row["id"], delay)
        else:
            db.mark_sent(conn, row["id"])
            sent += 1
    return sent


async def alert_loop(conn, bot: Bot, admin_id: int | None) -> None:
    while True:
        await deliver_pending_once(conn, bot, admin_id)
        await asyncio.sleep(1)
