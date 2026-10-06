"""Текстовые шаблоны сообщений. Всё собирается из конфига — без правки кода."""

from datetime import date as date_cls

import schedule as sched


def greeting_text(cfg: dict) -> str:
    parts = [(cfg.get("приветствие") or "Привет! 👋").strip()]
    if cfg.get("описание"):
        parts.append(cfg["описание"].strip())
    parts.append("Выберите раздел в меню 👇")
    return "\n\n".join(parts)


def price_text(cfg: dict) -> str:
    lines = [f"💰 Прайс — {cfg.get('название_студии', '')}".strip(), ""]
    for s in cfg["услуги"]:
        if not s.get("включена"):
            continue
        lines.append(
            f"• {s['название']} — {s['цена']} ₽ ({s['длительность_мин']} мин)"
        )
    lines += ["", "Записаться можно в разделе «📅 Записаться»."]
    return "\n".join(lines)


def reviews_text(cfg: dict) -> str:
    lines = [f"⭐ Отзывы — {cfg.get('название_студии', '')}".strip(), ""]
    reviews = cfg.get("отзывы") or []
    if not reviews:
        return "Отзывы скоро появятся! ⭐"
    for r in reviews:
        lines.append(f"«{r}»")
        lines.append("")
    lines.append("Хотите так же? Жмите «📅 Записаться» 💛")
    return "\n".join(lines)


def contacts_text(cfg: dict) -> str:
    c = cfg.get("контакты", {})
    lines = [f"📍 Контакты — {cfg.get('название_студии', '')}".strip(), ""]
    if cfg.get("адрес"):
        lines.append(f"Адрес: {cfg['адрес']}")
    if c.get("телефон"):
        lines.append(f"Телефон: {c['телефон']}")
    if c.get("instagram"):
        lines.append(f"Instagram: {c['instagram']}")
    lines.append("")
    lines.append("Записаться онлайн: «📅 Записаться»")
    return "\n".join(lines)


def booking_summary(cfg: dict, service: dict, day_iso: str, time: str) -> str:
    day = date_cls.fromisoformat(day_iso)
    return (
        "Проверьте запись:\n\n"
        f"💅 Услуга: {service['название']}\n"
        f"⏱ Длительность: {service['длительность_мин']} мин\n"
        f"💰 Цена: {service['цена']} ₽\n"
        f"📅 Дата: {sched.human_day(day)}\n"
        f"🕐 Время: {time}\n"
        f"📍 Адрес: {cfg.get('адрес') or 'уточните у мастера'}\n\n"
        "Всё верно?"
    )
