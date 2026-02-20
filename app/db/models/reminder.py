from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.session import Base

if TYPE_CHECKING:
    from db.models.appointment import Appointment


class ReminderType(str, enum.Enum):
    confirm_24h = "confirm_24h"
    confirm_6h = "confirm_6h"
    remind_3h = "remind_3h"


class ReminderStatus(str, enum.Enum):
    pending = "pending"
    sent = "sent"
    cancelled = "cancelled"
    failed = "failed"


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointments.id"), nullable=False)
    remind_at_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    type: Mapped[ReminderType] = mapped_column(
        Enum(ReminderType, name="reminder_type"), nullable=False
    )
    status: Mapped[ReminderStatus] = mapped_column(
        Enum(ReminderStatus, name="reminder_status"),
        nullable=False,
        default=ReminderStatus.pending,
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    appointment: Mapped["Appointment"] = relationship(back_populates="reminders")

    def __repr__(self) -> str:
        return f"<Reminder id={self.id} apt={self.appointment_id} type={self.type} status={self.status}>"
