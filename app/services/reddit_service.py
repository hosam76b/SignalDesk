"""
Reddit Scraping Service.
Searches subreddits and keywords for posts matching monitoring criteria.
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

try:
    import praw
    from praw.models import Submission
except ImportError:  # pragma: no cover - optional deployment dependency
    praw = None
    Submission = Any
from config import settings

logger = logging.getLogger(__name__)


class RedditService:
    """
    Service for scraping Reddit posts.
    
    Uses PRAW (Python Reddit API Wrapper) to search subreddits and retrieve posts.
    Credentials configured via environment variables.
    """

    def __init__(self):
        """
        Initialize Reddit API client.
        
        Requires credentials in environment:
        - REDDIT_CLIENT_ID
        - REDDIT_CLIENT_SECRET
        - REDDIT_USER_AGENT
        """
        try:
            if not all([settings.reddit_client_id, settings.reddit_client_secret]):
                logger.warning("⚠️  Reddit API credentials not configured")
                self.reddit = None
                return

            if praw is None:
                logger.warning("⚠️  PRAW is not installed")
                self.reddit = None
                return

            self.reddit = praw.Reddit(
                client_id=settings.reddit_client_id,
                client_secret=settings.reddit_client_secret,
                user_agent=settings.reddit_user_agent,
            )

            # Test connection
            self.reddit.user.me()
            logger.info("✅ Reddit API connection successful")

        except Exception as e:
            logger.error(f"❌ Failed to initialize Reddit API: {str(e)}")
            self.reddit = None

    def search_subreddit(
        self,
        subreddit_name: str,
        keywords: List[str],
        time_filter: str = "day",
        limit: int = 25,
    ) -> Dict[str, Any]:
        """
        Search a subreddit for posts containing keywords.

        Args:
            subreddit_name (str): Subreddit name (without r/).
            keywords (List[str]): List of keywords to search for.
            time_filter (str): Time filter - 'day', 'week', 'month', 'year', 'all'.
            limit (int): Maximum number of posts to retrieve per keyword.

        Returns:
            Dict containing:
                - 'success': bool - Whether search succeeded
                - 'error': str - Error message if failed
                - 'posts': List[Dict] - Normalized post data
                - 'subreddit': str - Subreddit name
                - 'total_posts': int - Number of posts found
        """
        if not self.reddit:
            return {
                "success": False,
                "error": "Reddit API not initialized",
                "posts": [],
                "subreddit": subreddit_name,
                "total_posts": 0,
            }

        try:
            logger.info(f"🔄 Searching r/{subreddit_name} for keywords: {keywords}")

            subreddit = self.reddit.subreddit(subreddit_name)
            all_posts = []
            seen_ids = set()

            # Search for each keyword
            for keyword in keywords:
                try:
                    submissions = subreddit.search(
                        keyword,
                        time_filter=time_filter,
                        limit=limit,
                        sort="new",
                    )

                    for submission in submissions:
                        # Avoid duplicates
                        if submission.id in seen_ids:
                            continue

                        seen_ids.add(submission.id)
                        post = self._format_submission(submission, subreddit_name)
                        all_posts.append(post)

                except Exception as e:
                    logger.warning(f"⚠️  Error searching for keyword '{keyword}': {str(e)}")
                    continue

            logger.info(f"✅ Found {len(all_posts)} posts in r/{subreddit_name}")

            return {
                "success": True,
                "error": None,
                "posts": all_posts,
                "subreddit": subreddit_name,
                "total_posts": len(all_posts),
            }

        except Exception as e:
            logger.error(f"❌ Error searching subreddit r/{subreddit_name}: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "posts": [],
                "subreddit": subreddit_name,
                "total_posts": 0,
            }

    def get_hot_posts(
        self,
        subreddit_name: str,
        limit: int = 25,
    ) -> Dict[str, Any]:
        """
        Get hot posts from a subreddit.

        Args:
            subreddit_name (str): Subreddit name (without r/).
            limit (int): Maximum number of posts to retrieve.

        Returns:
            Dict with post data and metadata.
        """
        if not self.reddit:
            return {
                "success": False,
                "error": "Reddit API not initialized",
                "posts": [],
                "subreddit": subreddit_name,
                "total_posts": 0,
            }

        try:
            logger.info(f"🔄 Fetching hot posts from r/{subreddit_name}")

            subreddit = self.reddit.subreddit(subreddit_name)
            posts = []

            for submission in subreddit.hot(limit=limit):
                post = self._format_submission(submission, subreddit_name)
                posts.append(post)

            logger.info(f"✅ Retrieved {len(posts)} hot posts from r/{subreddit_name}")

            return {
                "success": True,
                "error": None,
                "posts": posts,
                "subreddit": subreddit_name,
                "total_posts": len(posts),
            }

        except Exception as e:
            logger.error(f"❌ Error fetching hot posts from r/{subreddit_name}: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "posts": [],
                "subreddit": subreddit_name,
                "total_posts": 0,
            }

    def _format_submission(self, submission: Submission, subreddit_name: str) -> Dict[str, Any]:
        """
        Format a Reddit submission into normalized post format.

        Args:
            submission (Submission): PRAW Submission object.
            subreddit_name (str): Name of subreddit.

        Returns:
            Normalized post dictionary.
        """
        # Extract media URLs
        media_urls = []
        if submission.is_video:
            media_urls.append(submission.media["reddit_video"]["fallback_url"])
        elif hasattr(submission, "preview"):
            for image in submission.preview.get("images", []):
                if "source" in image:
                    media_urls.append(image["source"]["url"])

        # Combine title and selftext for content
        content = f"{submission.title}\n\n{submission.selftext}"

        return {
            "external_id": submission.id,
            "platform": "reddit",
            "author": submission.author.name if submission.author else "[deleted]",
            "title": submission.title,
            "content": content[:5000],
            "post_url": f"https://reddit.com{submission.permalink}",
            "published_at": datetime.fromtimestamp(submission.created_utc, timezone.utc),
            "media_urls": media_urls,
            "metadata": {
                "subreddit": subreddit_name,
                "score": submission.score,
                "num_comments": submission.num_comments,
                "upvote_ratio": submission.upvote_ratio,
            },
        }
