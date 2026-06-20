"""Async SQLAlchemy engine + session, and the FastAPI DB dependency.

FastAPI connects with the privileged Postgres role (the connection string owner),
which bypasses Row-Level Security. Authorization is therefore enforced in
application code (every query is scoped to the authenticated user's id). RLS is
still enabled in the database as a second wall protecting any *direct* Supabase
access (e.g. the client's realtime/PostgREST access).
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.ENV == "development",
    pool_pre_ping=True,  # survive Supabase idle-connection drops
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
