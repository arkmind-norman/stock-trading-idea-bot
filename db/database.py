from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from db.config import settings

# Explicitly disable SSL — Railway's TCP proxy is plain TCP and doesn't
# terminate SSL. asyncpg otherwise picks up PGSSLMODE from the environment
# (injected by Railway's Postgres plugin) and tries SSL, which hangs.
_connect_args: dict = {"ssl": False}

engine = create_async_engine(settings.DATABASE_URL, connect_args=_connect_args, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    """Create all tables on startup (idempotent — skips existing tables)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
