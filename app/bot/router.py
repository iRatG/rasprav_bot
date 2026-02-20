"""
Собирает все роутеры бота и подключает middleware.
"""

from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import client, master
from bot.middleware import DbSessionMiddleware


def setup_routers(dp: Dispatcher) -> None:
    """Подключает middleware и роутеры к диспетчеру."""

    # Middleware: инжектирует AsyncSession в каждый хэндлер
    from db.session import AsyncSessionLocal
    dp.update.middleware(DbSessionMiddleware(AsyncSessionLocal))

    # Роутер мастера — регистрируем первым (имеет MasterFilter)
    dp.include_router(master.router)

    # Роутер клиента — общий, без фильтра по роли
    dp.include_router(client.router)
