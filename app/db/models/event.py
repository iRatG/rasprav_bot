from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from db.session import Base


# Полный список event_type из ТЗ:
# По записи:
#   appointment_created, appointment_confirmed,
#   appointment_cancelled_by_client, appointment_cancelled_by_master,
#   late_cancel, client_arrived, service_done
# По напоминаниям:
#   reminder_sent_24h, reminder_sent_6h, reminder_sent_3h, reminder_failed
# По клиенту:
#   client_blocked_bot, client_unsubscribed, client_reactivated
# По системе:
#   price_changed, blackout_created, service_updated, admin_added, admin_removed


class Event(Base):
    """Event log — ядро аналитики. Только INSERT, никаких UPDATE/DELETE."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    appointment_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True
    )
    client_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("clients.id", ondelete="SET NULL"), nullable=True
    )
    master_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("masters.id", ondelete="SET NULL"), nullable=True
    )
    # client / master / scheduler / admin
    actor_type: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    def __repr__(self) -> str:
        return f"<Event id={self.id} type={self.event_type!r} at={self.created_at}>"
