"""Initial schema — все таблицы + exclusion constraint + seed данные

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00
"""

from typing import Sequence, Union
from datetime import date

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Расширение для exclusion constraint
    # ------------------------------------------------------------------
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    # ------------------------------------------------------------------
    # ENUM типы — DO-блок с проверкой существования, чтобы избежать
    # конфликта с SA-метаданными моделей при повторном запуске
    # ------------------------------------------------------------------
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'client_status') THEN
                CREATE TYPE client_status AS ENUM ('active', 'sleeping', 'blocked', 'unsubscribed');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'appointment_status') THEN
                CREATE TYPE appointment_status AS ENUM ('booked', 'confirmed', 'arrived', 'done', 'cancelled', 'late_cancel');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'reminder_type') THEN
                CREATE TYPE reminder_type AS ENUM ('confirm_24h', 'confirm_6h', 'remind_3h');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'reminder_status') THEN
                CREATE TYPE reminder_status AS ENUM ('pending', 'sent', 'cancelled', 'failed');
            END IF;
        END $$
    """)

    # ------------------------------------------------------------------
    # masters
    # ------------------------------------------------------------------
    op.create_table(
        "masters",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("tg_user_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("timezone", sa.String(50), nullable=False, server_default="Europe/Moscow"),
        sa.Column("work_start_time", sa.Time(), nullable=False, server_default="09:00:00"),
        sa.Column("work_end_time", sa.Time(), nullable=False, server_default="20:00:00"),
        sa.Column("buffer_min", sa.Integer(), nullable=False, server_default="10"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # ------------------------------------------------------------------
    # services
    # ------------------------------------------------------------------
    op.create_table(
        "services",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("duration_min", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # ------------------------------------------------------------------
    # master_service_prices
    # ------------------------------------------------------------------
    op.create_table(
        "master_service_prices",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("master_id", sa.Integer(), sa.ForeignKey("masters.id"), nullable=False),
        sa.Column("service_id", sa.Integer(), sa.ForeignKey("services.id"), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("active_from", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_msp_master_service", "master_service_prices", ["master_id", "service_id"])

    # ------------------------------------------------------------------
    # clients
    # ------------------------------------------------------------------
    op.create_table(
        "clients",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tg_user_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("tg_chat_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "tg_status",
            postgresql.ENUM("active", "sleeping", "blocked", "unsubscribed", name="client_status", create_type=False),
            nullable=False,
            server_default="active",
        ),
        sa.Column("tg_status_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_visit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_reactivation_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # ------------------------------------------------------------------
    # appointments
    # ------------------------------------------------------------------
    op.create_table(
        "appointments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("master_id", sa.Integer(), sa.ForeignKey("masters.id"), nullable=False),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("service_id", sa.Integer(), sa.ForeignKey("services.id"), nullable=False),
        sa.Column("start_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "booked", "confirmed", "arrived", "done", "cancelled", "late_cancel",
                name="appointment_status",
                create_type=False,
            ),
            nullable=False,
            server_default="booked",
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("price_snapshot", sa.Numeric(10, 2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_appointments_master_start", "appointments", ["master_id", "start_ts"])
    op.create_index("ix_appointments_client", "appointments", ["client_id"])

    # Exclusion constraint: запрет пересечений записей одного мастера
    # Игнорируем отменённые записи (cancelled / late_cancel)
    op.execute("""
        ALTER TABLE appointments
        ADD CONSTRAINT appointments_no_overlap
        EXCLUDE USING GIST (
            master_id WITH =,
            tstzrange(start_ts, end_ts, '[)') WITH &&
        )
        WHERE (status NOT IN ('cancelled', 'late_cancel'))
    """)

    # ------------------------------------------------------------------
    # blackouts
    # ------------------------------------------------------------------
    op.create_table(
        "blackouts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("master_id", sa.Integer(), sa.ForeignKey("masters.id"), nullable=False),
        sa.Column("start_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_by_admin_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # ------------------------------------------------------------------
    # reminders
    # ------------------------------------------------------------------
    op.create_table(
        "reminders",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("appointment_id", sa.Integer(), sa.ForeignKey("appointments.id"), nullable=False),
        sa.Column("remind_at_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "type",
            postgresql.ENUM("confirm_24h", "confirm_6h", "remind_3h", name="reminder_type", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM("pending", "sent", "cancelled", "failed", name="reminder_status", create_type=False),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_reminders_pending", "reminders", ["status", "remind_at_ts"])

    # ------------------------------------------------------------------
    # events (event log — только INSERT)
    # ------------------------------------------------------------------
    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column(
            "appointment_id",
            sa.Integer(),
            sa.ForeignKey("appointments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "client_id",
            sa.Integer(),
            sa.ForeignKey("clients.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "master_id",
            sa.Integer(),
            sa.ForeignKey("masters.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("actor_type", sa.String(50), nullable=False),
        sa.Column("actor_id", sa.BigInteger(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_events_type", "events", ["event_type"])
    op.create_index("ix_events_created_at", "events", ["created_at"])

    # ------------------------------------------------------------------
    # Seed: начальные данные
    # ------------------------------------------------------------------
    # Услуги из ТЗ
    op.execute("""
        INSERT INTO services (name, duration_min, active, created_at, updated_at)
        VALUES
            ('Массаж спины', 30, true, now(), now()),
            ('Массаж ног',   30, true, now(), now())
    """)


def downgrade() -> None:
    op.drop_table("events")
    op.drop_table("reminders")
    op.drop_table("blackouts")
    op.drop_table("appointments")
    op.drop_table("clients")
    op.drop_table("master_service_prices")
    op.drop_table("services")
    op.drop_table("masters")

    sa.Enum(name="reminder_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="reminder_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="appointment_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="client_status").drop(op.get_bind(), checkfirst=True)
