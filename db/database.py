import ssl

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from db.config import settings

# No SSL for local or Railway private-network URLs.
# Disable cert verification for Railway's self-signed certs.
_local = any(h in settings.DATABASE_URL for h in ["localhost", "127.0.0.1", ".railway.internal"])
if _local:
    _connect_args: dict = {}
else:
    _ssl_ctx = ssl.create_default_context()
    _ssl_ctx.check_hostname = False
    _ssl_ctx.verify_mode = ssl.CERT_NONE
    _connect_args = {"ssl": _ssl_ctx}

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
