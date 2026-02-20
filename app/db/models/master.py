from __future__ import annotations

from datetime import time, datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import String, Integer, BigInteger, Time, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.session import Base

if TYPE_CHECKING:
    from db.models.appointment import Appointment
    from db.models.master_service_price import MasterServicePrice
    from db.models.blackout import Blackout


class Master(Base):
    __tablename__ = "masters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    tg_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="Europe/Moscow")
    work_start_time: Mapped[time] = mapped_column(Time, nullable=False, default=time(9, 0))
    work_end_time: Mapped[time] = mapped_column(Time, nullable=False, default=time(20, 0))
    buffer_min: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    appointments: Mapped[list["Appointment"]] = relationship(back_populates="master")
    service_prices: Mapped[list["MasterServicePrice"]] = relationship(back_populates="master")
    blackouts: Mapped[list["Blackout"]] = relationship(back_populates="master")

    def __repr__(self) -> str:
        return f"<Master id={self.id} name={self.display_name!r}>"
