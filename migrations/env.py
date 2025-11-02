from logging.config import fileConfig
from sqlalchemy import pool, engine_from_config
from sqlalchemy.ext.asyncio import AsyncEngine
from alembic import context
from app.db.base import Base
from app.db.models import board, item, cluster_label
import os

# Alembic Config object
config = context.config
fileConfig(config.config_file_name) # type: ignore
config.set_main_option("sqlalchemy.url", os.getenv("DATABASE_URL", ""))

target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(
        url=os.getenv("DATABASE_URL", ""),
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online():
    connectable = AsyncEngine(
        engine_from_config(
            config.get_section(config.config_ini_section), # type: ignore
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    import asyncio
    asyncio.run(run_migrations_online())