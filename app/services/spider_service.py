"""Dynamic asynchronous web spider for topic discovery and threat intelligence collection.

Implements a lightweight Crawl4AI-style async crawler (httpx-based) with runtime-configurable
keyword matrices, Arabic-aware relevance scoring, and a direct hand-off into the existing
Phase 1 (relevance filtering) / Phase 2 (local Ollama LLM analysis) pipeline.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone
from hashlib import md5
from html import unescape
from typing import Any
from urllib.parse import urljoin

import feedparser
import httpx
from sqlalchemy.orm import Session

from config import settings
from app.db.session import SessionLocal
from app.models.post import Post
from app.models.source import MonitoredSource
from app.services.ai_service import analyze_post_content

logger = logging.getLogger(__name__)

_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_LINK_RE = re.compile(r'href=["\']([^"\'#]+)["\']', re.IGNORECASE)
_CVE_RE = re.compile(r"CVE-\d{4}-\d{4,7}", re.IGNORECASE)

# Common Arabic definite-article prefixes and inflection suffixes tolerated around a keyword.
_ARABIC_PREFIXES = ("وبال", "فبال", "وال", "بال", "كال", "فال", "ال")
_ARABIC_SUFFIXES = ("ات", "ون", "ين", "ية", "ها", "هم", "كم", "نا", "ة", "ه")

MAX_PAGES_PER_RUN = 60
MAX_LINKS_PER_PAGE = 20
CONCURRENCY = 5
REQUEST_TIMEOUT = 15.0
# A browser-like UA keeps the crawler working against sites that block bare bot UAs.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36 SignalDeskSpider/1.0"
)
PASS_INTERVAL_SECONDS = 20
# Google News RSS needs no API key/JS and is far less bot-blocked than scraping search HTML directly.
NEWS_SEARCH_URL = "https://news.google.com/rss/search"
MAX_DISCOVERY_QUERIES = 5
MAX_RESULTS_PER_QUERY = 8


def _build_keyword_pattern(keywords: list[str]) -> re.Pattern | None:
    """Combine keywords into one regex, tolerating Arabic prefixes/suffixes."""
    parts: list[str] = []
    for word in keywords:
        word = (word or "").strip()
        if not word:
            continue
        escaped = re.escape(word)
        if re.search(r"[\u0600-\u06FF]", word):
            prefix = "|".join(re.escape(p) for p in _ARABIC_PREFIXES)
            suffix = "|".join(re.escape(s) for s in _ARABIC_SUFFIXES)
            parts.append(f"(?:{prefix})?{escaped}(?:{suffix})?")
        else:
            parts.append(rf"\b{escaped}\b")
    if not parts:
        return None
    return re.compile("|".join(parts), re.IGNORECASE)


def _extract_text(html: str) -> tuple[str, str]:
    """Return (title, plain_text) extracted from raw HTML without extra parser deps."""
    title_match = _TITLE_RE.search(html)
    title = unescape(_HTML_TAG_RE.sub("", title_match.group(1))).strip() if title_match else ""
    cleaned = _SCRIPT_STYLE_RE.sub(" ", html)
    text = unescape(_HTML_TAG_RE.sub(" ", cleaned))
    text = re.sub(r"\s+", " ", text).strip()
    return title, text


def _extract_links(html: str, base_url: str) -> list[str]:
    links: list[str] = []
    for match in _LINK_RE.finditer(html):
        href = match.group(1).strip()
        if href.startswith(("mailto:", "javascript:", "tel:")):
            continue
        try:
            links.append(urljoin(base_url, href))
        except ValueError:
            continue
    return links


def _relevance_score(text: str, pattern: re.Pattern | None) -> float:
    """Score 0-100 based on unique keyword hits and their density in the text."""
    if pattern is None or not text:
        return 0.0
    matches = pattern.findall(text)
    if not matches:
        return 0.0
    unique_hits = len({match.lower() for match in matches})
    density = len(matches) / max(len(text.split()), 1)
    return round(min(100.0, (unique_hits * 15) + (density * 1000)), 2)


def _extract_cves(text: str) -> list[str]:
    return sorted({cve.upper() for cve in _CVE_RE.findall(text)})


async def _discover_items(client: httpx.AsyncClient, keywords: list[str]) -> list[dict[str, str]]:
    """Search Google News RSS for each active keyword to find fresh, unspecified articles.

    The feed's own title/summary is used as the analyzed text instead of re-fetching the
    linked page, because Google's redirect links resolve to a JS interstitial rather than
    the publisher's HTML.
    """
    discovered: list[dict[str, str]] = []
    seen: set[str] = set()
    for keyword in keywords[:MAX_DISCOVERY_QUERIES]:
        try:
            response = await client.get(
                NEWS_SEARCH_URL, params={"q": keyword, "hl": "ar", "gl": "SA", "ceid": "SA:ar"}
            )
            response.raise_for_status()
        except Exception as exc:
            logger.warning("Spider discovery search failed for %r: %s", keyword, exc)
            continue
        feed = feedparser.parse(response.text)
        found_for_keyword = 0
        for entry in feed.entries:
            link = entry.get("link")
            if not link or link in seen:
                continue
            seen.add(link)
            title = unescape(_HTML_TAG_RE.sub(" ", entry.get("title", ""))).strip()
            summary = unescape(_HTML_TAG_RE.sub(" ", entry.get("summary", ""))).strip()
            discovered.append({"url": link, "title": title, "text": f"{title}. {summary}".strip()})
            found_for_keyword += 1
            if found_for_keyword >= MAX_RESULTS_PER_QUERY:
                break
    return discovered


class SpiderRun:
    """Mutable state for a single spider execution; keyword matrix may change mid-run."""

    def __init__(
        self,
        run_id: str,
        topic_id: int,
        search_topics: list[str],
        target_keywords: list[str],
        seed_urls: list[str],
        relevance_threshold: float,
        max_depth: int,
        proxy_enabled: bool,
    ) -> None:
        self.run_id = run_id
        self.topic_id = topic_id
        self.search_topics = list(search_topics)
        self.target_keywords = list(target_keywords)
        self.seed_urls = list(seed_urls)
        self.relevance_threshold = relevance_threshold
        self.max_depth = max_depth
        self.proxy_enabled = proxy_enabled
        self.keywords: set[str] = set()
        self.pattern: re.Pattern | None = None
        self.status = "queued"
        self.stop_requested = False
        self.pages_crawled = 0
        self.accepted = 0
        self.discarded = 0
        self.errors: list[dict[str, Any]] = []
        self.started_at = datetime.now(timezone.utc)
        self.finished_at: datetime | None = None
        self.lock = asyncio.Lock()

    def add_keywords(self, words: list[str]) -> None:
        for word in words:
            word = (word or "").strip()
            if word:
                self.keywords.add(word)
        self.pattern = _build_keyword_pattern(list(self.keywords))

    def to_status(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "topic_id": self.topic_id,
            "pages_crawled": self.pages_crawled,
            "accepted": self.accepted,
            "discarded": self.discarded,
            "active_keywords": sorted(self.keywords),
            "search_topics": self.search_topics,
            "target_keywords": self.target_keywords,
            "seed_urls": self.seed_urls,
            "relevance_threshold": self.relevance_threshold,
            "max_depth": self.max_depth,
            "proxy_enabled": self.proxy_enabled,
            "errors": self.errors[-10:],
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


class SpiderOrchestrator:
    """Coordinates dynamic asynchronous spider runs and their topic-injection updates."""

    def __init__(self) -> None:
        self.runs: dict[str, SpiderRun] = {}

    def create_run(
        self,
        topic_id: int,
        search_topics: list[str],
        target_keywords: list[str],
        seed_urls: list[str],
        relevance_threshold: float,
        max_depth: int,
        proxy_enabled: bool,
    ) -> SpiderRun:
        run_id = uuid.uuid4().hex[:12]
        run = SpiderRun(run_id, topic_id, search_topics, target_keywords, seed_urls, relevance_threshold, max_depth, proxy_enabled)
        run.add_keywords([*search_topics, *target_keywords])
        self.runs[run_id] = run
        return run

    def get_run(self, run_id: str) -> SpiderRun | None:
        return self.runs.get(run_id)

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        ordered = sorted(self.runs.values(), key=lambda run: run.started_at, reverse=True)
        return [run.to_status() for run in ordered[:limit]]

    def get_active_summary(self) -> dict[str, Any]:
        """Lightweight overall activity indicator, safe for any authenticated user."""
        running = [run for run in self.runs.values() if run.status == "running"]
        latest = max(self.runs.values(), key=lambda run: run.started_at, default=None)
        return {
            "is_running": bool(running),
            "active_runs": len(running),
            "total_runs": len(self.runs),
            "last_run_id": latest.run_id if latest else None,
            "last_status": latest.status if latest else None,
        }

    def request_stop(self, run_id: str) -> SpiderRun | None:
        """Signal a queued or running spider run to halt after its current page batch."""
        run = self.runs.get(run_id)
        if run is None:
            return None
        run.stop_requested = True
        if run.status == "queued":
            run.status = "stopped"
            run.finished_at = datetime.now(timezone.utc)
        return run

    async def add_topic(
        self, run_id: str, search_topics: list[str], target_keywords: list[str]
    ) -> SpiderRun | None:
        run = self.runs.get(run_id)
        if run is None:
            return None
        async with run.lock:
            run.search_topics.extend([word for word in search_topics if word.strip()])
            run.target_keywords.extend([word for word in target_keywords if word.strip()])
            run.add_keywords([*search_topics, *target_keywords])
        return run

    async def execute(self, run_id: str, seed_urls: list[str]) -> None:
        """Continuously re-crawl the seed set (breadth-first, up to ``max_depth`` per pass)
        until ``stop_requested`` is set, either via the stop endpoint or a stop button.
        """
        run = self.runs[run_id]
        run.status = "running"
        semaphore = asyncio.Semaphore(CONCURRENCY)

        client_kwargs: dict[str, Any] = {
            "timeout": REQUEST_TIMEOUT,
            "follow_redirects": True,
            "headers": {"User-Agent": USER_AGENT},
        }
        if run.proxy_enabled:
            proxy_url = getattr(settings, "spider_proxy_url", "")
            if proxy_url:
                client_kwargs["proxy"] = proxy_url
            else:
                logger.warning("Spider run %s requested proxy rotation but no proxy is configured", run_id)

        try:
            async with httpx.AsyncClient(**client_kwargs) as client:
                while not run.stop_requested:
                    if seed_urls:
                        seen: set[str] = set(seed_urls)
                        queue: list[tuple[str, int]] = [(url, 0) for url in seed_urls]
                        pages_this_pass = 0
                        while queue and not run.stop_requested and pages_this_pass < MAX_PAGES_PER_RUN:
                            batch, queue = queue[:CONCURRENCY], queue[CONCURRENCY:]
                            tasks = [
                                self._process_url(run, client, semaphore, url, depth, seen)
                                for url, depth in batch
                            ]
                            results = await asyncio.gather(*tasks, return_exceptions=True)
                            pages_this_pass += len(batch)
                            for result in results:
                                if isinstance(result, Exception):
                                    logger.exception("Spider task failed", exc_info=result)
                                    continue
                                for link, depth in result:
                                    if link not in seen:
                                        seen.add(link)
                                        queue.append((link, depth))
                    else:
                        # No fixed seeds: search the open web for the run's current keywords
                        # so it keeps discovering new, unspecified links every pass.
                        async with run.lock:
                            keywords_snapshot = sorted(run.keywords)
                            pattern_snapshot = run.pattern
                        items = await _discover_items(client, keywords_snapshot)
                        if not items:
                            run.errors.append({"url": None, "error": "No search results discovered for the active keywords"})
                        for item in items:
                            if run.stop_requested:
                                break
                            run.pages_crawled += 1
                            score = _relevance_score(item["text"], pattern_snapshot)
                            if score < run.relevance_threshold:
                                run.discarded += 1
                                continue
                            run.accepted += 1
                            await asyncio.to_thread(
                                self._save_and_analyze,
                                run.run_id,
                                run.topic_id,
                                item["url"],
                                item["title"],
                                item["text"],
                                score,
                                keywords_snapshot,
                            )
                    if run.stop_requested:
                        break
                    # Idle between passes, then re-crawl seeds or re-search keywords for fresh content.
                    for _ in range(PASS_INTERVAL_SECONDS):
                        if run.stop_requested:
                            break
                        await asyncio.sleep(1)
        except Exception:
            logger.exception("Spider run %s crashed", run_id)
            run.errors.append({"url": None, "error": "Internal crawl failure; run stopped"})
        finally:
            run.status = "stopped"
            run.finished_at = datetime.now(timezone.utc)

    async def _process_url(
        self,
        run: SpiderRun,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        url: str,
        depth: int,
        seen: set[str],
    ) -> list[tuple[str, int]]:
        async with semaphore:
            try:
                response = await client.get(url)
                response.raise_for_status()
                html = response.text
            except Exception as exc:
                run.errors.append({"url": url, "error": str(exc)})
                return []

        run.pages_crawled += 1
        title, text = _extract_text(html)
        async with run.lock:
            pattern = run.pattern
            keywords_snapshot = sorted(run.keywords)
        score = _relevance_score(f"{title} {text}", pattern)
        if score < run.relevance_threshold:
            run.discarded += 1
        else:
            run.accepted += 1
            await asyncio.to_thread(
                self._save_and_analyze, run.run_id, run.topic_id, url, title, text, score, keywords_snapshot
            )

        if depth >= run.max_depth:
            return []
        return [(link, depth + 1) for link in _extract_links(html, url)[:MAX_LINKS_PER_PAGE]]

    @staticmethod
    def _save_and_analyze(
        run_id: str,
        topic_id: int,
        url: str,
        title: str,
        text: str,
        score: float,
        matched_keywords: list[str],
    ) -> None:
        """Phase 1 acceptance -> persist -> Phase 2 LLM analysis, on a dedicated DB session."""
        db = SessionLocal()
        try:
            fingerprint = md5(url.encode("utf-8")).hexdigest()
            already_saved = (
                db.query(Post)
                .filter(Post.topic_id == topic_id, Post.content_fingerprint == fingerprint)
                .first()
            )
            if already_saved is not None:
                return

            source = SpiderOrchestrator._get_or_create_spider_source(db, topic_id)
            post = Post(
                topic_id=topic_id,
                source_id=source.id,
                external_id=fingerprint,
                platform="spider",
                author="spider",
                content=text[:20000],
                title=title[:1000] if title else None,
                post_url=url,
                source_url=url,
                raw_metadata={"source_type": "SPIDER", "relevance_score": score, "run_id": run_id},
                published_at=datetime.now(timezone.utc),
                scraped_at=datetime.now(timezone.utc),
                content_fingerprint=fingerprint,
                entities={"cves": _extract_cves(text), "matched_keywords": matched_keywords},
            )
            db.add(post)
            db.flush()

            analysis = analyze_post_content(text)
            if analysis.get("success"):
                post.violence_category = analysis["violence_category"]
                post.severity_level = analysis["severity_level"]
                post.ai_summary = analysis["ai_summary"]
                post.raw_ai_response = analysis["raw_response"]
                post.is_flagged = analysis["is_flagged"]
            db.commit()
        except Exception:
            logger.exception("Failed to persist spider result for %s", url)
            db.rollback()
        finally:
            db.close()

    @staticmethod
    def _get_or_create_spider_source(db: Session, topic_id: int) -> MonitoredSource:
        source = (
            db.query(MonitoredSource)
            .filter(MonitoredSource.url_or_handle == "internal://spider")
            .first()
        )
        if source is None:
            source = MonitoredSource(
                platform="spider",
                name="Dynamic Spider",
                url_or_handle="internal://spider",
                target_type="crawler",
                status="active",
                is_active=True,
                approval_status="approved",
            )
            db.add(source)
            db.flush()
        return source


spider_orchestrator = SpiderOrchestrator()
