"""
Flask-приложение для веб-админки.
Монтируется в FastAPI через WSGIMiddleware по пути /admin.
"""

from flask import Flask
from flask_admin import Admin

import config as cfg
from db.session import sync_engine
from db.models import Master, Service, MasterServicePrice, Blackout
from web.admin.views import (
    BlackoutView,
    DashboardView,
    MasterServicePriceView,
    MasterView,
    ServiceView,
)


def create_flask_app() -> Flask:
    app = Flask(__name__, template_folder="templates")
    app.secret_key = cfg.ADMIN_SECRET_KEY
    app.config["FLASK_ADMIN_SWATCH"] = "cerulean"

    admin = Admin(
        app,
        name="Massage Bot Admin",
        index_view=DashboardView(name="Дашборд", url="/"),
        base_template="admin/base.html",
        template_mode="bootstrap4",
    )

    # Страница 1: Мастер / Настройки
    from db.session import SyncSessionLocal
    admin.add_view(MasterView(Master, SyncSessionLocal(), name="Мастер", category="Настройки"))

    # Страница 2: Услуги
    admin.add_view(ServiceView(Service, SyncSessionLocal(), name="Услуги", category="Настройки"))

    # Страница 3: Цены
    admin.add_view(MasterServicePriceView(
        MasterServicePrice, SyncSessionLocal(), name="Цены", category="Настройки"
    ))

    # Страница 4: Закрытия
    admin.add_view(BlackoutView(Blackout, SyncSessionLocal(), name="Закрытия"))

    return app
