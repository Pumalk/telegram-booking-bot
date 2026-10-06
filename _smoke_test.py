"""Offline smoke tests for config loading, SQLite booking, slots, and reminders."""

import asyncio
import shutil
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from config_loader import load_config
from db import Database, SlotUnavailable
from handlers_admin import build_admin_router
from handlers_user import build_user_router
import schedule as sched
from reminders import check_reminders
import texts


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))


def main():
    temp = tempfile.TemporaryDirectory()
    tmp = Path(temp.name)
    client_path = tmp / "config" / "клиенты" / "тест" / "конфиг.yaml"
    client_path.parent.mkdir(parents=True)
    niche_dir = tmp / "config" / "ниши"
    niche_dir.mkdir(parents=True)
    shutil.copy(BASE_DIR / "config" / "ниши" / "бровист.yaml", niche_dir / "бровист.yaml")
    source = (BASE_DIR / "config" / "клиенты" / "анна-брови" / "конфиг.example.yaml").read_text(
        encoding="utf-8"
    )
    source = source.replace(
        '"ВСТАВЬТЕ_ТОКЕН_ОТ_BotFather"', '"123456:TESTTOKEN"'
    ).replace("админы: [0]", "админы: [123456789]")
    client_path.write_text(source, encoding="utf-8")
    cfg = load_config(client_path)
    router_db = Database(":memory:")
    build_admin_router(cfg, router_db)
    build_user_router(cfg, router_db)

    assert cfg["клиент"] == "anna-brovi"
    assert cfg["ниша"] == "бровист"
    assert cfg["название_студии"] == "Моя студия"
    assert cfg["запись"]["рабочие_часы"] == "10:00-19:00"
    assert cfg["запись"]["шаг_слота_мин"] == 30
    services = [service for service in cfg["услуги"] if service.get("включена")]
    assert len(services) == 4
    assert services[0]["цена"] == 900
    print("1. Загрузка и слияние YAML-конфигов: OK")

    db = Database(tmp / "bookings.sqlite3")
    booking_id = db.add_booking(
        user_id=111,
        username="client",
        client_name="Тест",
        service="Коррекция бровей",
        price=900,
        duration_min=30,
        day="2030-01-15",
        time="12:00",
    )
    assert db.get_booking(booking_id)["prepayment"] == "none"
    try:
        db.add_booking(
            user_id=222,
            username="another",
            client_name="Другой",
            service="Другая услуга",
            price=1000,
            duration_min=60,
            day="2030-01-15",
            time="12:00",
        )
    except SlotUnavailable:
        pass
    else:
        raise AssertionError("Пересекающуюся запись ошибочно удалось создать")
    assert db.cancel_booking(booking_id)
    assert db.get_booking(booking_id)["status"] == "cancelled"
    assert not db.cancel_booking(booking_id)
    print("2. SQLite: запись, блокировка пересечения и отмена: OK")

    day = date(2030, 1, 15)
    slots = sched.slots_for_day(cfg, db, day, 30)
    assert slots[0] == "10:00" and slots[-1] == "18:30" and len(slots) == 18
    db.add_booking(
        user_id=1,
        username="",
        client_name="",
        service="Услуга",
        price=1,
        duration_min=30,
        day=day.isoformat(),
        time="12:00",
    )
    slots = sched.slots_for_day(cfg, db, day, 30)
    assert "12:00" not in slots and "12:30" in slots
    db.block_slot(day.isoformat(), "10:00")
    assert "10:00" not in sched.slots_for_day(cfg, db, day, 30)
    db.block_day("2030-01-16")
    assert db.is_day_blocked("2030-01-16")
    assert not sched.slots_for_day(cfg, db, date(2030, 1, 16), 30)
    assert not sched.slots_for_day(cfg, db, date(2030, 1, 20), 30)
    print("3. Расписание: рабочие часы, длительность и блокировки: OK")

    class FixedNow(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2030, 1, 14, 8, 0, 0)

    import reminders

    original_datetime = reminders.datetime
    reminders.datetime = FixedNow
    reminder_db = Database(tmp / "reminders.sqlite3")
    reminder_24_id = reminder_db.add_booking(
        user_id=222,
        username="",
        client_name="Клиент",
        service="Тест",
        price=1,
        duration_min=30,
        day="2030-01-15",
        time="04:00",
    )
    reminder_2_id = reminder_db.add_booking(
        user_id=333,
        username="",
        client_name="Клиент",
        service="Тест",
        price=1,
        duration_min=30,
        day="2030-01-14",
        time="09:30",
    )
    bot = FakeBot()
    asyncio.run(check_reminders(bot, cfg, reminder_db))
    assert reminder_db.get_booking(reminder_24_id)["reminded_24"] == 1
    assert reminder_db.get_booking(reminder_2_id)["reminded_24"] == 1
    assert reminder_db.get_booking(reminder_2_id)["reminded_2"] == 1
    assert len(bot.sent) == 3
    asyncio.run(check_reminders(bot, cfg, reminder_db))
    assert len(bot.sent) == 3
    reminders.datetime = original_datetime
    print("4. Напоминания за 24ч/2ч без повторов: OK")

    assert "900 ₽" in texts.price_text(cfg)
    assert "Контакты" in texts.contacts_text(cfg)
    summary = texts.booking_summary(cfg, services[0], "2030-01-15", "12:00")
    assert "12:00" in summary and "900 ₽" in summary
    print("5. Тексты меню и подтверждения: OK")

    db.close()
    reminder_db.close()
    router_db.close()
    temp.cleanup()
    print("\nВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
