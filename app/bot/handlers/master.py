"""
Хэндлеры для мастера.

Мастер определяется по tg_user_id в таблице masters.
Все его апдейты проходят через MasterFilter.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from aiogram import Router, F
from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import config as cfg
from db.models.appointment import Appointment, AppointmentStatus
from db.models.master import Master
from db.models.service import Service
from bot.keyboards.master import appointment_actions_kb, master_main_menu_kb
from services.appointments import cancel_appointment, mark_arrived, mark_done

TZ = ZoneInfo(cfg.TIMEZONE)
router = Router(name="master")


# ---------------------------------------------------------------------------
# Фильтр: проверяем что пользователь — мастер
# ---------------------------------------------------------------------------

class MasterFilter(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery, session: AsyncSession) -> bool:
        user_id = event.from_user.id
        result = await session.execute(select(Master).where(Master.tg_user_id == user_id))
        master = result.scalar_one_or_none()
        return master is not None


# Применяем фильтр ко всему роутеру
router.message.filter(MasterFilter())
router.callback_query.filter(MasterFilter())


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

async def _get_master(session: AsyncSession, tg_user_id: int) -> Master:
    result = await session.execute(select(Master).where(Master.tg_user_id == tg_user_id))
    return result.scalar_one()


async def _get_appointments_for_period(
    session: AsyncSession,
    master_id: int,
    start: datetime,
    end: datetime,
) -> list[Appointment]:
    stmt = (
        select(Appointment)
        .where(
            and_(
                Appointment.master_id == master_id,
                Appointment.start_ts >= start,
                Appointment.start_ts < end,
                Appointment.status.in_([
                    AppointmentStatus.booked,
                    AppointmentStatus.confirmed,
                    AppointmentStatus.arrived,
                    AppointmentStatus.done,
                ]),
            )
        )
        .order_by(Appointment.start_ts)
    )
    return (await session.execute(stmt)).scalars().all()


def _fmt_appointment_for_master(apt: Appointment, service_name: str) -> str:
    local = apt.start_ts.astimezone(TZ)
    STATUS_LABELS = {
        AppointmentStatus.booked: "⏳ ожидает",
        AppointmentStatus.confirmed: "✅ подтверждено",
        AppointmentStatus.arrived: "👤 пришёл",
        AppointmentStatus.done: "🏁 завершено",
        AppointmentStatus.cancelled: "❌ отменено",
        AppointmentStatus.late_cancel: "⚠️ поздняя отмена",
    }
    return (
        f"🕐 {local.strftime('%H:%M')} — <b>{service_name}</b>\n"
        f"ID: {apt.id}  |  {STATUS_LABELS.get(apt.status, apt.status)}\n"
        f"💰 {apt.price_snapshot} ₽"
    )


async def _send_schedule(
    callback: CallbackQuery,
    session: AsyncSession,
    start: datetime,
    end: datetime,
    title: str,
) -> None:
    master = await _get_master(session, callback.from_user.id)
    appointments = await _get_appointments_for_period(session, master.id, start, end)

    if not appointments:
        await callback.message.edit_text(
            f"{title}\n\nЗаписей нет.",
            reply_markup=master_main_menu_kb(),
        )
        await callback.answer()
        return

    # Загружаем услуги
    service_ids = {apt.service_id for apt in appointments}
    services = {
        svc.id: svc
        for svc in (await session.execute(
            select(Service).where(Service.id.in_(service_ids))
        )).scalars()
    }

    lines = []
    for apt in appointments:
        svc_name = services[apt.service_id].name
        lines.append(_fmt_appointment_for_master(apt, svc_name))

    text = f"{title}\n\n" + "\n\n".join(lines)
    await callback.message.edit_text(text, reply_markup=master_main_menu_kb(), parse_mode="HTML")
    await callback.answer()


# ---------------------------------------------------------------------------
# Главное меню мастера
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "master_menu")
async def cb_master_menu(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "👨‍⚕️ Меню мастера",
        reply_markup=master_main_menu_kb(),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Расписание
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "master_today")
async def cb_today(callback: CallbackQuery, session: AsyncSession) -> None:
    today = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    await _send_schedule(callback, session, today.astimezone(ZoneInfo("UTC")), tomorrow.astimezone(ZoneInfo("UTC")), "📆 Сегодня")


@router.callback_query(F.data == "master_tomorrow")
async def cb_tomorrow(callback: CallbackQuery, session: AsyncSession) -> None:
    today = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    day_after = today + timedelta(days=2)
    await _send_schedule(callback, session, tomorrow.astimezone(ZoneInfo("UTC")), day_after.astimezone(ZoneInfo("UTC")), "📆 Завтра")


@router.callback_query(F.data == "master_7days")
async def cb_7days(callback: CallbackQuery, session: AsyncSession) -> None:
    today = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    week_later = today + timedelta(days=7)
    await _send_schedule(callback, session, today.astimezone(ZoneInfo("UTC")), week_later.astimezone(ZoneInfo("UTC")), "📆 Ближайшие 7 дней")


# ---------------------------------------------------------------------------
# Статусы записей (booked/confirmed/arrived)
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "master_statuses")
async def cb_statuses(callback: CallbackQuery, session: AsyncSession) -> None:
    master = await _get_master(session, callback.from_user.id)
    now_utc = datetime.now(timezone.utc)
    stmt = (
        select(Appointment)
        .where(
            and_(
                Appointment.master_id == master.id,
                Appointment.status.in_([
                    AppointmentStatus.booked,
                    AppointmentStatus.confirmed,
                    AppointmentStatus.arrived,
                ]),
                Appointment.start_ts > now_utc - timedelta(hours=2),
            )
        )
        .order_by(Appointment.start_ts)
    )
    appointments = (await session.execute(stmt)).scalars().all()

    if not appointments:
        await callback.message.edit_text(
            "Нет активных записей.",
            reply_markup=master_main_menu_kb(),
        )
        await callback.answer()
        return

    service_ids = {apt.service_id for apt in appointments}
    services = {
        svc.id: svc
        for svc in (await session.execute(
            select(Service).where(Service.id.in_(service_ids))
        )).scalars()
    }

    # Показываем первую запись с кнопками действий
    apt = appointments[0]
    svc_name = services[apt.service_id].name
    text = _fmt_appointment_for_master(apt, svc_name)
    if len(appointments) > 1:
        text += f"\n\n<i>+ ещё {len(appointments) - 1} записей</i>"

    await callback.message.edit_text(
        text,
        reply_markup=appointment_actions_kb(apt),
        parse_mode="HTML",
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Действия с записью
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("master_arrived:"))
async def cb_mark_arrived(callback: CallbackQuery, session: AsyncSession) -> None:
    appointment_id = int(callback.data.split(":")[1])
    apt = (await session.execute(
        select(Appointment).where(Appointment.id == appointment_id)
    )).scalar_one_or_none()

    if not apt:
        await callback.answer("Запись не найдена", show_alert=True)
        return

    master = await _get_master(session, callback.from_user.id)
    await mark_arrived(session, apt, master.id)
    await callback.message.edit_text(
        f"✅ Клиент отмечен как пришедший.\n\nЗапись #{apt.id}",
        reply_markup=appointment_actions_kb(apt),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("master_done:"))
async def cb_mark_done(callback: CallbackQuery, session: AsyncSession) -> None:
    appointment_id = int(callback.data.split(":")[1])
    apt = (await session.execute(
        select(Appointment).where(Appointment.id == appointment_id)
    )).scalar_one_or_none()

    if not apt:
        await callback.answer("Запись не найдена", show_alert=True)
        return

    master = await _get_master(session, callback.from_user.id)
    await mark_done(session, apt, master.id)
    await callback.message.edit_text(
        f"🏁 Сеанс завершён. Запись #{apt.id}",
        reply_markup=master_main_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("master_cancel:"))
async def cb_master_cancel(callback: CallbackQuery, session: AsyncSession) -> None:
    appointment_id = int(callback.data.split(":")[1])
    apt = (await session.execute(
        select(Appointment)
        .where(Appointment.id == appointment_id)
        .options(selectinload(Appointment.reminders))
    )).scalar_one_or_none()

    if not apt:
        await callback.answer("Запись не найдена", show_alert=True)
        return

    master = await _get_master(session, callback.from_user.id)
    await cancel_appointment(session, apt, actor_type="master", actor_id=master.id)

    # Уведомляем клиента
    from db.models.client import Client
    from services.notifications import send_cancellation_by_master
    client = (await session.execute(select(Client).where(Client.id == apt.client_id))).scalar_one()
    svc = (await session.execute(select(Service).where(Service.id == apt.service_id))).scalar_one()
    await send_cancellation_by_master(callback.bot, client.tg_chat_id, apt, svc.name)

    await callback.message.edit_text(
        f"❌ Запись #{apt.id} отменена. Клиент уведомлён.",
        reply_markup=master_main_menu_kb(),
    )
    await callback.answer()
