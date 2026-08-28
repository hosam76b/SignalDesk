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
from app.services.media_extraction_service import media_extractor

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

            if topic_id is None:
                topics = db.query(Topic).order_by(Topic.id).all()
                for topic in topics:
                    topic_stats = await self._run_topic_cycle(db, topic)
                    for key in ("total_sources", "total_posts_found", "new_posts_saved"):
                        stats[key] += topic_stats[key]
                    stats["errors"].extend(topic_stats["errors"])
                    for platform, platform_stats in topic_stats["sources_processed"].items():
                        current = stats["sources_processed"].setdefault(platform, {"sources": 0, "posts_found": 0, "posts_saved": 0})
                        for key in current:
                            current[key] += platform_stats[key]
                return stats

            topic = db.query(Topic).filter(Topic.id == topic_id).first()
            if topic is None:
                stats["success"] = False
                stats["errors"].append(f"Topic {topic_id} not found")
                return stats

            return await self._run_topic_cycle(db, topic)

        except Exception as e:
            error_msg = f"Fatal error in scraping cycle: {str(e)}"
            logger.error(f"❌ {error_msg}")
            stats["success"] = False
            stats["errors"].append(error_msg)

        finally:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            stats["duration_seconds"] = duration

        return stats

    async def _run_topic_cycle(self, db: Session, topic: Topic) -> Dict[str, Any]:
        """Run ingestion using only active sources and keywords for one topic."""
        stats = {
            "success": True,
            "total_sources": 0,
            "total_posts_found": 0,
            "new_posts_saved": 0,
            "errors": [],
            "sources_processed": {},
        }
        sources = db.query(MonitoredSource).filter(
            MonitoredSource.topic_id == topic.id,
            MonitoredSource.is_active == True,
        ).all()
        keywords = db.query(Keyword).filter(
            Keyword.topic_id == topic.id,
            Keyword.is_active == True,
        ).all()

        if not sources:
            stats["errors"].append(f"No active monitored sources for topic {topic.id}")
            return stats

        keyword_list = [kw.word_or_phrase for kw in keywords]
        stats["total_sources"] = len(sources)

        logger.info(f"📊 Processing topic {topic.id}: {len(sources)} sources with {len(keywords)} keywords")

        for source in sources:
            try:
                source.status = "pending"
                source.last_error = None
                source.last_error_at = None
                db.commit()
                logger.info(f"🔄 Processing source: {source.name} ({source.platform})")
                posts = await self._scrape_source(source, keyword_list)
                
                # Multimodal enrichment (Audio transcription & Image OCR)
                enriched_posts: list[dict[str, Any]] = []
                for p in posts:
                    try:
                        enriched_posts.append(await media_extractor.enrich_post_multimodal(p))
                    except Exception as exc:
                        logger.debug("Media enrichment skipped for post: %s", exc)
                        enriched_posts.append(p)
                posts = enriched_posts

                if keyword_list:
                    posts = [post for post in posts if self._matches_keywords(post, keyword_list)]

                if not posts:
                    logger.warning(f"⚠️  No posts found for {source.name}")
                    source.last_scraped_at = datetime.now(timezone.utc)
                    source.status = "active"
                    db.add(source)
                    db.commit()
                    continue

                stats["total_posts_found"] += len(posts)

                saved_count = self._save_posts(db, source, posts, topic.id)
                stats["new_posts_saved"] += saved_count

                if saved_count > 0:
                    webhook_result = await dispatch_post_ingested({
                        "event": "post_ingested",
                        "topic_id": topic.id,
                        "topic_title": topic.title,
                        "topic_description": topic.description,
                        "ai_prompt": self._build_contextual_prompt(topic, posts),
                        "source_id": source.id,
                        "source_name": source.name,
                        "platform": source.platform,
                        "posts": posts,
                        "ingested_at": datetime.now(timezone.utc).isoformat(),
                    })
                    if not webhook_result.get("delivered") and webhook_result.get("error") != "Webhook URL is not configured":
                        stats["errors"].append(webhook_result["error"])

                source.last_scraped_at = datetime.now(timezone.utc)
                source.status = "active"
                db.add(source)
                db.commit()

                if source.platform not in stats["sources_processed"]:
                    stats["sources_processed"][source.platform] = {
                        "sources": 0,
                        "posts_found": 0,
                        "posts_saved": 0,
                    }

                stats["sources_processed"][source.platform]["sources"] += 1
                stats["sources_processed"][source.platform]["posts_found"] += len(posts)
                stats["sources_processed"][source.platform]["posts_saved"] += saved_count

                logger.info(
                    f"✅ {source.name}: Found {len(posts)} posts, "
                    f"saved {saved_count} new posts"
                )

            except Exception as e:
                source.status = "failed"
                source.last_error = str(e)[:1000]
                source.last_error_at = datetime.now(timezone.utc)
                db.add(source)
                db.commit()
                error_msg = f"Error processing {source.name}: {str(e)}"
                logger.error(f"❌ {error_msg}")
                stats["errors"].append(error_msg)
                continue

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

        for post_data in posts:
            try:
                # Check for duplicates
                external_id = post_data.get("external_id", "")
                post_url = post_data.get("post_url", "")
                content = post_data.get("content", "")[:5000]
                fingerprint = md5(
                    f"{content}|{post_data.get('author', 'Unknown')}|{post_url}".encode("utf-8")
                ).hexdigest()

                if external_id or post_url or fingerprint:
                    existing = db.query(Post).filter(
                        Post.source_id == source.id,
                        ((Post.external_id == external_id) | (Post.post_url == post_url) | (Post.content_fingerprint == fingerprint)),
                    ).first()

                    if existing:
                        logger.debug(f"Skipping duplicate post: {external_id}")
                        continue

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
                )

                db.add(new_post)
                saved_count += 1

            except Exception as e:
                logger.warning(f"⚠️  Error saving post: {str(e)}")
                continue

        # Commit all new posts
        if saved_count > 0:
            try:
                db.commit()
                logger.info(f"💾 Saved {saved_count} new posts to database")
            except Exception as e:
                logger.error(f"❌ Error committing posts to database: {str(e)}")
                db.rollback()
                saved_count = 0

        return saved_count
