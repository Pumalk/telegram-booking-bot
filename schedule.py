"""
Генерация доступных дат и слотов времени из конфига + БД.

Два источника занятости:
  1. Внутренний: записи и блокировки из локальной SQLite (реализовано).
  2. Внешний онлайн-календарь — ЗАГЛУШКА (см. busy_from_external_calendar).
"""

from datetime import date, datetime, timedelta

DAY_TO_WEEKDAY = {"пн": 0, "вт": 1, "ср": 2, "чт": 3, "пт": 4, "сб": 5, "вс": 6}
WEEKDAY_TO_DAY_RU = {v: k for k, v in DAY_TO_WEEKDAY.items()}
WEEKDAY_NAMES = ["понедельник", "вторник", "среда", "четверг",
                 "пятница", "суббота", "воскресенье"]


# ===== ЗАГЛУШКА: ОНЛАЙН-КАЛЕНДАРЬ =====
# Тариф 1: режим "мой_календарь" (Google/Яндекс Calendar) НЕ реализован.
# Эта функция-заглушка всегда возвращает пустое множество «занятых» слотов.
# Для продвинутой версии: OAuth + API календаря, см. config.запись.календарь_источник.
def busy_from_external_calendar(cfg: dict, day: date) -> set[str]:
    return set()


def working_weekdays(cfg: dict) -> set[int]:
    return {DAY_TO_WEEKDAY[d] for d in cfg["запись"]["рабочие_дни"]}


def parse_hours(hours: str) -> tuple[int, int]:
    """'10:00-20:00' -> (600, 1200) в минутах от начала суток."""
    start, end = hours.split("-")
    sh, sm = map(int, start.split(":"))
    eh, em = map(int, end.split(":"))
    return sh * 60 + sm, eh * 60 + em


def fmt_minutes(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def human_day(day: date) -> str:
    """2026-10-05 -> 'понедельник, 05.10'"""
    return f"{WEEKDAY_NAMES[day.weekday()]}, {day.strftime('%d.%m')}"


def next_open_days(cfg: dict, db, count: int = 8) -> list[date]:
    """Ближайшие рабочие дни, не заблокированные мастером."""
    days: list[date] = []
    allowed = working_weekdays(cfg)
    cursor = date.today()
    while len(days) < count and (cursor - date.today()).days < 60:
        if cursor.weekday() in allowed and not db.is_day_blocked(cursor.isoformat()):
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


def _ranges_overlap(a_start: int, a_len: int, b_start: int, b_len: int) -> bool:
    return a_start < b_start + b_len and b_start < a_start + a_len


def slots_for_day(cfg: dict, db, day: date, duration_min: int) -> list[str]:
    """
    Свободные слоты дня с учётом:
    - рабочих часов и шага из конфига,
    - активных записей из БД (пересечение по длительности),
    - слотов, закрытых мастером,
    - ЗАГЛУШКИ внешнего календаря (пока всегда пусто).
    """
    if day.weekday() not in working_weekdays(cfg) or db.is_day_blocked(day.isoformat()):
        return []

    start_min, end_min = parse_hours(cfg["запись"]["рабочие_часы"])
    step = int(cfg["запись"]["шаг_слота_мин"])
    day_iso = day.isoformat()

    blocked = db.blocked_slots_on(day_iso)
    blocked |= busy_from_external_calendar(cfg, day)

    taken: list[tuple[int, int]] = []
    for b in db.active_on_day(day_iso):
        bh, bm = map(int, b["time"].split(":"))
        taken.append((bh * 60 + bm, int(b["duration_min"])))

    slots = []
    t = start_min
    now = datetime.now()
    if day == now.date():
        now_min = now.hour * 60 + now.minute
        t = max(t, ((now_min + step - 1) // step) * step)
    while t + duration_min <= end_min:
        conflicts = any(
            _ranges_overlap(t, duration_min, b_start, b_len)
            for b_start, b_len in taken
        )
        if not conflicts and fmt_minutes(t) not in blocked:
            slots.append(fmt_minutes(t))
        t += step
    return slots
