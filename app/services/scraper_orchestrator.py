"""
Scraper Orchestrator Service.
Coordinates all scraping services and manages data integration.
"""

import logging
from hashlib import md5
from typing import List, Dict, Any, Tuple
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.source import MonitoredSource
from app.models.keyword import Keyword
from app.models.post import Post
from app.models.topic import Topic
from app.services.scraper_service import ScraperService
from app.services.webhook_service import dispatch_post_ingested
from app.services.media_processor import schedule_media_processing

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
        2. For each source, scrape based on platform type
        3. Normalize results into Post schema
        4. Check for duplicates and save new posts
        5. Update last_scraped_at timestamp
        
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

            for source in sources:
                try:
                    source.status = "pending"
                    source.last_error = None
                    source.last_error_at = None
                    db.commit()
                    posts = await self._scrape_source(source, search_keywords)
                    stats["total_posts_found"] += len(posts)
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
                    db.commit()
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

        Args:
            db (Session): Database session.
            source (MonitoredSource): Source the posts came from.
            posts (List[Dict]): Posts to save.

        Returns:
            Number of new posts saved.
        """
        saved_count = 0
        new_posts: list[Post] = []
        seen_keys: set[tuple[str, str]] = set()

        for post_data in posts:
            try:
                # Check for duplicates
                external_id = post_data.get("external_id", "")
                post_url = post_data.get("post_url", "")
                content = post_data.get("content", "")[:5000]
                fingerprint = md5(
                    f"{content}|{post_data.get('author', 'Unknown')}|{post_url}".encode("utf-8")
                ).hexdigest()

                candidate_keys = {
                    ("external_id", external_id),
                    ("post_url", post_url),
                    ("fingerprint", fingerprint),
                }
                if any(value and key in seen_keys for key, value in candidate_keys):
                    logger.debug("Skipping duplicate post within scrape batch: %s", external_id)
                    continue

                if external_id or post_url or fingerprint:
                    existing = db.query(Post).filter(
                        Post.source_id == source.id,
                        Post.topic_id == topic_id,
                        ((Post.external_id == external_id) | (Post.post_url == post_url) | (Post.content_fingerprint == fingerprint)),
                    ).first()

                    if existing:
                        logger.debug(f"Skipping duplicate post: {external_id}")
                        continue

                seen_keys.update((key, value) for key, value in candidate_keys if value)

                # Create new Post object
                new_post = Post(
                    topic_id=topic_id,
                    source_id=source.id,
                    external_id=post_data.get("external_id", f"unknown_{datetime.now(timezone.utc).timestamp()}"),
                    platform=post_data.get("platform", source.platform),
                    author=post_data.get("author", "Unknown"),
                    title=post_data.get("title", ""),
                    content=content,
                    content_fingerprint=fingerprint,
                    media_urls=post_data.get("media_urls", []),
                    post_url=post_data.get("post_url", ""),
                    source_url=post_data.get("source_url", source.url_or_handle),
                    raw_metadata=post_data.get("raw_metadata", {}),
                    tags=post_data.get("tags", []),
                    published_at=post_data.get("published_at", datetime.now(timezone.utc)),
                    scraped_at=datetime.now(timezone.utc),
                    is_flagged=False,
                    media_status="pending",
                )

                db.add(new_post)
                new_posts.append(new_post)
                saved_count += 1

            except Exception as e:
                logger.warning(f"⚠️  Error saving post: {str(e)}")
                continue

        # Commit all new posts
        if saved_count > 0:
            try:
                db.commit()
                logger.info(f"💾 Saved {saved_count} new posts to database")
                # OCR/audio-transcript extraction runs as a per-post background task so
                # it never blocks the scraping cycle or HTTP workers.
                for post in new_posts:
                    if post.media_urls or post.post_url or post.source_url:
                        schedule_media_processing(post.id)
            except Exception as e:
                logger.error(f"❌ Error committing posts to database: {str(e)}")
                db.rollback()
                saved_count = 0

        return saved_count
