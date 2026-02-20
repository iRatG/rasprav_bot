"""
Хэндлеры клиентского сценария.

Сценарии:
  /start, "Меню"  → главное меню
  Записаться      → FSM: услуга → день → время → подтверждение
  Мои записи      → список + отмена
  Отписаться      → unsubscribe
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

import config as cfg
from db.models.appointment import Appointment, AppointmentStatus
from db.models.client import Client, ClientStatus
from db.models.event import Event
from db.models.master import Master
from db.models.master_service_price import MasterServicePrice
from db.models.service import Service
from bot.keyboards.client import (
    after_cancel_kb,
    booking_confirm_kb,
    cancel_confirm_kb,
    days_kb,
    main_menu_kb,
    my_appointments_kb,
    services_kb,
    slots_kb,
)
from services.appointments import SlotAlreadyTakenError, cancel_appointment, create_appointment
from services.notifications import send_booking_confirmation
from services.slots import get_available_dates, get_available_slots

TZ = ZoneInfo(cfg.TIMEZONE)
router = Router(name="client")

# ---------------------------------------------------------------------------
# FSM States для сценария записи
# ---------------------------------------------------------------------------

class BookingFSM(StatesGroup):
    choosing_service = State()
    choosing_day = State()
    choosing_time = State()
    confirming = State()


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

async def _get_or_create_client(session: AsyncSession, message: Message) -> Client:
    """Возвращает клиента из БД или создаёт нового."""
    stmt = select(Client).where(Client.tg_user_id == message.from_user.id)
    client = (await session.execute(stmt)).scalar_one_or_none()
    if client is None:
        client = Client(
            tg_user_id=message.from_user.id,
            tg_chat_id=message.chat.id,
            tg_status=ClientStatus.active,
        )
        session.add(client)
        await session.commit()
        await session.refresh(client)
    elif client.tg_status in (ClientStatus.blocked, ClientStatus.unsubscribed):
        # Реактивация
        client.tg_status = ClientStatus.active
        client.tg_status_updated_at = datetime.now(timezone.utc)
        session.add(Event(
            event_type="client_reactivated",
            client_id=client.id,
            actor_type="client",
            actor_id=client.id,
        ))
        await session.commit()
    return client


async def _get_master(session: AsyncSession) -> Master | None:
    """Возвращает первого активного мастера (MVP — один мастер)."""
    result = await session.execute(select(Master).limit(1))
    return result.scalar_one_or_none()


async def _get_active_services(session: AsyncSession) -> list[Service]:
    result = await session.execute(select(Service).where(Service.active.is_(True)))
    return result.scalars().all()


async def _get_price(session: AsyncSession, master_id: int, service_id: int):
    """Актуальная цена мастера на услугу (последняя по active_from)."""
    stmt = (
        select(MasterServicePrice)
        .where(
            and_(
                MasterServicePrice.master_id == master_id,
                MasterServicePrice.service_id == service_id,
            )
        )
        .order_by(MasterServicePrice.active_from.desc())
        .limit(1)
    )
    price_row = (await session.execute(stmt)).scalar_one_or_none()
    return price_row.price if price_row else None


async def _get_upcoming_appointments(session: AsyncSession, client_id: int) -> list[Appointment]:
    now = datetime.now(timezone.utc)
    stmt = (
        select(Appointment)
        .where(
            and_(
                Appointment.client_id == client_id,
                Appointment.status.in_([AppointmentStatus.booked, AppointmentStatus.confirmed]),
                Appointment.start_ts > now,
            )
        )
        .order_by(Appointment.start_ts)
    )
    return (await session.execute(stmt)).scalars().all()


def _fmt_appointment(apt: Appointment, service_name: str) -> str:
    local = apt.start_ts.astimezone(TZ)
    status_label = "✅ подтверждено" if apt.status == AppointmentStatus.confirmed else "⏳ ожидает"
    return (
        f"📋 <b>{service_name}</b>\n"
        f"📅 {local.strftime('%d.%m.%Y')} в {local.strftime('%H:%M')}\n"
        f"💰 {apt.price_snapshot} ₽  |  {status_label}"
    )


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------

@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    client = await _get_or_create_client(session, message)
    upcoming = await _get_upcoming_appointments(session, client.id)

    if upcoming:
        apt = upcoming[0]
        svc = (await session.execute(select(Service).where(Service.id == apt.service_id))).scalar_one()
        text = (
            f"👋 Добро пожаловать!\n\n"
            f"Ваша ближайшая запись:\n{_fmt_appointment(apt, svc.name)}"
        )
    else:
        text = "👋 Добро пожаловать! Запишитесь на удобное время."

    await message.answer(text, reply_markup=main_menu_kb(bool(upcoming)), parse_mode="HTML")


@router.callback_query(F.data == "menu")
async def cb_menu(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    client = await _get_or_create_client(session, callback.message)
    upcoming = await _get_upcoming_appointments(session, client.id)

    if upcoming:
        apt = upcoming[0]
        svc = (await session.execute(select(Service).where(Service.id == apt.service_id))).scalar_one()
        text = f"Ваша ближайшая запись:\n{_fmt_appointment(apt, svc.name)}"
    else:
        text = "Главное меню"

    await callback.message.edit_text(text, reply_markup=main_menu_kb(bool(upcoming)), parse_mode="HTML")
    await callback.answer()


# ---------------------------------------------------------------------------
# Сценарий записи
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "book_start")
async def cb_book_start(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    services = await _get_active_services(session)
    if not services:
        await callback.answer("Нет доступных услуг", show_alert=True)
        return

    await state.set_state(BookingFSM.choosing_service)
    await callback.message.edit_text(
        "Выберите услугу:",
        reply_markup=services_kb(services),
    )
    await callback.answer()


@router.callback_query(BookingFSM.choosing_service, F.data.startswith("svc:"))
async def cb_choose_service(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    service_id = int(callback.data.split(":")[1])
    svc = (await session.execute(select(Service).where(Service.id == service_id))).scalar_one_or_none()
    if not svc:
        await callback.answer("Услуга не найдена", show_alert=True)
        return

    master = await _get_master(session)
    if not master:
        await callback.answer("Мастер недоступен", show_alert=True)
        return

    available_dates = await get_available_dates(session, master, svc.duration_min)
    if not available_dates:
        await callback.message.edit_text(
            "К сожалению, свободных слотов на ближайшие 7 дней нет.",
            reply_markup=main_menu_kb(False),
        )
        await callback.answer()
        return

    await state.update_data(service_id=service_id, master_id=master.id, duration_min=svc.duration_min)
    await state.set_state(BookingFSM.choosing_day)
    await callback.message.edit_text(
        f"<b>{svc.name}</b>\nВыберите день:",
        reply_markup=days_kb(available_dates),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(BookingFSM.choosing_day, F.data.startswith("day:"))
async def cb_choose_day(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    from datetime import date
    date_str = callback.data.split(":")[1]
    chosen_date = date.fromisoformat(date_str)

    data = await state.get_data()
    master = (await session.execute(select(Master).where(Master.id == data["master_id"]))).scalar_one()

    slots = await get_available_slots(session, master, data["duration_min"], chosen_date)
    if not slots:
        await callback.answer("На этот день слоты уже заняты, выберите другой", show_alert=True)
        return

    await state.update_data(chosen_date=date_str)
    await state.set_state(BookingFSM.choosing_time)
    await callback.message.edit_text(
        f"📅 {chosen_date.strftime('%d.%m.%Y')}\nВыберите время:",
        reply_markup=slots_kb(slots),
    )
    await callback.answer()


@router.callback_query(BookingFSM.choosing_time, F.data.startswith("slot:"))
async def cb_choose_slot(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    start_ts_iso = callback.data[len("slot:"):]
    start_ts = datetime.fromisoformat(start_ts_iso)

    data = await state.get_data()
    price = await _get_price(session, data["master_id"], data["service_id"])
    if price is None:
        await callback.answer("Цена не найдена, обратитесь к мастеру", show_alert=True)
        return

    svc = (await session.execute(select(Service).where(Service.id == data["service_id"]))).scalar_one()
    local = start_ts.astimezone(TZ)
    text = (
        f"Подтвердите запись:\n\n"
        f"📋 <b>{svc.name}</b>\n"
        f"📅 {local.strftime('%d.%m.%Y')} в {local.strftime('%H:%M')}\n"
        f"💰 <b>{price} ₽</b>\n\nЗаписать?"
    )
    await state.update_data(start_ts_iso=start_ts_iso)
    await state.set_state(BookingFSM.confirming)
    await callback.message.edit_text(
        text,
        reply_markup=booking_confirm_kb(data["service_id"], start_ts_iso),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(BookingFSM.confirming, F.data.startswith("book_confirm:"))
async def cb_book_confirm(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    parts = callback.data.split(":")
    service_id = int(parts[1])
    start_ts_iso = ":".join(parts[2:])  # ISO может содержать ':'
    start_ts = datetime.fromisoformat(start_ts_iso)

    data = await state.get_data()
    client = await _get_or_create_client(session, callback.message)
    price = await _get_price(session, data["master_id"], service_id)
    svc = (await session.execute(select(Service).where(Service.id == service_id))).scalar_one()

    try:
        appointment = await create_appointment(
            session,
            master_id=data["master_id"],
            client_id=client.id,
            service_id=service_id,
            start_ts=start_ts,
            duration_min=data["duration_min"],
            price=price,
        )
    except SlotAlreadyTakenError:
        await callback.message.edit_text(
            "😔 Этот слот только что заняли. Пожалуйста, выберите другое время.",
            reply_markup=main_menu_kb(False),
        )
        await state.clear()
        await callback.answer()
        return

    await state.clear()
    await callback.message.delete()
    await send_booking_confirmation(callback.bot, callback.message.chat.id, appointment, svc.name)
    await callback.answer()


# ---------------------------------------------------------------------------
# Мои записи
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "my_appointments")
async def cb_my_appointments(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    client = await _get_or_create_client(session, callback.message)
    upcoming = await _get_upcoming_appointments(session, client.id)

    if not upcoming:
        await callback.message.edit_text(
            "У вас нет предстоящих записей.",
            reply_markup=main_menu_kb(False),
        )
        await callback.answer()
        return

    lines = []
    for apt in upcoming:
        svc = (await session.execute(select(Service).where(Service.id == apt.service_id))).scalar_one()
        local = apt.start_ts.astimezone(TZ)
        lines.append(f"• {local.strftime('%d.%m')} в {local.strftime('%H:%M')} — {svc.name}")

    text = "📋 <b>Ваши записи:</b>\n\n" + "\n".join(lines) + "\n\nНажмите на запись, чтобы отменить:"
    await callback.message.edit_text(
        text,
        reply_markup=my_appointments_kb(upcoming),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("apt_cancel_ask:"))
async def cb_cancel_ask(callback: CallbackQuery, session: AsyncSession) -> None:
    appointment_id = int(callback.data.split(":")[1])
    apt = (await session.execute(
        select(Appointment).where(Appointment.id == appointment_id)
    )).scalar_one_or_none()

    if not apt or apt.status not in (AppointmentStatus.booked, AppointmentStatus.confirmed):
        await callback.answer("Запись не найдена или уже отменена", show_alert=True)
        return

    svc = (await session.execute(select(Service).where(Service.id == apt.service_id))).scalar_one()
    local = apt.start_ts.astimezone(TZ)
    text = (
        f"Отменяем запись:\n\n"
        f"📋 {svc.name}\n"
        f"📅 {local.strftime('%d.%m')} в {local.strftime('%H:%M')}\n\n"
        f"Подтверждаете отмену?"
    )
    await callback.message.edit_text(text, reply_markup=cancel_confirm_kb(appointment_id))
    await callback.answer()


@router.callback_query(F.data.startswith("apt_cancel_confirm:"))
async def cb_cancel_confirm(callback: CallbackQuery, session: AsyncSession) -> None:
    appointment_id = int(callback.data.split(":")[1])
    apt = (await session.execute(
        select(Appointment)
        .where(Appointment.id == appointment_id)
        .options()  # reminders загружаются lazy
    )).scalar_one_or_none()

    if not apt:
        await callback.answer("Запись не найдена", show_alert=True)
        return

    # Подгружаем reminders явно
    from sqlalchemy.orm import selectinload
    apt = (await session.execute(
        select(Appointment)
        .where(Appointment.id == appointment_id)
        .options(selectinload(Appointment.reminders))
    )).scalar_one()

    client = await _get_or_create_client(session, callback.message)
    await cancel_appointment(session, apt, actor_type="client", actor_id=client.id)

    await callback.message.edit_text(
        "✅ Запись отменена.\n\nХотите записаться заново?",
        reply_markup=after_cancel_kb(),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Подтверждение из напоминания
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("apt_confirm:"))
async def cb_apt_confirm(callback: CallbackQuery, session: AsyncSession) -> None:
    from services.appointments import confirm_appointment
    appointment_id = int(callback.data.split(":")[1])
    apt = (await session.execute(
        select(Appointment).where(Appointment.id == appointment_id)
    )).scalar_one_or_none()

    if not apt or apt.status != AppointmentStatus.booked:
        await callback.answer("Запись уже подтверждена или отменена", show_alert=True)
        return

    client = await _get_or_create_client(session, callback.message)
    await confirm_appointment(session, apt, actor_id=client.id)
    await callback.message.edit_text("✅ Визит подтверждён. Ждём вас!")
    await callback.answer()


# ---------------------------------------------------------------------------
# Отписаться
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "unsubscribe")
async def cb_unsubscribe(callback: CallbackQuery, session: AsyncSession) -> None:
    stmt = select(Client).where(Client.tg_user_id == callback.from_user.id)
    client = (await session.execute(stmt)).scalar_one_or_none()
    if client:
        client.tg_status = ClientStatus.unsubscribed
        client.tg_status_updated_at = datetime.now(timezone.utc)
        session.add(Event(
            event_type="client_unsubscribed",
            client_id=client.id,
            actor_type="client",
            actor_id=client.id,
        ))
        await session.commit()
    await callback.message.edit_text(
        "Вы отписались от уведомлений бота. "
        "Чтобы снова начать, отправьте /start."
    )
    await callback.answer()
