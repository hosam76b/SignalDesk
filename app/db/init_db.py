"""
Database initialization and seeding.
Creates all tables and seeds initial data on first run.
"""

import logging
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from app.db import session
from app.db.session import Base, SessionLocal
from app.models import AuditLog, Topic, User  # This import triggers all model registrations
from app.core.security import hash_password

logger = logging.getLogger(__name__)

DEFAULT_TOPIC_TITLE = "General Monitoring"
DEFAULT_TOPIC_DESCRIPTION = "المراقبة العامة"


class _EngineProxy:
    """Live handle on ``session.engine``, resolved on every attribute access.

    ``app.db.session.configure_database()`` rebinds ``session.engine`` during
    first-run setup. An Engine imported *by value* would keep pointing at the
    pre-setup database, so these helpers would create, migrate, and then drop
    tables in the wrong place. Forwarding instead of capturing means one
    rebind is picked up everywhere.
    """

    def __getattr__(self, name: str):
        return getattr(session.engine, name)

    def unwrap(self):
        """The real Engine, for APIs that reject a proxy (e.g. ``bind=``)."""
        return session.engine

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<live engine proxy -> {session.engine!r}>"


#: Module-level handle on the engine these helpers act on. It is also the patch
#: point tests use to redirect initialization at a throwaway database, which is
#: why the helpers resolve it through ``_active_engine()`` instead of reading
#: ``session.engine`` directly.
engine = _EngineProxy()


def _active_engine():
    """Return a real ``Engine`` for the initialization helpers.

    Reads the module-level ``engine`` hook via ``globals()`` so a test's
    ``monkeypatch.setattr(init_db, "engine", other_engine)`` is honoured, while
    production unwraps the proxy to whatever ``session.engine`` currently is.
    """
    candidate = globals()["engine"]
    return candidate.unwrap() if isinstance(candidate, _EngineProxy) else candidate


def migrate_topic_schema():
    """Add topic ownership to existing tables and backfill legacy rows."""
    bind = _active_engine()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    with bind.begin() as connection:
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

        for table in ("keywords", "posts"):
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

            # AI analysis lifecycle columns. create_all() never adds columns to
            # an existing table, and the ORM selects every mapped column on
            # every Post query -- so without these an upgraded install fails
            # immediately with "no such column: posts.ai_status".
            for column_name, column_type in (
                ("ai_status", "VARCHAR(20) NOT NULL DEFAULT 'pending'"),
                ("ai_analyzed_at", "TIMESTAMP"),
            ):
                if column_name not in post_columns:
                    connection.execute(text(f"ALTER TABLE posts ADD COLUMN {column_name} {column_type}"))

            # create_all() never widens an existing table, so the ALTERs above
            # just added columns: re-read the column set before anything below
            # references it. A genuinely legacy table may still be missing
            # columns this install never had, and this self-heal must degrade
            # rather than abort the whole startup with "no such column".
            post_columns = {
                column["name"] for column in inspect(connection).get_columns("posts")
            }

            # Replace the '' sentinel with NULL. The old pending-post predicate
            # was `ai_summary IS NULL OR ai_summary = ''`, and that second
            # disjunct cannot use any index on ai_status -- it forced the full
            # table scan the audit measured at 99 ms and growing linearly.
            if "ai_summary" in post_columns:
                connection.execute(
                    text("UPDATE posts SET ai_summary = NULL WHERE ai_summary = ''")
                )
            if "severity_level" in post_columns:
                connection.execute(
                    text("UPDATE posts SET severity_level = NULL WHERE severity_level = ''")
                )

            if "ai_status" in post_columns:
                # Backfill, mirroring migration 0009. Without this, every
                # historical post defaults to 'pending' and the worker is handed
                # the entire archive instead of just the unanalysed subset.
                already_analyzed = " OR ".join(
                    f"{name} IS NOT NULL"
                    for name in ("ai_summary", "severity_level")
                    if name in post_columns
                )
                if already_analyzed:
                    analyzed_at = (
                        "COALESCE(scraped_at, CURRENT_TIMESTAMP)"
                        if "scraped_at" in post_columns
                        else "CURRENT_TIMESTAMP"
                    )
                    connection.execute(
                        text(
                            f"UPDATE posts SET ai_status = 'done', "
                            f"ai_analyzed_at = {analyzed_at} "
                            f"WHERE ({already_analyzed}) AND ai_status = 'pending'"
                        )
                    )
                # Rows with no text can never be analyzed; 'pending' would make
                # the worker claim them on every cycle forever.
                if "content" in post_columns:
                    connection.execute(
                        text(
                            "UPDATE posts SET ai_status = 'skipped' "
                            "WHERE (content IS NULL OR TRIM(content) = '') "
                            "AND ai_status = 'pending'"
                        )
                    )

            is_sqlite = connection.dialect.name == "sqlite"
            post_indexes = {
                index["name"] for index in inspect(connection).get_indexes("posts")
            }
            for index_name, index_columns in (
                ("ix_posts_flagged", ("is_flagged", "id")),
                ("ix_posts_severity", ("severity_level", "id")),
                ("ix_posts_dedup_external", ("source_id", "topic_id", "external_id")),
                ("ix_posts_dedup_url", ("source_id", "topic_id", "post_url")),
                ("ix_posts_dedup_fingerprint", ("source_id", "topic_id", "content_fingerprint")),
            ):
                if index_name in post_indexes:
                    continue
                missing = [c for c in index_columns if c not in post_columns]
                if missing:
                    # An index is an optimization, not a correctness
                    # requirement, so a legacy table simply goes without it.
                    logger.debug(
                        "Skipping index %s; posts is missing column(s) %s",
                        index_name,
                        ", ".join(missing),
                    )
                    continue
                connection.execute(
                    text(f"CREATE INDEX {index_name} ON posts ({', '.join(index_columns)})")
                )

            # The claim query filters on `ai_status IN ('pending','failed')`, so
            # the partial index must cover both branches. An index narrowed to
            # `= 'pending'` is unusable for the claim and the query falls back to
            # a full table scan.
            if "ix_posts_ai_queue" not in post_indexes:
                if is_sqlite:
                    connection.execute(
                        text(
                            "CREATE INDEX ix_posts_ai_queue ON posts (id) "
                            "WHERE ai_status IN ('pending', 'failed')"
                        )
                    )
                else:
                    connection.execute(
                        text("CREATE INDEX ix_posts_ai_queue ON posts (id)")
                    )
            if "ix_posts_ai_pending" in post_indexes:
                # Superseded by ix_posts_ai_queue; leaving it in place wastes
                # write amplification on every status transition.
                connection.execute(text("DROP INDEX ix_posts_ai_pending"))

            # Export Data tab. Same rationale as the ORM declarations in
            # app/models/post.py: ix_posts_ai_queue is partial to the
            # unanalysed subset and keyed on `id`, so it cannot serve a
            # `published_at` window or a `done`/`skipped` status filter.
            for index_name, index_columns in (
                ("ix_posts_export_date", ("published_at", "id")),
                ("ix_posts_export_ai_date", ("ai_status", "published_at", "id")),
            ):
                if index_name in post_indexes:
                    continue
                missing = [c for c in index_columns if c not in post_columns]
                if missing:
                    logger.debug(
                        "Skipping index %s; posts is missing column(s) %s",
                        index_name,
                        ", ".join(missing),
                    )
                    continue
                connection.execute(
                    text(f"CREATE INDEX {index_name} ON posts ({', '.join(index_columns)})")
                )

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

        if connection.dialect.name == "postgresql":
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
    2. Applies compatibility migrations without creating credentials
    
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
        bind = _active_engine()
        Base.metadata.create_all(bind=bind)
        logger.info("✅ Database tables created/verified successfully")

        migrate_topic_schema()

        # create_all does not add columns to tables that already exist.
        if bind.dialect.name == "postgresql":
            with bind.begin() as connection:
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
        bind = _active_engine()
        Base.metadata.drop_all(bind=bind)
        logger.warning("✅ All tables dropped")

        # Recreate all tables
        logger.info("🔄 Creating database tables...")
        Base.metadata.create_all(bind=bind)
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
