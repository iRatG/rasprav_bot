from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.session import Base

if TYPE_CHECKING:
    from db.models.appointment import Appointment


class ClientStatus(str, enum.Enum):
    active = "active"
    sleeping = "sleeping"
    blocked = "blocked"
    unsubscribed = "unsubscribed"


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tg_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    tg_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tg_status: Mapped[ClientStatus] = mapped_column(
        Enum(ClientStatus, name="client_status"),
        nullable=False,
        default=ClientStatus.active,
    )
    tg_status_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_visit_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_reactivation_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    appointments: Mapped[list["Appointment"]] = relationship(back_populates="client")

    def __repr__(self) -> str:
        return f"<Client id={self.id} tg_user_id={self.tg_user_id}>"
