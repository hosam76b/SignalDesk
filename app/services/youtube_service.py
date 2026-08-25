"""
YouTube Scraping Service.
Searches YouTube videos and retrieves transcripts when available.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from urllib.parse import urlparse, parse_qs
from config import settings

logger = logging.getLogger(__name__)


class YouTubeService:
    """
    Service for scraping YouTube videos and transcripts.
    
    Uses YouTube Data API to search for videos and youtube-transcript-api
    to retrieve transcripts when available.
    API key configured via environment variable.
    """

    def __init__(self):
        """
        Initialize YouTube API client.
        
        Requires YouTube API key in environment:
        - YOUTUBE_API_KEY
        """
        try:
            if not settings.youtube_api_key:
                logger.warning("⚠️  YouTube API key not configured")
                self.youtube = None
                return

            self.youtube = build("youtube", "v3", developerKey=settings.youtube_api_key)
            logger.info("✅ YouTube API connection successful")

        except Exception as e:
            logger.error(f"❌ Failed to initialize YouTube API: {str(e)}")
            self.youtube = None

    def search_videos(
        self,
        keyword: str,
        max_results: int = 25,
        order: str = "relevance",
        published_after: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Search YouTube for videos by keyword.

        Args:
            keyword (str): Search keyword/phrase.
            max_results (int): Maximum number of results (1-50).
            order (str): Result order - 'relevance', 'date', 'viewCount', 'rating'.
            published_after (Optional[str]): ISO 8601 date string (e.g. '2026-08-01T00:00:00Z').

        Returns:
            Dict containing:
                - 'success': bool - Whether search succeeded
                - 'error': str - Error message if failed
                - 'videos': List[Dict] - Video data with transcripts
                - 'total_results': int - Number of videos found
        """
        if not self.youtube:
            return {
                "success": False,
                "error": "YouTube API not initialized",
                "videos": [],
                "total_results": 0,
            }

        try:
            logger.info(f"🔄 Searching YouTube for: {keyword}")

            # Execute search
            search_response = self.youtube.search().list(
                q=keyword,
                part="snippet",
                maxResults=min(max_results, 50),
                order=order,
                type="video",
                publishedAfter=published_after,
            ).execute()

            videos = []

            for item in search_response.get("items", []):
                try:
                    video_id = item["id"]["videoId"]
                    video_data = self._format_video(item, video_id)
                    videos.append(video_data)

                except Exception as e:
                    logger.warning(f"⚠️  Error processing video {item.get('id', {}).get('videoId')}: {str(e)}")
                    continue

            logger.info(f"✅ Found {len(videos)} YouTube videos for '{keyword}'")

            return {
                "success": True,
                "error": None,
                "videos": videos,
                "total_results": len(videos),
            }

        except Exception as e:
            logger.error(f"❌ Error searching YouTube for '{keyword}': {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "videos": [],
                "total_results": 0,
            }

    def get_transcript(self, video_id: str) -> Dict[str, Any]:
        """
        Retrieve transcript for a YouTube video.

        Args:
            video_id (str): YouTube video ID.

        Returns:
            Dict containing:
                - 'success': bool
                - 'error': str - Error message if failed
                - 'transcript': str - Full transcript text or empty if unavailable
                - 'language': str - Transcript language
        """
        try:
            logger.info(f"🔄 Fetching transcript for video {video_id}")

            # Try to get transcript
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id)

            # Combine transcript entries
            transcript = " ".join([entry["text"] for entry in transcript_list])

            logger.info(f"✅ Retrieved transcript for video {video_id} ({len(transcript)} chars)")

            return {
                "success": True,
                "error": None,
                "transcript": transcript[:10000],  # Limit to 10k chars
                "language": "en",
            }

        except Exception as e:
            logger.debug(f"⚠️  Could not retrieve transcript for {video_id}: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "transcript": "",
                "language": None,
            }

    def _format_video(self, search_result: Dict[str, Any], video_id: str) -> Dict[str, Any]:
        """
        Format YouTube search result into standardized video format.

        Args:
            search_result (Dict): YouTube API search result item.
            video_id (str): YouTube video ID.

        Returns:
            Formatted video dictionary with transcript if available.
        """
        snippet = search_result.get("snippet", {})

        # Get transcript
        transcript_data = self.get_transcript(video_id)
        transcript = transcript_data.get("transcript", "")

        # Combine title and description with transcript for content
        content = f"{snippet.get('title', '')}\n\n{snippet.get('description', '')}"
        if transcript:
            content += f"\n\n[TRANSCRIPT]\n{transcript}"

        return {
            "external_id": video_id,
            "platform": "youtube",
            "author": snippet.get("channelTitle", "Unknown"),
            "title": snippet.get("title", "No Title"),
            "content": content[:5000],
            "post_url": f"https://www.youtube.com/watch?v={video_id}",
            "published_at": self._parse_date(snippet.get("publishedAt")),
            "media_urls": [f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"],
            "metadata": {
                "video_id": video_id,
                "channel_id": snippet.get("channelId", ""),
                "has_transcript": transcript_data.get("success", False),
                "transcript_language": transcript_data.get("language"),
            },
        }

    def _parse_date(self, date_string: Optional[str]) -> datetime:
        """
        Parse ISO 8601 date string from YouTube API.

        Args:
            date_string (Optional[str]): ISO 8601 datetime string.

        Returns:
            Parsed datetime or current time if parsing fails.
        """
        try:
            if not date_string:
                return datetime.now(timezone.utc)

            # Remove 'Z' and parse
            if date_string.endswith("Z"):
                date_string = date_string[:-1]

            return datetime.fromisoformat(date_string)

        except Exception as e:
            logger.warning(f"⚠️  Could not parse YouTube date '{date_string}': {str(e)}")
            return datetime.now(timezone.utc)
