"""
Фоновые задачи (APScheduler):
  - каждую минуту: отправка pending-напоминаний
  - раз в неделю: реактивация sleeping-клиентов
"""

import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import and_, select
from sqlalchemy.orm import selectinload

from db.session import AsyncSessionLocal
from db.models.appointment import Appointment
from db.models.client import Client, ClientStatus
from db.models.event import Event
from db.models.reminder import Reminder, ReminderStatus
from db.models.service import Service
import config as cfg

logger = logging.getLogger(__name__)


async def send_pending_reminders(bot: Bot) -> None:
    """
    Находит все напоминания со статусом pending, время которых уже наступило,
    и отправляет их клиентам.
    """
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as session:
        stmt = (
            select(Reminder)
            .where(
                and_(
                    Reminder.status == ReminderStatus.pending,
                    Reminder.remind_at_ts <= now,
                )
            )
            .options(selectinload(Reminder.appointment))
        )
        reminders = (await session.execute(stmt)).scalars().all()

        for reminder in reminders:
            apt = reminder.appointment

            # Пропускаем если запись уже не активна
            from db.models.appointment import AppointmentStatus
            if apt.status not in (AppointmentStatus.booked, AppointmentStatus.confirmed):
                reminder.status = ReminderStatus.cancelled
                continue

            # Для confirm_6h: отправляем только если НЕ подтверждено
            from db.models.reminder import ReminderType
            if reminder.type == ReminderType.confirm_6h and apt.confirmed_at is not None:
                reminder.status = ReminderStatus.cancelled
                continue

            # Для remind_3h: отправляем только если подтверждено
            if reminder.type == ReminderType.remind_3h and apt.confirmed_at is None:
                reminder.status = ReminderStatus.cancelled
                continue

            # Получаем данные клиента и услуги
            client = (await session.execute(
                select(Client).where(Client.id == apt.client_id)
            )).scalar_one()
            svc = (await session.execute(
                select(Service).where(Service.id == apt.service_id)
            )).scalar_one()

            try:
                from services.notifications import send_reminder
                await send_reminder(bot, client.tg_chat_id, apt, reminder.type, svc.name)
                reminder.status = ReminderStatus.sent
                reminder.sent_at = datetime.now(timezone.utc)

                event_type_map = {
                    ReminderType.confirm_24h: "reminder_sent_24h",
                    ReminderType.confirm_6h: "reminder_sent_6h",
                    ReminderType.remind_3h: "reminder_sent_3h",
                }
                session.add(Event(
                    event_type=event_type_map[reminder.type],
                    appointment_id=apt.id,
                    client_id=apt.client_id,
                    master_id=apt.master_id,
                    actor_type="scheduler",
                    actor_id=0,
                ))

            except TelegramForbiddenError:
                # Клиент заблокировал бота
                reminder.status = ReminderStatus.failed
                client.tg_status = ClientStatus.blocked
                client.tg_status_updated_at = datetime.now(timezone.utc)
                session.add(Event(
                    event_type="reminder_failed",
                    appointment_id=apt.id,
                    client_id=apt.client_id,
                    master_id=apt.master_id,
                    actor_type="scheduler",
                    actor_id=0,
                    payload={"reason": "bot_blocked"},
                ))
                session.add(Event(
                    event_type="client_blocked_bot",
                    client_id=apt.client_id,
                    actor_type="scheduler",
                    actor_id=0,
                ))

            except Exception as e:
                logger.error("Ошибка отправки напоминания %s: %s", reminder.id, e)
                reminder.status = ReminderStatus.failed
                session.add(Event(
                    event_type="reminder_failed",
                    appointment_id=apt.id,
                    client_id=apt.client_id,
                    master_id=apt.master_id,
                    actor_type="scheduler",
                    actor_id=0,
                    payload={"reason": str(e)},
                ))

        await session.commit()
        if reminders:
            logger.info("Обработано напоминаний: %d", len(reminders))


async def check_sleeping_clients(bot: Bot) -> None:
    """
    Раз в неделю: находит sleeping-клиентов и отправляет реактивационное сообщение
    (не чаще 1 раза в 3 месяца).
    """
    now = datetime.now(timezone.utc)
    sleeping_threshold = now - timedelta(days=cfg.SLEEPING_THRESHOLD_DAYS)
    reactivation_cooldown = now - timedelta(days=cfg.REACTIVATION_COOLDOWN_DAYS)

    async with AsyncSessionLocal() as session:
        stmt = select(Client).where(
            and_(
                Client.tg_status == ClientStatus.active,
                Client.last_visit_at < sleeping_threshold,
                (
                    Client.last_reactivation_sent_at.is_(None)
                    | (Client.last_reactivation_sent_at < reactivation_cooldown)
                ),
            )
        )
        clients = (await session.execute(stmt)).scalars().all()

        for client in clients:
            try:
                from services.notifications import send_reactivation
                await send_reactivation(bot, client.tg_chat_id)
                client.tg_status = ClientStatus.sleeping
                client.last_reactivation_sent_at = now
                session.add(Event(
                    event_type="client_reactivated",
                    client_id=client.id,
                    actor_type="scheduler",
                    actor_id=0,
                ))
            except TelegramForbiddenError:
                client.tg_status = ClientStatus.blocked
                client.tg_status_updated_at = now
                session.add(Event(
                    event_type="client_blocked_bot",
                    client_id=client.id,
                    actor_type="scheduler",
                    actor_id=0,
                ))
            except Exception as e:
                logger.error("Реактивация клиента %s: %s", client.id, e)

        await session.commit()
        logger.info("Проверка sleeping-клиентов завершена. Отправлено: %d", len(clients))


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    """Создаёт и настраивает планировщик."""
    scheduler = AsyncIOScheduler(timezone=cfg.TIMEZONE)

    # Каждую минуту — напоминания
    scheduler.add_job(
        send_pending_reminders,
        CronTrigger(minute="*"),
        args=[bot],
        id="send_reminders",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=30,
    )

    # Каждый понедельник в 10:00 МСК — реактивация
    scheduler.add_job(
        check_sleeping_clients,
        CronTrigger(day_of_week="mon", hour=10, minute=0),
        args=[bot],
        id="reactivation",
        replace_existing=True,
        max_instances=1,
    )

    return scheduler
