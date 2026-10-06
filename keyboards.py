"""Клавиатуры бота (меню и inline-кнопки сценария записи)."""

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


def main_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="📅 Записаться"), KeyboardButton(text="💰 Прайс")],
        [KeyboardButton(text="⭐ Отзывы"), KeyboardButton(text="📍 Контакты")],
    ]
    if is_admin:
        rows.append([KeyboardButton(text="⚙️ Управление")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def services_keyboard(services: list[dict]) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(
            text=f"{s['название']} — {s['цена']} ₽",
            callback_data=f"s:{i}",
        )]
        for i, s in enumerate(services)
        if s.get("включена")
    ]
    buttons.append([InlineKeyboardButton(text="↩️ В меню", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def days_keyboard(days: list) -> InlineKeyboardMarkup:
    from schedule import human_day

    buttons = [
        [InlineKeyboardButton(text=human_day(d), callback_data=f"d:{d.isoformat()}")]
        for d in days
    ]
    buttons.append([InlineKeyboardButton(text="↩️ К услугам", callback_data="back:s")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def times_keyboard(times: list[str]) -> InlineKeyboardMarkup:
    row: list[InlineKeyboardButton] = []
    rows: list[list[InlineKeyboardButton]] = []
    for t in times:
        row.append(InlineKeyboardButton(text=t, callback_data=f"t:{t}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="↩️ К датам", callback_data="back:d")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить запись", callback_data="ok")],
        [InlineKeyboardButton(text="🔄 Начать заново", callback_data="back:s")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu")],
    ])
