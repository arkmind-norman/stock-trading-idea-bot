from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context

from db.config import settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

from db.database import Base  # noqa: E402
import db.models  # noqa: E402, F401

target_metadata = Base.metadata

# Convert asyncpg URL → psycopg2 URL for synchronous Alembic use.
_db_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://", 1)
config.set_main_option("sqlalchemy.url", _db_url)

# Railway private-network URLs (.railway.internal) don't need SSL.
# Public URLs require sslmode=require.
_internal = any(h in _db_url for h in [".railway.internal", "localhost", "127.0.0.1"])
_connect_args = {} if _internal else {"sslmode": "require"}


def run_migrations_offline() -> None:
    context.configure(
        url=_db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(
        _db_url,
        poolclass=pool.NullPool,
        connect_args=_connect_args,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
