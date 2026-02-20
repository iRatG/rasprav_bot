"""
Генерация свободных слотов для записи.

Алгоритм:
1. Берём рабочее окно мастера (09:00–20:00 МСК) для запрошенной даты.
2. Генерируем кандидатов с шагом (duration + buffer).
3. Фильтруем: убираем занятые (appointments) и заблокированные (blackouts).
4. Убираем слоты ближе, чем MIN_BOOKING_AHEAD_HOURS от текущего момента.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

import config as cfg
from db.models.appointment import Appointment, AppointmentStatus
from db.models.blackout import Blackout
from db.models.master import Master

TZ = ZoneInfo(cfg.TIMEZONE)
_ACTIVE_STATUSES = (
    AppointmentStatus.booked,
    AppointmentStatus.confirmed,
    AppointmentStatus.arrived,
)


def _work_window(for_date: date, master: Master) -> tuple[datetime, datetime]:
    """Возвращает (work_start, work_end) в UTC для заданной даты."""
    work_start_local = datetime(
        for_date.year, for_date.month, for_date.day,
        master.work_start_time.hour, master.work_start_time.minute,
        tzinfo=TZ,
    )
    work_end_local = datetime(
        for_date.year, for_date.month, for_date.day,
        master.work_end_time.hour, master.work_end_time.minute,
        tzinfo=TZ,
    )
    return work_start_local.astimezone(ZoneInfo("UTC")), work_end_local.astimezone(ZoneInfo("UTC"))


def _generate_candidates(
    work_start: datetime,
    work_end: datetime,
    duration_min: int,
    buffer_min: int,
) -> list[datetime]:
    """Все возможные старты слотов в рабочем окне."""
    step = timedelta(minutes=duration_min + buffer_min)
    duration = timedelta(minutes=duration_min)
    slots: list[datetime] = []
    current = work_start
    while current + duration <= work_end:
        slots.append(current)
        current += step
    return slots


async def get_available_slots(
    session: AsyncSession,
    master: Master,
    duration_min: int,
    for_date: date,
) -> list[datetime]:
    """
    Возвращает список доступных UTC datetime для старта записи.
    Для отображения клиенту конвертируй в МСК.
    """
    now_utc = datetime.now(ZoneInfo("UTC"))
    min_start = now_utc + timedelta(hours=cfg.MIN_BOOKING_AHEAD_HOURS)

    work_start, work_end = _work_window(for_date, master)

    # Все кандидаты
    candidates = _generate_candidates(work_start, work_end, duration_min, master.buffer_min)

    # Загружаем занятые записи за этот день
    stmt = select(Appointment).where(
        and_(
            Appointment.master_id == master.id,
            Appointment.status.in_(_ACTIVE_STATUSES),
            Appointment.start_ts >= work_start,
            Appointment.start_ts < work_end,
        )
    )
    result = await session.execute(stmt)
    booked = result.scalars().all()

    # Загружаем blackout'ы, пересекающиеся с рабочим окном
    bl_stmt = select(Blackout).where(
        and_(
            Blackout.master_id == master.id,
            Blackout.start_ts < work_end,
            Blackout.end_ts > work_start,
        )
    )
    bl_result = await session.execute(bl_stmt)
    blackouts = bl_result.scalars().all()

    buffer = timedelta(minutes=master.buffer_min)
    duration = timedelta(minutes=duration_min)
    available: list[datetime] = []

    for slot_start in candidates:
        slot_end = slot_start + duration

        # Слот должен быть достаточно далеко от текущего момента
        if slot_start < min_start:
            continue

        # Проверяем конфликт с существующими записями
        conflict = False
        for apt in booked:
            # Новый слот не должен налезать на [apt.start - buffer, apt.end + buffer)
            if slot_start < apt.end_ts + buffer and slot_end > apt.start_ts - buffer:
                conflict = True
                break
        if conflict:
            continue

        # Проверяем blackout'ы
        for bl in blackouts:
            if slot_start < bl.end_ts and slot_end > bl.start_ts:
                conflict = True
                break
        if conflict:
            continue

        available.append(slot_start)

    return available


async def get_available_dates(
    session: AsyncSession,
    master: Master,
    duration_min: int,
) -> list[date]:
    """
    Возвращает список дат (сегодня + 6 дней), на которых есть хотя бы 1 свободный слот.
    """
    today = datetime.now(TZ).date()
    result: list[date] = []
    for offset in range(cfg.BOOKING_HORIZON_DAYS):
        day = today + timedelta(days=offset)
        slots = await get_available_slots(session, master, duration_min, day)
        if slots:
            result.append(day)
    return result
