from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from typing import AsyncGenerator

import config as cfg

# ---------------------------------------------------------------------------
# Async engine + session — используется в боте и FastAPI
# ---------------------------------------------------------------------------
async_engine = create_async_engine(
    cfg.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


# ---------------------------------------------------------------------------
# Sync engine + session — используется в Flask-Admin
# ---------------------------------------------------------------------------
sync_engine = create_engine(
    cfg.SYNC_DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)
SyncSessionLocal = sessionmaker(sync_engine, expire_on_commit=False)


def get_sync_db() -> Session:
    return SyncSessionLocal()


# ---------------------------------------------------------------------------
# Base для всех моделей — единственный, общий для обоих движков
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    pass
