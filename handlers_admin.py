"""
Админ-режим мастера: команды управления расписанием и записями.
Работает только для ID из списка cfg["админы"].
"""

import logging
import re
from datetime import date, timedelta

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import Message

log = logging.getLogger(__name__)

HELP_TEXT = """⚙️ Панель управления

/bookings — ближайшие записи
/block_day 2026-10-05 — закрыть день (выходной)
/open_day 2026-10-05 — снова открыть день
/block_slot 2026-10-05 18:00 — закрыть конкретное время
/open_slot 2026-10-05 18:00 — открыть время
/cancel 3 — отменить запись №3

Дату указывайте в формате ГГГГ-ММ-ДД, «сегодня» или «завтра»."""


def _parse_day(raw: str) -> str | None:
    raw = raw.strip().lower()
    if raw == "сегодня":
        return date.today().isoformat()
    if raw == "завтра":
        return (date.today() + timedelta(days=1)).isoformat()
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        return None


def build_admin_router(cfg: dict, db) -> Router:
    router = Router()
    router.message.filter(F.from_user.id.in_(cfg["админы"]))

    def _need_args(message: Message, n: int, usage: str) -> list[str] | None:
        parts = (message.text or "").split(maxsplit=n)
        if len(parts) < n + 1:
            return None
        return parts[1:]

    @router.message(F.text == "⚙️ Управление")
    @router.message(Command("admin", "help"))
    async def admin_panel(message: Message):
        await message.answer(HELP_TEXT)

    @router.message(Command("bookings"))
    async def list_bookings(message: Message):
        rows = db.upcoming_active()
        if not rows:
            await message.answer("📋 Ближайших записей нет.")
            return
        lines = ["📋 Ближайшие записи:", ""]
        for b in rows:
            lines.append(
                f"№{b['id']} — {b['day'][8:]}.{b['day'][5:7]} {b['time']} — "
                f"{b['service']} — {b['client_name']}"
                + (f" (@{b['username']})" if b["username"] else "")
            )
        await message.answer("\n".join(lines))

    @router.message(Command("block_day"))
    async def cmd_block_day(message: Message):
        args = _need_args(message, 1, "/block_day 2026-10-05")
        day = _parse_day(args[0]) if args else None
        if not day:
            await message.answer("Напишите: /block_day 2026-10-05 (или «сегодня», «завтра»).")
            return
        db.block_day(day)
        await message.answer(f"✅ День {day} закрыт для записи.")

    @router.message(Command("open_day"))
    async def cmd_unblock_day(message: Message):
        args = _need_args(message, 1, "/open_day 2026-10-05")
        day = _parse_day(args[0]) if args else None
        if not day:
            await message.answer("Напишите: /open_day 2026-10-05 (или «сегодня», «завтра»).")
            return
        db.unblock_day(day)
        await message.answer(f"✅ День {day} снова открыт (слоты этого дня разблокированы).")

    @router.message(Command("block_slot"))
    async def cmd_block_slot(message: Message):
        args = _need_args(message, 2, "/block_slot 2026-10-05 18:00")
        if not args:
            await message.answer("Напишите: /закрыть_слот 2026-10-05 18:00")
            return
        day = _parse_day(args[0])
        time = args[1] if len(args) > 1 else ""
        if not day or not _valid_time(time):
            await message.answer("Формат: /block_slot 2026-10-05 18:00")
            return
        db.block_slot(day, time)
        await message.answer(f"✅ Слот {day} {time} закрыт.")

    @router.message(Command("open_slot"))
    async def cmd_unblock_slot(message: Message):
        args = _need_args(message, 2, "/open_slot 2026-10-05 18:00")
        if not args:
            await message.answer("Напишите: /открыть_слот 2026-10-05 18:00")
            return
        day = _parse_day(args[0])
        time = args[1] if len(args) > 1 else ""
        if not day or not _valid_time(time):
            await message.answer("Формат: /open_slot 2026-10-05 18:00")
            return
        db.unblock_slot(day, time)
        await message.answer(f"✅ Слот {day} {time} открыт.")

    @router.message(Command("cancel"))
    async def cmd_cancel(message: Message):
        args = _need_args(message, 1, "/cancel 3")
        if not args or not args[0].isdigit():
            await message.answer("Напишите: /cancel 3 (номер записи из /bookings).")
            return
        booking_id = int(args[0])
        booking = db.get_booking(booking_id)
        if not booking:
            await message.answer("Запись с таким номером не найдена.")
            return
        if not db.cancel_booking(booking_id):
            await message.answer("Эта запись уже отменена.")
            return
        await message.answer(f"✅ Запись №{booking_id} отменена.")
        try:
            await message.bot.send_message(
                booking["user_id"],
                f"К сожалению, ваша запись №{booking_id} ({booking['service']}, "
                f"{booking['day']} {booking['time']}) отменена мастером. "
                f"Для уточнений напишите: {cfg['контакты'].get('телефон') or 'в разделе Контакты'}.",
            )
        except TelegramAPIError:
            log.exception("Не удалось уведомить клиента об отмене записи №%s", booking_id)

    return router


def _valid_time(value: str) -> bool:
    return re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value) is not None
