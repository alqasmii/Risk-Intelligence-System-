"""
Database Layer
==============
Manages the SQLAlchemy engine, session factory, and ORM base class.

Production guidance:
  - Replace SQLite URL with PostgreSQL (asyncpg driver for async FastAPI)
  - Add QueuePool: pool_size=10, max_overflow=20, pool_timeout=30
  - Point read-only reporting queries to a read replica endpoint
  - Enable Alembic for schema versioning/migrations
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import settings


# ── Engine ────────────────────────────────────────────────────────────────────
# Supports both SQLite (local dev) and PostgreSQL (production / Vercel + Neon)
# pg8000 is a pure-Python PostgreSQL driver (no C extensions) — required for
# Vercel Lambda which cannot load platform-specific binaries like psycopg2.
import re as _re
_db_url = settings.DATABASE_URL
if "postgresql" in _db_url and "pg8000" not in _db_url:
    _db_url = _db_url.replace("postgresql+psycopg2://", "postgresql+pg8000://", 1)
    _db_url = _db_url.replace("postgresql://", "postgresql+pg8000://", 1)
    # pg8000 doesn't support channel_binding — strip it from the query string
    _db_url = _re.sub(r'[&?]channel_binding=[^&]*', '', _db_url)
    _db_url = _re.sub(r'\?&', '?', _db_url)  # clean up ?& if channel_binding was first param

_is_sqlite = _db_url.startswith("sqlite")

engine = create_engine(
    _db_url,
    # check_same_thread is a SQLite-only arg; omit for PostgreSQL
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    echo=settings.DEBUG,
    # Neon uses PgBouncer in transaction mode — these settings keep connections healthy
    pool_pre_ping=True,      # test connection before every checkout (handles stale sockets)
    pool_recycle=300,        # recycle connections every 5 min (Neon idles out at ~5 min)
)


if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _configure_sqlite(dbapi_connection, connection_record):
        """
        Applies performance and correctness pragmas to every new SQLite connection.
        WAL mode allows concurrent reads alongside write operations — critical when
        the ingestion pipeline writes while the API serves reporting queries.
        """
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")    # Write-Ahead Logging for concurrent reads
        cursor.execute("PRAGMA foreign_keys=ON")      # Enforce referential integrity
        cursor.execute("PRAGMA synchronous=NORMAL")   # Balance speed vs. durability
        cursor.close()


# ── Session Factory ───────────────────────────────────────────────────────────
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ── ORM Base ──────────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── FastAPI Dependency ────────────────────────────────────────────────────────
def get_db():
    """
    Provides a database session scoped to a single HTTP request.
    The try/finally block guarantees the session is closed (and the
    underlying connection returned to the pool) even if an exception occurs.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables() -> None:
    """
    Creates all ORM-mapped tables in the database.
    Called once at application startup if tables do not exist.
    In production, defer to Alembic migrations instead.
    """
    # Import models so SQLAlchemy registers their Table metadata before create_all
    from app.models import client, transaction, loan, risk_score, anomaly  # noqa: F401

    Base.metadata.create_all(bind=engine)
