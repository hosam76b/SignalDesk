"""
SQLAlchemy database session configuration and setup.
Handles engine creation, session management, and dependency injection for FastAPI routes.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy.pool import StaticPool
from config import settings
import logging

logger = logging.getLogger(__name__)

# Create SQLAlchemy engine
# - pool_pre_ping=True: Tests connection before using it
# - echo=False: Set to True for SQL debugging
engine = create_engine(
    settings.db_url,
    connect_args={},
    poolclass=None,
    echo=False,
    future=True,
)

# Create session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False
)

# Declarative base for all models
Base = declarative_base()


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
