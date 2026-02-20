"""Клавиатуры для сценария мастера."""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from db.models.appointment import Appointment, AppointmentStatus


def master_main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📆 Сегодня", callback_data="master_today")],
        [InlineKeyboardButton(text="📆 Завтра", callback_data="master_tomorrow")],
        [InlineKeyboardButton(text="📆 7 дней", callback_data="master_7days")],
        [InlineKeyboardButton(text="✅ Статусы записей", callback_data="master_statuses")],
    ])


def appointment_actions_kb(appointment: Appointment) -> InlineKeyboardMarkup:
    """Кнопки действий в зависимости от текущего статуса записи."""
    rows: list[list[InlineKeyboardButton]] = []

    if appointment.status in (AppointmentStatus.booked, AppointmentStatus.confirmed):
        rows.append([
            InlineKeyboardButton(
                text="✅ Принято (клиент пришёл)",
                callback_data=f"master_arrived:{appointment.id}",
            )
        ])
        rows.append([
            InlineKeyboardButton(
                text="❌ Отменить",
                callback_data=f"master_cancel:{appointment.id}",
            )
        ])
    elif appointment.status == AppointmentStatus.arrived:
        rows.append([
            InlineKeyboardButton(
                text="🏁 Сеанс завершён",
                callback_data=f"master_done:{appointment.id}",
            )
        ])
    # done — только метка, кнопок нет

    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else InlineKeyboardMarkup(inline_keyboard=[])
