import ssl

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from db.config import settings

_local = any(h in settings.DATABASE_URL for h in ["localhost", "127.0.0.1"])
_connect_args = {} if _local else {"ssl": ssl.create_default_context()}

engine = create_async_engine(settings.DATABASE_URL, connect_args=_connect_args, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    """Verify DB connectivity on startup. Schema is managed by Alembic migrations."""
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
