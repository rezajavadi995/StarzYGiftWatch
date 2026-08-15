from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramRetryAfter

from . import db
from .alerts import alert_loop, retry_delay
from .config import load_config
from .telegram_admin import build_router
from .watcher import watcher_loop

LOGGER = logging.getLogger(__name__)


async def telegram_admin_loop(dp: Dispatcher, bot: Bot) -> None:
    failures = 0
    while True:
        try:
            await dp.start_polling(bot)
            failures = 0
        except TelegramRetryAfter as exc:
            failures += 1
            delay = retry_delay(failures, exc.retry_after)
            LOGGER.warning("Telegram admin polling rate limited; retrying in %.1fs", delay)
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            failures += 1
            delay = retry_delay(failures)
            LOGGER.exception("Telegram admin polling failed; retrying in %.1fs: %s", delay, type(exc).__name__)
            await asyncio.sleep(delay)


async def amain() -> None:
    cfg = load_config()
    logging.basicConfig(level=getattr(logging, cfg.log_level.upper(), logging.INFO))
    conn = db.connect(cfg.database_path)
    db.init_db(conn)
    if db.needs_configuration(conn, cfg.bot_token, cfg.admin_id):
        LOGGER.warning("StarzYGiftWatch status NEEDS_CONFIGURATION; run `watch` to set BOT_TOKEN and ADMIN_ID")
        return
    bot = Bot(cfg.bot_token)
    dp = Dispatcher()
    dp.include_router(build_router(conn, cfg.admin_id))
    await asyncio.gather(watcher_loop(conn, bot), alert_loop(conn, bot, cfg.admin_id), telegram_admin_loop(dp, bot))


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
