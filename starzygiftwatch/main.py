from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher

from . import db
from .alerts import alert_loop
from .config import load_config
from .telegram_admin import build_router
from .watcher import watcher_loop


async def amain() -> None:
    cfg = load_config()
    logging.basicConfig(level=getattr(logging, cfg.log_level.upper(), logging.INFO))
    conn = db.connect(cfg.database_path)
    db.init_db(conn)
    if not cfg.bot_token or not cfg.admin_id:
        logging.warning("BOT_TOKEN/ADMIN_ID missing; service initialized without polling")
        while True:
            await asyncio.sleep(3600)
    bot = Bot(cfg.bot_token)
    dp = Dispatcher()
    dp.include_router(build_router(conn, cfg.admin_id))
    await asyncio.gather(watcher_loop(conn, bot), alert_loop(conn, bot, cfg.admin_id), dp.start_polling(bot))


def main() -> None:
    asyncio.run(amain())

if __name__ == "__main__":
    main()
