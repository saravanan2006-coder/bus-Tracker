"""Async SQLAlchemy engine, session factory and declarative base."""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _engine_kwargs() -> dict:
    kwargs: dict = {"echo": settings.db_echo}
    if settings.is_sqlite:
        # aiosqlite does not support the pool_size options.
        return {**kwargs, "connect_args": {"check_same_thread": False}}
    return {
        **kwargs,
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_pre_ping": True,
    }


engine = create_async_engine(settings.database_url, **_engine_kwargs())

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a scoped async session."""
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    """Create tables. Production deployments should use migrations instead."""
    # Import models so they are registered on Base.metadata.
    import app.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
