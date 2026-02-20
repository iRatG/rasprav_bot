from __future__ import annotations

import enum
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.session import Base

if TYPE_CHECKING:
    from db.models.master import Master
    from db.models.client import Client
    from db.models.service import Service
    from db.models.reminder import Reminder


class AppointmentStatus(str, enum.Enum):
    booked = "booked"
    confirmed = "confirmed"
    arrived = "arrived"
    done = "done"
    cancelled = "cancelled"
    late_cancel = "late_cancel"


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    master_id: Mapped[int] = mapped_column(ForeignKey("masters.id"), nullable=False)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), nullable=False)
    start_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus, name="appointment_status"),
        nullable=False,
        default=AppointmentStatus.booked,
    )
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # Цена фиксируется в момент записи — не меняется при изменении прайса
    price_snapshot: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    master: Mapped["Master"] = relationship(back_populates="appointments")
    client: Mapped["Client"] = relationship(back_populates="appointments")
    service: Mapped["Service"] = relationship(back_populates="appointments")
    reminders: Mapped[list["Reminder"]] = relationship(back_populates="appointment")

    # Примечание: exclusion constraint (запрет пересечений у одного мастера)
    # добавляется в Alembic-миграции через op.execute() с btree_gist.
    # SQLAlchemy не поддерживает его декларативно.

    def __repr__(self) -> str:
        return (
            f"<Appointment id={self.id} master={self.master_id} "
            f"client={self.client_id} start={self.start_ts} status={self.status}>"
        )
