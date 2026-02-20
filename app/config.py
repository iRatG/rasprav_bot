import os
from pathlib import Path
from dotenv import load_dotenv

# .env лежит на уровень выше (рядом с docker-compose.yml)
_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)


def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise RuntimeError(f"Обязательная переменная окружения не задана: {key}")
    return val


# Telegram
BOT_TOKEN: str = _require("BOT_TOKEN")
BOT_USERNAME: str = os.getenv("BOT_USERNAME", "rasprav_bot")
WEBHOOK_SECRET: str = _require("WEBHOOK_SECRET")
WEBHOOK_URL: str = _require("WEBHOOK_URL")

# Database
DATABASE_URL: str = _require("DATABASE_URL")        # async (asyncpg)
SYNC_DATABASE_URL: str = _require("SYNC_DATABASE_URL")  # sync (psycopg2)

# Flask-Admin
ADMIN_SECRET_KEY: str = _require("ADMIN_SECRET_KEY")

# Бизнес-правила (из ТЗ, зафиксированы)
TIMEZONE = "Europe/Moscow"
BOOKING_HORIZON_DAYS = 7         # горизонт записи — 7 дней вперёд
MIN_BOOKING_AHEAD_HOURS = 1      # минимум за 1 час до начала
DEFAULT_BUFFER_MIN = 10          # буфер между клиентами по умолчанию
BUFFER_OPTIONS = (5, 10, 15)     # допустимые значения буфера
WORK_START = "09:00"             # рабочее окно мастера (московское время)
WORK_END = "20:00"
SERVICE_DURATION_MIN = 30        # длительность услуги

# Lifecycle клиентов
SLEEPING_THRESHOLD_DAYS = 90     # нет визитов > 90 дней → sleeping
REACTIVATION_COOLDOWN_DAYS = 90  # реактивационное сообщение не чаще раза в 3 месяца
