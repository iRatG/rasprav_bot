"""
Отправка Telegram-сообщений клиентам и мастеру.
Централизованное место для всех шаблонов сообщений.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError

import config as cfg
from db.models.appointment import Appointment
from db.models.reminder import ReminderType

TZ = ZoneInfo(cfg.TIMEZONE)


def _fmt_dt(ts: datetime) -> str:
    """Форматирует UTC datetime в человекочитаемый МСК вид: 'пн 15 янв в 14:30'."""
    local = ts.astimezone(TZ)
    MONTHS = {
        1: "янв", 2: "фев", 3: "мар", 4: "апр",
        5: "май", 6: "июн", 7: "июл", 8: "авг",
        9: "сен", 10: "окт", 11: "ноя", 12: "дек",
    }
    DAYS = {0: "пн", 1: "вт", 2: "ср", 3: "чт", 4: "пт", 5: "сб", 6: "вс"}
    return f"{DAYS[local.weekday()]} {local.day} {MONTHS[local.month]} в {local.strftime('%H:%M')}"


async def send_booking_confirmation(
    bot: Bot,
    chat_id: int,
    appointment: Appointment,
    service_name: str,
) -> None:
    """Отправляет клиенту карточку записи после создания."""
    dt_str = _fmt_dt(appointment.start_ts)
    text = (
        f"✅ <b>Запись создана!</b>\n\n"
        f"📋 Услуга: {service_name}\n"
        f"📅 Дата и время: {dt_str}\n"
        f"💰 Сумма: <b>{appointment.price_snapshot} ₽</b>\n\n"
        f"Подготовьте {appointment.price_snapshot} ₽. "
        f"Мы напомним о визите за 24 часа."
    )
    await bot.send_message(chat_id, text, parse_mode="HTML")


async def send_reminder(
    bot: Bot,
    chat_id: int,
    appointment: Appointment,
    reminder_type: ReminderType,
    service_name: str,
) -> None:
    """Отправляет напоминание в зависимости от типа."""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    dt_str = _fmt_dt(appointment.start_ts)

    if reminder_type in (ReminderType.confirm_24h, ReminderType.confirm_6h):
        hours = 24 if reminder_type == ReminderType.confirm_24h else 6
        text = (
            f"⏰ <b>Напоминание о записи</b>\n\n"
            f"У вас запись через {hours} ч:\n"
            f"📋 {service_name}\n"
            f"📅 {dt_str}\n\n"
            f"Подтвердите, пожалуйста, свой визит."
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="✅ Подтверждаю",
                callback_data=f"apt_confirm:{appointment.id}",
            ),
            InlineKeyboardButton(
                text="❌ Отменить",
                callback_data=f"apt_cancel:{appointment.id}",
            ),
        ]])
        await bot.send_message(chat_id, text, reply_markup=keyboard, parse_mode="HTML")

    elif reminder_type == ReminderType.remind_3h:
        text = (
            f"🔔 <b>Ждём вас через 3 часа!</b>\n\n"
            f"📋 {service_name}\n"
            f"📅 {dt_str}\n"
            f"💰 {appointment.price_snapshot} ₽"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="❌ Отменить запись",
                callback_data=f"apt_cancel:{appointment.id}",
            ),
        ]])
        await bot.send_message(chat_id, text, reply_markup=keyboard, parse_mode="HTML")


async def send_cancellation_by_master(
    bot: Bot,
    chat_id: int,
    appointment: Appointment,
    service_name: str,
) -> None:
    """Уведомление клиенту при отмене мастером / blackout."""
    text = (
        "😔 К сожалению, мастер не сможет вас принять в запланированное время.\n\n"
        f"Ваша запись на <b>{service_name}</b> ({_fmt_dt(appointment.start_ts)}) отменена.\n\n"
        "Извините за неудобства. Вы можете записаться на другое время."
    )
    await bot.send_message(chat_id, text, parse_mode="HTML")


async def send_reactivation(bot: Bot, chat_id: int) -> None:
    """Реактивационное сообщение спящему клиенту."""
    text = (
        "👋 Давно не виделись!\n\n"
        "Будем рады снова видеть вас. Запишитесь на удобное время — "
        "свободные слоты ждут вас."
    )
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📅 Записаться", callback_data="book_start"),
    ]])
    await bot.send_message(chat_id, text, reply_markup=keyboard)


async def safe_send(bot: Bot, chat_id: int, text: str, **kwargs) -> bool:
    """
    Отправляет сообщение и возвращает False если бот заблокирован (403).
    Используется там, где нужна обработка блокировки.
    """
    try:
        await bot.send_message(chat_id, text, **kwargs)
        return True
    except TelegramForbiddenError:
        return False
