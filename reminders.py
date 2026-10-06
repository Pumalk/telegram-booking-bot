"""
Напоминания клиентам за 24 часа и за 2 часа до визита.

Фоновая asyncio-задача раз в минуту проверяет активные записи.
Время — локальное время компьютера, где запущен бот.
"""

import asyncio
import logging
from datetime import datetime

from aiogram.exceptions import TelegramAPIError

log = logging.getLogger(__name__)

CHECK_INTERVAL_SEC = 60


async def send_reminder(bot, cfg: dict, booking: dict, hours: int) -> bool:
    appointment = datetime.strptime(
        f"{booking['day']} {booking['time']}", "%Y-%m-%d %H:%M"
    )
    day_delta = (appointment.date() - datetime.now().date()).days
    day_label = {
        0: "сегодня",
        1: "завтра",
    }.get(day_delta, appointment.strftime("%d.%m"))
    if hours == 24:
        when = f"{day_label}, {booking['time']}"
        emoji = "⏰"
    else:
        when = f"{day_label}, {booking['time']}"
        emoji = "🔔"

    text = (
        f"{emoji} Напоминание о записи!\n\n"
        f"💅 {booking['service']}\n"
        f"📅 {when}\n"
        f"📍 {cfg.get('адрес') or 'адрес уточните у мастера'}\n\n"
        f"Ждём вас! 💛"
    )
    try:
        await bot.send_message(booking["user_id"], text)
    except TelegramAPIError:
        log.exception("Не удалось отправить напоминание по записи %s", booking["id"])
        return False
    return True


async def check_reminders(bot, cfg: dict, db) -> None:
    mods = cfg.get("модули", {}).get("напоминания", {})
    if not mods.get("включено", True):
        return

    now = datetime.now()
    for b in db.upcoming_active(limit=100):
        try:
            start = datetime.strptime(f"{b['day']} {b['time']}", "%Y-%m-%d %H:%M")
        except ValueError:
            continue
        seconds_left = (start - now).total_seconds()
        if seconds_left <= 0:
            continue

        if (
            mods.get("за_24ч", True)
            and not b["reminded_24"]
            and seconds_left <= 24 * 3600
        ):
            if await send_reminder(bot, cfg, b, hours=24):
                db.mark_reminded(b["id"], "reminded_24")

        if (
            mods.get("за_2ч", True)
            and not b["reminded_2"]
            and seconds_left <= 2 * 3600
        ):
            if await send_reminder(bot, cfg, b, hours=2):
                db.mark_reminded(b["id"], "reminded_2")


async def reminder_loop(bot, cfg: dict, db) -> None:
    while True:
        try:
            await check_reminders(bot, cfg, db)
        except Exception:
            log.exception("Ошибка в цикле напоминаний")
        await asyncio.sleep(CHECK_INTERVAL_SEC)
