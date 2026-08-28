"""
Database initialization and seeding.
Creates all tables and seeds initial data on first run.
"""

import logging
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from app.db.session import Base, engine, SessionLocal
from app.models import AuditLog, Topic, User  # This import triggers all model registrations
from app.core.security import hash_password

logger = logging.getLogger(__name__)

DEFAULT_TOPIC_TITLE = "General Monitoring"
DEFAULT_TOPIC_DESCRIPTION = "المراقبة العامة"


def migrate_topic_schema():
    """Add topic ownership to existing tables and backfill legacy rows."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as connection:
        if "topics" not in existing_tables:
            Base.metadata.create_all(bind=connection, tables=[Topic.__table__])
        topic_id = connection.execute(
            text("SELECT id FROM topics WHERE title = :title"),
            {"title": DEFAULT_TOPIC_TITLE},
        ).scalar_one_or_none()
        if topic_id is None:
            connection.execute(
                text(
                    "INSERT INTO topics (title, description, created_at) "
                    "VALUES (:title, :description, CURRENT_TIMESTAMP)"
                ),
                {"title": DEFAULT_TOPIC_TITLE, "description": DEFAULT_TOPIC_DESCRIPTION},
            )
            topic_id = connection.execute(
                text("SELECT id FROM topics WHERE title = :title"),
                {"title": DEFAULT_TOPIC_TITLE},
            ).scalar_one()

        for table in ("monitored_sources", "keywords", "posts"):
            if table not in existing_tables:
                continue
            columns = {column["name"] for column in inspect(connection).get_columns(table)}
            if "topic_id" not in columns:
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN topic_id INTEGER"))
            connection.execute(
                text(f"UPDATE {table} SET topic_id = :topic_id WHERE topic_id IS NULL"),
                {"topic_id": topic_id},
            )

        if "monitored_sources" in existing_tables:
            source_columns = {column["name"] for column in inspect(connection).get_columns("monitored_sources")}
            for column_name, column_type, default_value in (
                ("target_type", "VARCHAR(30)", "url"),
                ("apify_actor_id", "VARCHAR(255)", None),
                ("status", "VARCHAR(20)", "active"),
                    ("last_error", "VARCHAR(1000)", None),
                    ("last_error_at", "TIMESTAMP", None),
            ):
                if column_name not in source_columns:
                    connection.execute(text(f"ALTER TABLE monitored_sources ADD COLUMN {column_name} {column_type}"))
                    if default_value is not None:
                        connection.execute(text(f"UPDATE monitored_sources SET {column_name} = :value WHERE {column_name} IS NULL"), {"value": default_value})

        if "posts" in existing_tables:
            post_columns = {column["name"] for column in inspect(connection).get_columns("posts")}
            for column_name in ("is_important", "is_dangerous", "content_fingerprint", "sentiment", "sentiment_score", "entities"):
                if column_name not in post_columns:
                    column_type = {"is_important": "BOOLEAN DEFAULT FALSE", "is_dangerous": "BOOLEAN DEFAULT FALSE", "content_fingerprint": "VARCHAR(32)", "sentiment": "VARCHAR(20)", "sentiment_score": "INTEGER", "entities": "JSON"}[column_name]
                    connection.execute(text(f"ALTER TABLE posts ADD COLUMN {column_name} {column_type}"))

        if "prompt_templates" in existing_tables:
            prompt_template_columns = {column["name"] for column in inspect(connection).get_columns("prompt_templates")}
            for column_name, column_type, default_value in (
                ("provider", "VARCHAR(50)", "ollama"),
                ("model_name", "VARCHAR(255)", "qwen2.5:7b"),
            ):
                if column_name not in prompt_template_columns:
                    connection.execute(text(f"ALTER TABLE prompt_templates ADD COLUMN {column_name} {column_type} DEFAULT '{default_value}'"))
                    connection.execute(text(f"UPDATE prompt_templates SET {column_name} = :value WHERE {column_name} IS NULL"), {"value": default_value})

        if "audit_logs" not in existing_tables:
            Base.metadata.create_all(bind=connection, tables=[AuditLog.__table__])

        if "users" in existing_tables:
            connection.execute(text("UPDATE users SET role = 'super_admin' WHERE role = 'admin'"))
            connection.execute(text("UPDATE users SET role = 'topic_monitor' WHERE role = 'analyst'"))

        if engine.dialect.name == "postgresql":
            for table in ("monitored_sources", "keywords", "posts"):
                if table in existing_tables:
                    foreign_keys = inspect(connection).get_foreign_keys(table)
                    has_topic_fk = any(
                        fk.get("referred_table") == "topics" and "topic_id" in fk.get("constrained_columns", [])
                        for fk in foreign_keys
                    )
                    if not has_topic_fk:
                        connection.execute(text(
                            f"ALTER TABLE {table} ADD CONSTRAINT fk_{table}_topic_id "
                            "FOREIGN KEY (topic_id) REFERENCES topics(id)"
                        ))
                    connection.execute(text(f"ALTER TABLE {table} ALTER COLUMN topic_id SET NOT NULL"))

    logger.info("Topic schema migration and legacy backfill complete")


def init_db():
    """
    Initialize database on application startup.
    
    Performs the following actions:
    1. Creates all database tables from SQLAlchemy models
    2. Seeds default admin user if no users exist in database
    
    This function should be called in the FastAPI startup event.
    
    Raises:
        Exception: If database operations fail (connection, creation, seeding)
    """
    try:
        logger.info("=" * 60)
        logger.info("🚀 Database Initialization Started")
        logger.info("=" * 60)

        # Step 1: Create all tables from models
        logger.info("🔄 Creating database tables...")
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Database tables created/verified successfully")

        migrate_topic_schema()

        # create_all does not add columns to tables that already exist.
        if engine.dialect.name == "postgresql":
            with engine.begin() as connection:
                for column_name, column_type in (
                    ("title", "VARCHAR(1000)"),
                    ("source_url", "VARCHAR(1000)"),
                    ("raw_metadata", "JSON"),
                    ("tags", "JSON"),
                ):
                    connection.execute(text(
                        f"ALTER TABLE posts ADD COLUMN IF NOT EXISTS {column_name} {column_type}"
                    ))
            logger.info("✅ Post export columns verified")

        # Step 2: Seed default admin user if database is empty
        logger.info("🔄 Checking for existing users...")
        db = SessionLocal()
        try:
            existing_user_count = db.query(User).count()

            if existing_user_count > 0:
                logger.info(f"✅ Database already has {existing_user_count} user(s), skipping seeding")
            else:
                # Create default admin user
                admin_user = User(
                    email="admin@example.com",
                    hashed_password=hash_password("admin123"),
                    full_name="Administrator",
                    role="super_admin",
                    is_active=True
                )

                db.add(admin_user)
                db.commit()
                db.refresh(admin_user)

                logger.info(f"✅ Default admin user created: {admin_user.email} (ID: {admin_user.id})")
                logger.info("   ℹ️  Default credentials: email=admin@example.com, password=admin123")
                logger.info("   ⚠️  IMPORTANT: Change these credentials in production!")

        finally:
            db.close()

        logger.info("=" * 60)
        logger.info("✅ Database Initialization Complete")
        logger.info("=" * 60)

    except Exception as e:
        logger.error("=" * 60)
        logger.error(f"❌ Database initialization failed: {str(e)}")
        logger.error("=" * 60)
        raise


def reset_database():
    """
    Reset the database by dropping all tables and recreating them.
    
    WARNING: This will DELETE all data! Use only for development/testing.
    
    This function:
    1. Drops all existing tables
    2. Recreates all tables from models
    3. Seeds default admin user
    """
    try:
        logger.warning("=" * 60)
        logger.warning("⚠️  DESTRUCTIVE OPERATION: Resetting database...")
        logger.warning("=" * 60)

        # Drop all tables
        logger.warning("🗑️  Dropping all tables...")
        Base.metadata.drop_all(bind=engine)
        logger.warning("✅ All tables dropped")

        # Recreate all tables
        logger.info("🔄 Creating database tables...")
        Base.metadata.create_all(bind=engine)
        logger.info("✅ All tables recreated")

        # Seed default data
        db = SessionLocal()
        try:
            admin_user = User(
                email="admin@example.com",
                hashed_password=hash_password("admin123"),
                full_name="Administrator",
                role="super_admin",
                is_active=True
            )

            db.add(admin_user)
            db.commit()
            db.refresh(admin_user)

            logger.info(f"✅ Default admin user created: {admin_user.email} (ID: {admin_user.id})")

        finally:
            db.close()

        logger.info("=" * 60)
        logger.info("✅ Database reset complete")
        logger.info("=" * 60)

    except Exception as e:
        logger.error("=" * 60)
        logger.error(f"❌ Database reset failed: {str(e)}")
        logger.error("=" * 60)
        raise
