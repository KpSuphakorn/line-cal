from logging.config import fileConfig
from alembic import context
from sqlalchemy import create_engine, pool
from app.config import normalize_postgres_url, postgres_connect_args, settings
from app.db.database import Base
from app.db import models  # noqa: F401

config = context.config
migration_url = (settings.MIGRATION_DATABASE_URL or settings.DATABASE_URL).strip()
migration_url = normalize_postgres_url(migration_url)
config.set_main_option("sqlalchemy.url", migration_url.replace("%", "%%"))
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata

def run_migrations_offline():
    context.configure(url=migration_url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = create_engine(
        migration_url,
        poolclass=pool.NullPool,
        pool_pre_ping=True,
        connect_args=postgres_connect_args(migration_url),
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
