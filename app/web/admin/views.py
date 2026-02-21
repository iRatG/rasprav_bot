"""
Flask-Admin views для 5 страниц из ТЗ:
  1. Мастер / Настройки
  2. Услуги
  3. Цены (master × service)
  4. Закрытия (Blackouts)
  5. Дашборд
"""

from flask import redirect, request, session, url_for
from flask_admin import AdminIndexView, expose
from flask_admin.contrib.sqla import ModelView
from sqlalchemy import func, and_
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import config as cfg

TZ = ZoneInfo(cfg.TIMEZONE)


def _is_authenticated() -> bool:
    return "admin_tg_id" in session


class SecureModelView(ModelView):
    """Базовый ModelView с защитой через Telegram Login."""

    can_delete = True
    can_create = True
    can_edit = True
    page_size = 50

    def is_accessible(self):
        return _is_authenticated()

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("admin.login_view"))


class MasterView(SecureModelView):
    """Страница 1: настройки мастера."""
    column_list = ["display_name", "tg_user_id", "timezone", "work_start_time", "work_end_time", "buffer_min"]
    column_labels = {
        "display_name": "Имя",
        "tg_user_id": "Telegram ID",
        "timezone": "Часовой пояс",
        "work_start_time": "Начало работы",
        "work_end_time": "Конец работы",
        "buffer_min": "Буфер (мин)",
    }
    form_choices = {
        "buffer_min": [(5, "5 мин"), (10, "10 мин"), (15, "15 мин")],
    }


class ServiceView(SecureModelView):
    """Страница 2: услуги."""
    column_list = ["name", "duration_min", "active", "updated_at"]
    column_labels = {
        "name": "Название",
        "duration_min": "Длительность (мин)",
        "active": "Активна",
        "updated_at": "Обновлено",
    }
    column_editable_list = ["active"]


class MasterServicePriceView(SecureModelView):
    """Страница 3: цены мастер × услуга."""
    column_list = ["master", "service", "price", "active_from"]
    column_labels = {
        "master": "Мастер",
        "service": "Услуга",
        "price": "Цена (₽)",
        "active_from": "Действует с",
    }
    column_sortable_list = ["price", "active_from"]


class ClientView(SecureModelView):
    """Клиенты бота."""
    can_create = False
    can_delete = False
    column_list = ["tg_user_id", "first_name", "last_name", "username", "tg_status", "created_at"]
    column_labels = {
        "tg_user_id": "Telegram ID",
        "first_name": "Имя",
        "last_name": "Фамилия",
        "username": "Username",
        "tg_status": "Статус",
        "created_at": "Зарегистрирован",
    }
    column_searchable_list = ["first_name", "last_name", "username"]
    column_sortable_list = ["created_at", "tg_status"]
    column_default_sort = ("created_at", True)
    column_formatters = {
        "username": lambda v, c, m, p: f"@{m.username}" if m.username else "—",
        "created_at": lambda v, c, m, p: m.created_at.astimezone(TZ).strftime("%d.%m.%Y %H:%M"),
    }


class BlackoutView(SecureModelView):
    """Страница 4: закрытия."""
    column_list = ["master", "start_ts", "end_ts", "reason", "created_at"]
    column_labels = {
        "master": "Мастер",
        "start_ts": "Начало",
        "end_ts": "Конец",
        "reason": "Причина",
        "created_at": "Создано",
    }

    def on_model_change(self, form, model, is_created):
        """При создании blackout'а — отмечаем admin_id из сессии."""
        if is_created:
            model.created_by_admin_id = session.get("admin_tg_id")


class DashboardView(AdminIndexView):
    """Страница 5: дашборд + логин."""

    @expose("/")
    def index(self):
        if not _is_authenticated():
            return redirect(url_for("admin.login_view"))

        # Статистика из БД через sync сессию
        from db.session import SyncSessionLocal
        from db.models.appointment import Appointment, AppointmentStatus

        db = SyncSessionLocal()
        try:
            now_local = datetime.now(TZ)
            today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)
            week_end = today_start + timedelta(days=7)

            # Сегодня
            today_appointments = db.query(Appointment).filter(
                and_(
                    Appointment.start_ts >= today_start,
                    Appointment.start_ts < today_end,
                    Appointment.status.in_([
                        AppointmentStatus.booked,
                        AppointmentStatus.confirmed,
                        AppointmentStatus.arrived,
                    ]),
                )
            ).order_by(Appointment.start_ts).all()

            # Неподтверждённые (риск неявки)
            unconfirmed = db.query(Appointment).filter(
                and_(
                    Appointment.status == AppointmentStatus.booked,
                    Appointment.confirmed_at.is_(None),
                    Appointment.start_ts > now_local,
                    Appointment.start_ts < week_end,
                )
            ).all()

            return self.render(
                "admin/dashboard.html",
                today_appointments=today_appointments,
                unconfirmed=unconfirmed,
                now=now_local,
                tz=TZ,
            )
        finally:
            db.close()

    @expose("/login")
    def login_view(self):
        return self.render(
            "admin/login.html",
            bot_username=cfg.BOT_USERNAME,
        )

    @expose("/dev-login")
    def dev_login_view(self):
        """Вход по секретному ключу (для IP-окружений без Telegram Widget)."""
        key = request.args.get("key", "")
        if not key or key != cfg.ADMIN_SECRET_KEY:
            return "Не найдено", 404
        from db.session import SyncSessionLocal
        from db.models.master import Master
        db = SyncSessionLocal()
        try:
            master = db.query(Master).first()
            if not master:
                return "Нет мастеров в БД", 404
            session["admin_tg_id"] = master.tg_user_id
            session["admin_name"] = master.display_name
        finally:
            db.close()
        return redirect(url_for("admin.index"))

    @expose("/auth")
    def auth_view(self):
        """Callback от Telegram Login Widget."""
        from web.auth import verify_telegram_auth
        data = dict(request.args)
        if not verify_telegram_auth(data, cfg.BOT_TOKEN):
            return "Ошибка авторизации", 403

        # Проверяем что этот tg_user_id есть в таблице masters
        from db.session import SyncSessionLocal
        from db.models.master import Master
        db = SyncSessionLocal()
        try:
            tg_id = int(data["id"])
            master = db.query(Master).filter(Master.tg_user_id == tg_id).first()
            if not master:
                return "Доступ запрещён: вы не являетесь мастером", 403
        finally:
            db.close()

        session["admin_tg_id"] = tg_id
        session["admin_name"] = data.get("first_name", "Мастер")
        return redirect(url_for("admin.index"))

    @expose("/logout")
    def logout_view(self):
        session.clear()
        return redirect(url_for("admin.login_view"))
