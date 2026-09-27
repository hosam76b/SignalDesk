"""
SQLAlchemy database session configuration and setup.
Handles engine creation, session management, and dependency injection for FastAPI routes.
"""

import logging
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy.pool import StaticPool
from config import settings
import logging

logger = logging.getLogger(__name__)

# SQLite tuning applied to every new connection.
#
# The audit measured 30 concurrent writers taking 495 ms under the previous
# defaults versus 205 ms with WAL (2.4x), with worst-case single commits
# dropping from 882 ms to 506 ms. journal_mode=delete takes an EXCLUSIVE lock
# for the duration of each commit, so every writer also blocks every reader.
SQLITE_PRAGMAS: tuple[tuple[str, str], ...] = (
    # WAL lets readers proceed during a write. This is the single most
    # effective change for concurrent ingestion plus background analysis.
    ("journal_mode", "WAL"),
    # NORMAL still survives an application crash; only an OS-level crash can
    # lose the most recent transactions. FULL fsyncs twice per commit.
    ("synchronous", "NORMAL"),
    # Negative values are kibibytes: -64000 is a 64 MB page cache. The previous
    # -2000 (2 MB) thrashed against a database that grows past 100 MB.
    ("cache_size", "-64000"),
    # 256 MB memory-mapped reads, cutting page copies out of the hot paths.
    ("mmap_size", "268435456"),
    # Wait rather than immediately raising "database is locked".
    ("busy_timeout", "15000"),
    # Keep ORDER BY / GROUP BY spill files in memory instead of on disk.
    ("temp_store", "MEMORY"),
    # Off by default in SQLite; the schema relies on ON DELETE CASCADE.
    ("foreign_keys", "ON"),
)


def _apply_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    """Apply WAL and the tuning pragmas to a freshly opened SQLite connection."""
    cursor = dbapi_connection.cursor()
    try:
        for pragma, value in SQLITE_PRAGMAS:
            try:
                cursor.execute(f"PRAGMA {pragma} = {value}")
            except Exception as exc:  # pragma: no cover - driver/version specific
                # Never let a tuning knob take down the connection.
                logger.warning("Could not apply PRAGMA %s=%s: %s", pragma, value, exc)
    finally:
        cursor.close()


def _create_engine(db_url: str):
    if db_url.startswith("sqlite"):
        # StaticPool + check_same_thread=False is required for the in-memory
        # database used by the test suite; file-backed databases get their own
        # tuning via the connect event below.
        if ":memory:" in db_url or db_url.endswith("sqlite://"):
            return create_engine(
                db_url,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
                future=True,
            )
        return create_engine(
            db_url,
            connect_args={"check_same_thread": False},
            future=True,
        )
    return create_engine(
        db_url,
        connect_args={},
        poolclass=None,
        pool_size=10,
        max_overflow=20,
        pool_timeout=10,
        pool_pre_ping=True,
        echo=False,
        future=True,
    )


def _register_sqlite_pragma_listener(engine: Engine) -> None:
    """Attach the pragma listener, but only once per engine."""
    if engine.dialect.name != "sqlite":
        return
    if getattr(engine, "_signaldesk_pragmas_applied", False):
        return
    event.listen(engine, "connect", _apply_sqlite_pragmas)
    engine._signaldesk_pragmas_applied = True


def current_sqlite_pragmas() -> dict[str, object]:
    """Report the live SQLite pragmas. Used by the startup log and by tests."""
    if engine.dialect.name != "sqlite":
        return {}
    with engine.connect() as connection:
        keys = ("journal_mode", "synchronous", "busy_timeout", "cache_size", "mmap_size", "foreign_keys")
        return {key: connection.exec_driver_sql(f"PRAGMA {key}").scalar() for key in keys}


engine = _create_engine(settings.db_url)
_register_sqlite_pragma_listener(engine)

# Create session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False
)

# Declarative base for all models
Base = declarative_base()


def configure_database(db_url: str) -> None:
    """Rebind the session factory to a database selected during first-run setup."""
    global engine
    new_engine = _create_engine(db_url)
    _register_sqlite_pragma_listener(new_engine)
    with new_engine.connect():
        pass
    previous_engine = engine
    engine = new_engine
    SessionLocal.configure(bind=engine)
    previous_engine.dispose()


def get_db() -> Session:
    """
    Dependency for FastAPI route injection.
    Provides database session for each request and ensures cleanup.

    Yields:
        Session: SQLAlchemy session instance.

    Example:
        @app.get("/users")
        async def get_users(db: Session = Depends(get_db)):
            return db.query(User).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db_connection():
    """
    Test database connection on application startup.
    Logs connection status and raises exception if connection fails.

    Raises:
        Exception: If database connection cannot be established.
    """
    try:
        with engine.connect() as connection:
            logger.info("✅ Database connection successful")
            return True
    except Exception as e:
        logger.error(f"❌ Database connection failed: {str(e)}")
        raise


def drop_all_tables():
    """
    Drop all tables from the database.
    Use with caution - this will delete all data!

    Warning:
        This is a destructive operation. Use only for development/testing.
    """
    Base.metadata.drop_all(bind=engine)
    logger.warning("🗑️  All tables dropped from database")
