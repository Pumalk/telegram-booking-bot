"""
Клиентская часть бота: приветствие, меню, сценарий записи
(услуга → дата → время → подтверждение), прайс, отзывы, контакты.
"""

import logging
from datetime import date as date_cls

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import keyboards as kb
import schedule as sched
from db import SlotUnavailable
from texts import booking_summary, price_text, reviews_text, contacts_text, greeting_text

log = logging.getLogger(__name__)


class Booking(StatesGroup):
    service = State()
    day = State()
    time = State()
    confirm = State()


def enabled_services(cfg: dict) -> list[dict]:
    return [s for s in cfg["услуги"] if s.get("включена")]


def build_user_router(cfg: dict, db) -> Router:
    router = Router()

    def is_admin(user_id: int) -> bool:
        return user_id in cfg["админы"]

    # ---------- /start и меню ----------

    @router.message(CommandStart())
    async def cmd_start(message: Message, state: FSMContext):
        await state.clear()
        await message.answer(
            greeting_text(cfg),
            reply_markup=kb.main_menu(is_admin(message.from_user.id)),
        )

    @router.message(F.text == "💰 Прайс")
    async def show_price(message: Message):
        await message.answer(price_text(cfg))

    @router.message(F.text == "⭐ Отзывы")
    async def show_reviews(message: Message):
        if not cfg["модули"]["отзывы"].get("включено", True):
            await message.answer("Отзывы скоро появятся! ⭐")
            return
        await message.answer(reviews_text(cfg))

    @router.message(F.text == "📍 Контакты")
    async def show_contacts(message: Message):
        await message.answer(contacts_text(cfg))

    # ---------- сценарий записи ----------

    @router.message(F.text == "📅 Записаться")
    async def start_booking(message: Message, state: FSMContext):
        services = enabled_services(cfg)
        await state.set_state(Booking.service)
        await message.answer(
            "Выберите услугу:",
            reply_markup=kb.services_keyboard(services),
        )

    @router.callback_query(Booking.service, F.data == "menu")
    @router.callback_query(Booking.day, F.data == "menu")
    @router.callback_query(Booking.time, F.data == "menu")
    @router.callback_query(Booking.confirm, F.data == "menu")
    async def back_to_menu(query: CallbackQuery, state: FSMContext):
        await state.clear()
        await query.message.edit_text("Хорошо! Выберите раздел в меню 👇")
        await query.answer()

    @router.callback_query(Booking.service, F.data == "back:s")
    @router.callback_query(Booking.time, F.data == "back:d")
    async def step_back(query: CallbackQuery, state: FSMContext):
        # возврат на шаг выбора услуги
        await state.set_state(Booking.service)
        await query.message.edit_text(
            "Выберите услугу:",
            reply_markup=kb.services_keyboard(enabled_services(cfg)),
        )
        await query.answer()

    @router.callback_query(Booking.service, F.data.startswith("s:"))
    async def pick_service(query: CallbackQuery, state: FSMContext):
        services = enabled_services(cfg)
        try:
            idx = int(query.data.split(":")[1])
            service = services[idx]
        except (ValueError, IndexError):
            await query.answer("Услуга не найдена. Начните запись заново.", show_alert=True)
            await state.clear()
            return
        await state.update_data(service=service)

        days = sched.next_open_days(cfg, db)
        if not days:
            await query.message.edit_text(
                "К сожалению, свободных дней пока нет. Напишите мастеру — "
                f"{cfg['контакты'].get('телефон') or 'через контакты в меню'}."
            )
            await state.clear()
            await query.answer()
            return
        await state.set_state(Booking.day)
        await query.message.edit_text(
            f"Услуга: {service['название']} ({service['длительность_мин']} мин, "
            f"{service['цена']} ₽)\n\nВыберите день:",
            reply_markup=kb.days_keyboard(days),
        )
        await query.answer()

    @router.callback_query(Booking.day, F.data == "back:s")
    async def back_to_services(query: CallbackQuery, state: FSMContext):
        await state.set_state(Booking.service)
        await query.message.edit_text(
            "Выберите услугу:",
            reply_markup=kb.services_keyboard(enabled_services(cfg)),
        )
        await query.answer()

    @router.callback_query(Booking.day, F.data.startswith("d:"))
    async def pick_day(query: CallbackQuery, state: FSMContext):
        day_iso = query.data.split(":")[1]
        try:
            day = date_cls.fromisoformat(day_iso)
        except ValueError:
            await query.answer("Дата некорректна. Выберите день заново.", show_alert=True)
            return
        data = await state.get_data()
        if day not in sched.next_open_days(cfg, db, count=60):
            await query.answer("Эта дата больше недоступна.", show_alert=True)
            return
        service = data["service"]

        slots = sched.slots_for_day(cfg, db, day, service["длительность_мин"])
        if not slots:
            await query.answer("На этот день всё занято, выберите другой.", show_alert=True)
            return
        await state.update_data(day_iso=day_iso)
        await state.set_state(Booking.time)
        await query.message.edit_text(
            f"{service['название']} — {sched.human_day(day)}\n\nВыберите время:",
            reply_markup=kb.times_keyboard(slots),
        )
        await query.answer()

    @router.callback_query(Booking.time, F.data == "back:d")
    async def back_to_days(query: CallbackQuery, state: FSMContext):
        days = sched.next_open_days(cfg, db)
        await state.set_state(Booking.day)
        await query.message.edit_text("Выберите день:", reply_markup=kb.days_keyboard(days))
        await query.answer()

    @router.callback_query(Booking.time, F.data.startswith("t:"))
    async def pick_time(query: CallbackQuery, state: FSMContext):
        time = query.data.split(":")[1]
        data = await state.get_data()
        day = date_cls.fromisoformat(data["day_iso"])
        if time not in sched.slots_for_day(
            cfg, db, day, data["service"]["длительность_мин"]
        ):
            await query.answer("Это время больше недоступно. Выберите другое.", show_alert=True)
            return
        await state.update_data(time=time)
        await state.set_state(Booking.confirm)
        await query.message.edit_text(
            booking_summary(cfg, data["service"], data["day_iso"], time),
            reply_markup=kb.confirm_keyboard(),
        )
        await query.answer()

    @router.callback_query(Booking.confirm, F.data == "back:s")
    async def restart_booking(query: CallbackQuery, state: FSMContext):
        await state.set_state(Booking.service)
        await query.message.edit_text(
            "Выберите услугу:",
            reply_markup=kb.services_keyboard(enabled_services(cfg)),
        )
        await query.answer()

    @router.callback_query(Booking.confirm, F.data == "ok")
    async def confirm_booking(query: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        service, day_iso, time = data["service"], data["day_iso"], data["time"]

        # финальная проверка, что слот ещё свободен
        day = date_cls.fromisoformat(day_iso)
        if time not in sched.slots_for_day(cfg, db, day, service["длительность_мин"]):
            await query.answer("Это время только что заняли. Выберите другое.", show_alert=True)
            await state.set_state(Booking.time)
            slots = sched.slots_for_day(cfg, db, day, service["длительность_мин"])
            await query.message.edit_text(
                "Выберите другое время:",
                reply_markup=kb.times_keyboard(slots),
            )
            return

        user = query.from_user
        try:
            booking_id = db.add_booking(
                user_id=user.id,
                username=user.username or "",
                client_name=user.full_name,
                service=service["название"],
                price=service["цена"],
                duration_min=service["длительность_мин"],
                day=day_iso,
                time=time,
            )
        except SlotUnavailable:
            slots = sched.slots_for_day(cfg, db, day, service["длительность_мин"])
            await state.set_state(Booking.time)
            await query.message.edit_text(
                "Это время только что заняли. Выберите другое:",
                reply_markup=kb.times_keyboard(slots),
            )
            await query.answer("Время уже занято.", show_alert=True)
            return
        await state.clear()

        await query.message.edit_text(
            f"✅ Вы записаны!\n\n"
            f"{service['название']}\n"
            f"📅 {sched.human_day(day)} в {time}\n"
            f"📍 {cfg.get('адрес') or 'адрес уточните у мастера'}\n\n"
            f"Напомним о визите за 24 часа и за 2 часа. Ждём вас! 💛"
        )
        await query.answer()

        # уведомление мастера
        admin_msg = (
            f"🔔 Новая запись №{booking_id}\n"
            f"👤 {user.full_name} (@{user.username or 'без username'})\n"
            f"💅 {service['название']} — {service['цена']} ₽\n"
            f"📅 {sched.human_day(day)} в {time}"
        )
        for admin_id in cfg["админы"]:
            try:
                await query.bot.send_message(admin_id, admin_msg)
            except TelegramAPIError:
                log.exception("Не удалось отправить мастеру уведомление о записи №%s", booking_id)

    # ---------- прочее ----------

    @router.message()
    async def fallback(message: Message):
        await message.answer(
            "Выберите раздел меню 👇",
            reply_markup=kb.main_menu(is_admin(message.from_user.id)),
        )

    return router
