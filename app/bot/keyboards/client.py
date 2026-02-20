"""Клавиатуры для клиентского сценария."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import config as cfg
from db.models.appointment import Appointment
from db.models.service import Service

TZ = ZoneInfo(cfg.TIMEZONE)

MONTHS_RU = {
    1: "янв", 2: "фев", 3: "мар", 4: "апр",
    5: "май", 6: "июн", 7: "июл", 8: "авг",
    9: "сен", 10: "окт", 11: "ноя", 12: "дек",
}
DAYS_RU = {0: "пн", 1: "вт", 2: "ср", 3: "чт", 4: "пт", 5: "сб", 6: "вс"}


def main_menu_kb(has_appointment: bool) -> InlineKeyboardMarkup:
    rows = []
    if has_appointment:
        rows.append([InlineKeyboardButton(text="📅 Записаться", callback_data="book_start")])
    else:
        rows.append([InlineKeyboardButton(text="📅 Записаться", callback_data="book_start")])
    rows.append([InlineKeyboardButton(text="📋 Мои записи", callback_data="my_appointments")])
    rows.append([InlineKeyboardButton(text="❌ Отписаться от бота", callback_data="unsubscribe")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def services_kb(services: list[Service]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=svc.name, callback_data=f"svc:{svc.id}")]
        for svc in services
    ]
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def days_kb(available_dates: list[date]) -> InlineKeyboardMarkup:
    today = datetime.now(TZ).date()
    rows = []
    for d in available_dates:
        if d == today:
            label = f"Сегодня, {d.day} {MONTHS_RU[d.month]}"
        elif (d - today).days == 1:
            label = f"Завтра, {d.day} {MONTHS_RU[d.month]}"
        else:
            label = f"{DAYS_RU[d.weekday()]} {d.day} {MONTHS_RU[d.month]}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"day:{d.isoformat()}")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="book_start")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def slots_kb(slots: list[datetime]) -> InlineKeyboardMarkup:
    """Слоты в виде сетки: по 3 кнопки в ряду."""
    row: list[InlineKeyboardButton] = []
    rows: list[list[InlineKeyboardButton]] = []
    for slot in slots:
        local = slot.astimezone(TZ)
        row.append(InlineKeyboardButton(
            text=local.strftime("%H:%M"),
            callback_data=f"slot:{slot.isoformat()}",
        ))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="book_choose_day")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def booking_confirm_kb(service_id: int, start_ts_iso: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Да, записать",
                callback_data=f"book_confirm:{service_id}:{start_ts_iso}",
            ),
            InlineKeyboardButton(text="❌ Нет", callback_data="book_start"),
        ]
    ])


def my_appointments_kb(appointments: list[Appointment]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for apt in appointments:
        local = apt.start_ts.astimezone(TZ)
        label = f"{local.strftime('%d.%m')} {local.strftime('%H:%M')} — отменить"
        rows.append([InlineKeyboardButton(
            text=label,
            callback_data=f"apt_cancel_ask:{apt.id}",
        )])
    rows.append([InlineKeyboardButton(text="◀️ В меню", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_confirm_kb(appointment_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Да, отменить",
                callback_data=f"apt_cancel_confirm:{appointment_id}",
            ),
            InlineKeyboardButton(text="❌ Нет", callback_data="my_appointments"),
        ]
    ])


def after_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Записаться заново", callback_data="book_start")],
        [InlineKeyboardButton(text="◀️ В меню", callback_data="menu")],
    ])
