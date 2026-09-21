from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import normalize_postgres_url, postgres_connect_args, settings, validate_production_settings

db_url = settings.DATABASE_URL.strip()
db_url = normalize_postgres_url(db_url)

# Configure engine arguments
connect_args = postgres_connect_args(db_url)
engine_kwargs = {
    "pool_pre_ping": True
}

if db_url.lower().startswith("sqlite"):
    connect_args["check_same_thread"] = False
else:
    # Supabase / PostgreSQL specific optimizations
    engine_kwargs["pool_size"] = settings.DB_POOL_SIZE
    engine_kwargs["max_overflow"] = settings.DB_MAX_OVERFLOW

engine = create_engine(
    db_url,
    connect_args=connect_args,
    **engine_kwargs
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    # Imported for its side effect: registers every model on Base.metadata
    # before create_all below.
    from app.db import models  # noqa: F401
    validate_production_settings()
    if settings.APP_ENV.lower() in {"production", "prod"}:
        # Production schema changes must be applied by Alembic before startup.
        return
    Base.metadata.create_all(bind=engine)
