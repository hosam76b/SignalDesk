"""
Scraper Orchestrator Service.
Coordinates all scraping services and manages data integration.
"""

import asyncio
import logging
from hashlib import md5
from typing import List, Dict, Any, Tuple
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func

from config import settings
from app.models.source import MonitoredSource
from app.models.keyword import Keyword
from app.models.post import AI_STATUS_PENDING, Post
from app.models.topic import Topic
from app.services.ai_queue import schedule_analysis
from app.services.scraper_service import ScraperService
from app.services.webhook_service import dispatch_post_ingested
from app.services.media_processor import schedule_media_processing
from app.services.risk_signals import screen_text

logger = logging.getLogger(__name__)


class ScraperOrchestrator:
    """
    Orchestrates scraping operations across all platforms.
    
    Manages the flow of:
    1. Fetching active sources and keywords
    2. Routing to appropriate service
    3. Normalizing data
    4. Saving to database
    5. Updating metadata
    """

    def __init__(self):
        """Initialize scraper services."""
        self.scraper_service = ScraperService()

    async def run_scraping_cycle(self, db: Session, topic_id: int | None = None) -> Dict[str, Any]:
        """
        Execute a complete scraping cycle.

        Process:
        1. Fetch active monitored sources and keywords
        2. Scrape sources concurrently (network-bound) under a semaphore
        3. Normalize results into Post schema
        4. Check for duplicates in one batched query and save new posts
        5. Hand the new post IDs to the background AI queue
        6. Update last_scraped_at timestamp

        Fetching is concurrent and persistence is serial on purpose. Scraping is
        dominated by network waits (Playwright navigation, RSS fetches), so
        overlapping it is where the throughput is. Writes stay on one session
        and one code path, because a SQLAlchemy Session is not safe to drive
        from interleaved tasks and SQLite serialises writers regardless.

        Args:
            db (Session): Database session.

        Returns:
            Dict with scraping statistics:
                - 'success': bool
                - 'total_sources': int
                - 'total_posts_found': int
                - 'new_posts_saved': int
                - 'errors': List[str]
                - 'duration_seconds': float
                - 'sources_processed': Dict with per-platform stats
        """
        start_time = datetime.now(timezone.utc)
        stats = {
            "success": True,
            "total_sources": 0,
            "total_posts_found": 0,
            "new_posts_saved": 0,
            "errors": [],
            "sources_processed": {},
        }

        try:
            logger.info("=" * 60)
            logger.info("🚀 Starting Scraping Cycle")
            logger.info("=" * 60)

            topics_query = db.query(Topic).order_by(Topic.id)
            if topic_id is not None:
                topics_query = topics_query.filter(Topic.id == topic_id)
            topics = topics_query.all()
            if not topics:
                stats["success"] = False
                stats["errors"].append(f"Topic {topic_id} not found")
                return stats

            sources = db.query(MonitoredSource).filter(
                MonitoredSource.is_active.is_(True),
                MonitoredSource.approval_status == "approved",
            ).all()
            keywords_by_topic = {
                topic.id: [keyword.word_or_phrase for keyword in db.query(Keyword).filter(
                    Keyword.topic_id == topic.id,
                    Keyword.is_active.is_(True),
                    Keyword.approval_status == "approved",
                ).all()]
                for topic in topics
            }
            search_keywords = list(dict.fromkeys(
                keyword for keywords in keywords_by_topic.values() for keyword in keywords
            ))
            stats["total_sources"] = len(sources)

            # ---- Phase 1: concurrent fetch (network-bound) --------------
            fetched = await self._fetch_all_sources(sources, search_keywords)
            stats["total_posts_found"] = sum(len(posts) for _, posts, _ in fetched)

            # ---- Phase 2: serial persistence (DB-bound) -----------------
            for source, posts, error in fetched:
                try:
                    if error is not None:
                        raise RuntimeError(error)

                    saved_for_source = 0
                    for topic in topics:
                        topic_posts = posts if not keywords_by_topic[topic.id] else [
                            post for post in posts if self._matches_keywords(post, keywords_by_topic[topic.id])
                        ]
                        if not topic_posts:
                            continue
                        saved_count = self._save_posts(db, source, topic_posts, topic.id)
                        saved_for_source += saved_count
                        stats["new_posts_saved"] += saved_count
                        if saved_count:
                            webhook_result = await dispatch_post_ingested({
                                "event": "post_ingested", "topic_id": topic.id,
                                "topic_title": topic.title, "topic_description": topic.description,
                                "ai_prompt": self._build_contextual_prompt(topic, topic_posts),
                                "source_id": source.id, "source_name": source.name,
                                "platform": source.platform, "posts": topic_posts,
                                "ingested_at": datetime.now(timezone.utc).isoformat(),
                            }, db=db)
                            if not webhook_result.get("delivered") and webhook_result.get("error") != "Webhook URL is not configured":
                                stats["errors"].append(webhook_result["error"])

                    source.last_scraped_at = datetime.now(timezone.utc)
                    source.status = "active"
                    source.last_error = None
                    source.last_error_at = None
                    db.commit()
                    platform_stats = stats["sources_processed"].setdefault(
                        source.platform, {"sources": 0, "posts_found": 0, "posts_saved": 0}
                    )
                    platform_stats["sources"] += 1
                    platform_stats["posts_found"] += len(posts)
                    platform_stats["posts_saved"] += saved_for_source
                except Exception as exc:
                    source.status = "failed"
                    source.last_error = str(exc)[:1000]
                    source.last_error_at = datetime.now(timezone.utc)
                    try:
                        db.commit()
                    except Exception:
                        db.rollback()
                    stats["success"] = False
                    stats["errors"].append(f"Error processing {source.name}: {exc}")

            return stats

        except Exception as e:
            error_msg = f"Fatal error in scraping cycle: {str(e)}"
            logger.error(f"❌ {error_msg}")
            stats["success"] = False
            stats["errors"].append(error_msg)

        finally:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            stats["duration_seconds"] = duration

        return stats

    async def _fetch_all_sources(
        self,
        sources: List[MonitoredSource],
        search_keywords: List[str],
    ) -> List[tuple[MonitoredSource, List[Dict[str, Any]], str | None]]:
        """Fetch every source concurrently, returning (source, posts, error)."""
        limit = max(1, int(getattr(settings, "scraping_max_concurrency", 6) or 6))
        semaphore = asyncio.Semaphore(limit)

        async def _one(source: MonitoredSource):
            async with semaphore:
                try:
                    posts = await self._scrape_source(source, search_keywords)
                    return (source, posts, None)
                except Exception as exc:
                    logger.warning("Scrape failed for %s: %s", source.name, exc)
                    return (source, [], str(exc))

        return list(await asyncio.gather(*(_one(source) for source in sources)))

    @staticmethod
    def _matches_keywords(post: Dict[str, Any], keywords: List[str]) -> bool:
        """Keep only content matching a keyword assigned to the current topic."""
        if not keywords:
            return True
        content = " ".join(str(post.get(field, "")) for field in ("title", "content")).lower()
        return any(keyword.lower() in content for keyword in keywords)

    @staticmethod
    def _build_contextual_prompt(topic: Topic, posts: List[Dict[str, Any]]) -> str:
        return (
            f"Analyze these posts in the context of [Topic Title: {topic.title}]. "
            f"Topic description: {topic.description or 'No description provided'}. "
            "Assess relevance and harmful-content signals only within this topic scope."
        )

    async def _scrape_source(
        self,
        source: MonitoredSource,
        keywords: List[str],
    ) -> List[Dict[str, Any]]:
        """
        Scrape a single source based on platform type.

        Args:
            source (MonitoredSource): Source to scrape.
            keywords (List[str]): Keywords to search for.

        Returns:
            List of normalized post dictionaries.
        """
        result = await self.scraper_service.scrape_source(
            source.platform,
            source.url_or_handle,
            use_apify=source.name.lower().startswith("apify:")
            or source.url_or_handle.lower().startswith("apify://"),
            keywords=keywords,
            apify_actor_id=source.apify_actor_id,
        )
        if not result.get("success"):
            raise RuntimeError(result.get("error", "Source scraping failed"))
        return result.get("posts", [])

    def _save_posts(
        self,
        db: Session,
        source: MonitoredSource,
        posts: List[Dict[str, Any]],
        topic_id: int,
    ) -> int:
        """
        Save posts to database, avoiding duplicates.

        Duplicate detection used to issue one SELECT per candidate post using
        the predicate ``source_id AND topic_id AND (external_id OR post_url OR
        content_fingerprint)``, which SQLite could only satisfy from
        ``ix_posts_topic_id`` -- so each lookup scanned every post in the topic.
        Measured at 1.75 ms per post on a 3.8k-row table: 0.35 s for a 200-post
        batch, growing quadratically within a topic.

        It is now a fixed number of queries regardless of batch size: one
        ``IN`` lookup per identity column, resolved into in-memory sets.

        Args:
            db (Session): Database session.
            source (MonitoredSource): Source the posts came from.
            posts (List[Dict]): Posts to save.

        Returns:
            Number of new posts saved.
        """
        if not posts:
            return 0

        saved_count = 0
        new_posts: list[Post] = []
        seen_keys: set[tuple[str, str]] = set()

        # --- Pass 1: normalize candidates, collect identity values --------
        candidates: List[tuple] = []
        external_ids: set[str] = set()
        post_urls: set[str] = set()
        fingerprints: set[str] = set()

        for post_data in posts:
            external_id = str(post_data.get("external_id", "") or "")
            post_url = str(post_data.get("post_url", "") or "")
            author = str(post_data.get("author", "Unknown"))
            # Truncated to the same width as the stored column so the value
            # computed here matches what is already in the database.
            content = str(post_data.get("content", "") or "")[:5000]
            fingerprint = md5(f"{content}|{author}|{post_url}".encode("utf-8")).hexdigest()
            if not (external_id or post_url or fingerprint):
                continue
            candidates.append((post_data, external_id, post_url, fingerprint, content, author))
            if external_id:
                external_ids.add(external_id)
            if post_url:
                post_urls.add(post_url)
            fingerprints.add(fingerprint)

        # --- Pass 2: one batched lookup per identity column ----------------
        # SQLAlchemy's default SQLite bind-parameter limit is 999, so chunk.
        def _chunks(values: set[str], size: int = 400):
            batch: List[str] = []
            for value in values:
                batch.append(value)
                if len(batch) >= size:
                    yield batch
                    batch = []
            if batch:
                yield batch

        existing_external: set[str] = set()
        existing_urls: set[str] = set()
        existing_fingerprints: set[str] = set()
        base_filter = (Post.source_id == source.id, Post.topic_id == topic_id)

        for chunk in _chunks(external_ids):
            existing_external.update(
                row[0] for row in
                db.query(Post.external_id).filter(*base_filter, Post.external_id.in_(chunk)).all()
                if row[0]
            )
        for chunk in _chunks(post_urls):
            existing_urls.update(
                row[0] for row in
                db.query(Post.post_url).filter(*base_filter, Post.post_url.in_(chunk)).all()
                if row[0]
            )
        for chunk in _chunks(fingerprints):
            existing_fingerprints.update(
                row[0] for row in
                db.query(Post.content_fingerprint)
                .filter(*base_filter, Post.content_fingerprint.in_(chunk)).all()
                if row[0]
            )

        # --- Pass 3: filter and insert ------------------------------------
        now = datetime.now(timezone.utc)
        for post_data, external_id, post_url, fingerprint, content, author in candidates:
            try:
                # In-batch duplicate suppression (feeds repeat entries).
                candidate_keys = {
                    ("external_id", external_id),
                    ("post_url", post_url),
                    ("fingerprint", fingerprint),
                }
                if any(value and key in seen_keys for key, value in candidate_keys):
                    logger.debug("Skipping duplicate post within scrape batch: %s", external_id)
                    continue

                if (
                    (external_id and external_id in existing_external)
                    or (post_url and post_url in existing_urls)
                    or (fingerprint and fingerprint in existing_fingerprints)
                ):
                    logger.debug("Skipping duplicate post: %s", external_id)
                    continue

                seen_keys.update((key, value) for key, value in candidate_keys if value)
                existing_external.add(external_id)
                existing_urls.add(post_url)
                existing_fingerprints.add(fingerprint)

                # Rule-based pre-screen so explicit threats are visible before the AI batch runs.
                risk = screen_text(content)

                new_post = Post(
                    topic_id=topic_id,
                    source_id=source.id,
                    external_id=post_data.get("external_id", f"unknown_{now.timestamp()}"),
                    platform=post_data.get("platform", source.platform),
                    author=author,
                    title=post_data.get("title", ""),
                    content=content,
                    content_fingerprint=fingerprint,
                    media_urls=post_data.get("media_urls", []),
                    post_url=post_data.get("post_url", ""),
                    source_url=post_data.get("source_url", source.url_or_handle),
                    raw_metadata=post_data.get("raw_metadata", {}),
                    tags=post_data.get("tags", []),
                    published_at=post_data.get("published_at", now),
                    scraped_at=now,
                    is_flagged=risk is not None,
                    is_dangerous=risk is not None,
                    violence_category=risk["violence_category"] if risk else None,
                    media_status="pending",
                    # Claimable by the background worker immediately. Set
                    # explicitly rather than relying on the column default so
                    # the row is never briefly invisible to the queue.
                    ai_status=AI_STATUS_PENDING,
                )

                db.add(new_post)
                new_posts.append(new_post)
                saved_count += 1

            except Exception as e:
                logger.warning(f"⚠️  Error saving post: {str(e)}")
                continue

        if saved_count > 0:
            try:
                # One commit for the whole batch: with synchronous=NORMAL under
                # WAL this is a single fsync instead of one per post.
                db.commit()
                logger.info(f"💾 Saved {saved_count} new posts to database")
            except Exception as e:
                logger.error(f"❌ Error committing posts to database: {str(e)}")
                db.rollback()
                return 0

            # AI analysis goes to the bounded background queue. It must not run
            # inline: blocking here froze the entire event loop for the duration
            # of every provider call in the batch.
            accepted = schedule_analysis([post.id for post in new_posts])
            if accepted < saved_count:
                logger.info(
                    "%d of %d new post(s) queued; the rest stay 'pending' and are "
                    "claimed on a later cycle",
                    accepted,
                    saved_count,
                )

            # OCR/audio-transcript extraction runs as a per-post background task so
            # it never blocks the scraping cycle or HTTP workers.
            for post in new_posts:
                if post.media_urls or post.post_url or post.source_url:
                    schedule_media_processing(post.id)

        return saved_count
