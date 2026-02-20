"""
Создание, отмена записей и управление статусами.
Атомарная операция бронирования — защита от гонок через SELECT FOR UPDATE.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import config as cfg
from db.models.appointment import Appointment, AppointmentStatus
from db.models.client import Client
from db.models.event import Event
from db.models.reminder import Reminder, ReminderType, ReminderStatus


class SlotAlreadyTakenError(Exception):
    """Слот занят — параллельная запись успела раньше."""


async def create_appointment(
    session: AsyncSession,
    master_id: int,
    client_id: int,
    service_id: int,
    start_ts: datetime,
    duration_min: int,
    price: Decimal,
) -> Appointment:
    """
    Создаёт запись атомарно.
    Проверяет занятость слота через SELECT FOR UPDATE перед INSERT.
    Raises SlotAlreadyTakenError если слот занят.
    """
    end_ts = start_ts + timedelta(minutes=duration_min)

    # Блокируем конкурирующие записи на этот слот
    conflict_stmt = (
        select(Appointment)
        .where(
            and_(
                Appointment.master_id == master_id,
                Appointment.status.in_([
                    AppointmentStatus.booked,
                    AppointmentStatus.confirmed,
                    AppointmentStatus.arrived,
                ]),
                Appointment.start_ts < end_ts,
                Appointment.end_ts > start_ts,
            )
        )
        .with_for_update()
    )
    result = await session.execute(conflict_stmt)
    if result.scalars().first():
        raise SlotAlreadyTakenError("Слот уже занят")

    appointment = Appointment(
        master_id=master_id,
        client_id=client_id,
        service_id=service_id,
        start_ts=start_ts,
        end_ts=end_ts,
        status=AppointmentStatus.booked,
        price_snapshot=price,
    )
    session.add(appointment)
    await session.flush()  # получаем id до commit

    # Создаём напоминания
    reminders = _build_reminders(appointment)
    session.add_all(reminders)

    # Логируем событие
    session.add(Event(
        event_type="appointment_created",
        appointment_id=appointment.id,
        client_id=client_id,
        master_id=master_id,
        actor_type="client",
        actor_id=client_id,
        payload={"price": str(price), "start_ts": start_ts.isoformat()},
    ))

    await session.commit()
    await session.refresh(appointment)
    return appointment


def _build_reminders(appointment: Appointment) -> list[Reminder]:
    """Создаёт три напоминания по правилам из ТЗ."""
    reminders = []
    for hours_before, reminder_type in [
        (24, ReminderType.confirm_24h),
        (6, ReminderType.confirm_6h),
        (3, ReminderType.remind_3h),
    ]:
        remind_at = appointment.start_ts - timedelta(hours=hours_before)
        # Не создаём напоминание если оно уже в прошлом
        if remind_at > datetime.now(timezone.utc):
            reminders.append(Reminder(
                appointment_id=appointment.id,
                remind_at_ts=remind_at,
                type=reminder_type,
                status=ReminderStatus.pending,
            ))
    return reminders


async def cancel_appointment(
    session: AsyncSession,
    appointment: Appointment,
    actor_type: str,
    actor_id: int,
) -> None:
    """Отменяет запись и все pending-напоминания по ней."""
    now = datetime.now(timezone.utc)
    is_late = (appointment.start_ts - now) < timedelta(hours=1)

    appointment.status = AppointmentStatus.late_cancel if is_late else AppointmentStatus.cancelled
    appointment.cancelled_at = now

    # Отменяем все pending напоминания
    for reminder in appointment.reminders:
        if reminder.status == ReminderStatus.pending:
            reminder.status = ReminderStatus.cancelled

    event_type = (
        "late_cancel" if is_late
        else "appointment_cancelled_by_client" if actor_type == "client"
        else "appointment_cancelled_by_master"
    )
    session.add(Event(
        event_type=event_type,
        appointment_id=appointment.id,
        client_id=appointment.client_id,
        master_id=appointment.master_id,
        actor_type=actor_type,
        actor_id=actor_id,
        payload={"is_late": is_late},
    ))

    await session.commit()


async def confirm_appointment(
    session: AsyncSession,
    appointment: Appointment,
    actor_id: int,
) -> None:
    """Клиент подтверждает визит (кнопка "Подтверждаю")."""
    appointment.status = AppointmentStatus.confirmed
    appointment.confirmed_at = datetime.now(timezone.utc)

    session.add(Event(
        event_type="appointment_confirmed",
        appointment_id=appointment.id,
        client_id=appointment.client_id,
        master_id=appointment.master_id,
        actor_type="client",
        actor_id=actor_id,
    ))
    await session.commit()


async def mark_arrived(
    session: AsyncSession,
    appointment: Appointment,
    master_id: int,
) -> None:
    """Мастер нажал "Принято" — клиент пришёл."""
    appointment.status = AppointmentStatus.arrived
    session.add(Event(
        event_type="client_arrived",
        appointment_id=appointment.id,
        client_id=appointment.client_id,
        master_id=master_id,
        actor_type="master",
        actor_id=master_id,
    ))
    await session.commit()


async def mark_done(
    session: AsyncSession,
    appointment: Appointment,
    master_id: int,
) -> None:
    """Мастер нажал "Сеанс завершён"."""
    appointment.status = AppointmentStatus.done

    # Обновляем last_visit_at у клиента
    client_stmt = select(Client).where(Client.id == appointment.client_id)
    client = (await session.execute(client_stmt)).scalar_one()
    client.last_visit_at = datetime.now(timezone.utc)

    session.add(Event(
        event_type="service_done",
        appointment_id=appointment.id,
        client_id=appointment.client_id,
        master_id=master_id,
        actor_type="master",
        actor_id=master_id,
    ))
    await session.commit()
