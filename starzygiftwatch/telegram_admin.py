from __future__ import annotations

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from . import db


def build_router(conn, admin_id: int | None) -> Router:
    router = Router()

    def allowed(user) -> bool:
        return bool(admin_id and user and user.id == admin_id)

    def panel() -> str:
        gifts = conn.execute("SELECT COUNT(*) c FROM gifts").fetchone()["c"]
        pending = conn.execute("SELECT COUNT(*) c FROM events WHERE alertable=1 AND sent_at IS NULL").fetchone()["c"]
        last = conn.execute("SELECT value FROM health WHERE key='last_success'").fetchone()
        return f"Watcher: {'ON' if db.watcher_enabled(conn) else 'OFF'}\nInterval: {db.poll_interval(conn)}s\nGifts: {gifts}\nPending alerts: {pending}\nLast success: {(last['value'] if last else 'never')}"

    def kb() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="ON", callback_data="watch:on"), InlineKeyboardButton(text="OFF", callback_data="watch:off")],
            [InlineKeyboardButton(text="Current gifts", callback_data="show:gifts"), InlineKeyboardButton(text="Recent changes", callback_data="show:events")],
            [InlineKeyboardButton(text="Test alert", callback_data="test:alert"), InlineKeyboardButton(text="Rebuild baseline", callback_data="rebuild:confirm")],
        ])

    @router.message(Command("start", "admin"))
    async def start(message: types.Message):
        if not allowed(message.from_user):
            return
        await message.answer(panel(), reply_markup=kb())

    @router.callback_query()
    async def cb(callback: types.CallbackQuery):
        if not allowed(callback.from_user):
            await callback.answer("Unauthorized", show_alert=False)
            return
        data = callback.data or ""
        if data == "watch:on":
            db.set_watcher_enabled(conn, True)
        elif data == "watch:off":
            db.set_watcher_enabled(conn, False)
        elif data == "show:gifts":
            rows = conn.execute("SELECT id FROM gifts ORDER BY id LIMIT 50").fetchall()
            await callback.message.answer("Gifts:\n" + "\n".join(r["id"] for r in rows))
        elif data == "show:events":
            rows = conn.execute("SELECT event_type,gift_id FROM events ORDER BY id DESC LIMIT 10").fetchall()
            await callback.message.answer("Recent:\n" + "\n".join(f"{r['event_type']} {r['gift_id']}" for r in rows))
        elif data == "test:alert":
            await callback.message.answer("StarzYGiftWatch test alert")
        elif data == "rebuild:confirm":
            await callback.message.answer("Baseline rebuild requires CLI confirmation in v1 safe mode.")
        await callback.message.edit_text(panel(), reply_markup=kb())
        await callback.answer()

    return router
