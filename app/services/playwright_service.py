"""
Playwright Web Scraping Service.
Async scraper for loading and extracting content from web pages.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
import re

logger = logging.getLogger(__name__)


class PlaywrightService:
    """
    Service for scraping web pages using Playwright.
    
    Provides async methods for loading pages, extracting text and media,
    and handling JavaScript-rendered content.
    """

    def __init__(self):
        """Initialize Playwright service."""
        self.browser = None
        self.context = None

    async def initialize(self):
        """
        Initialize browser and context.
        Must be called before using any scraping methods.
        
        Raises:
            ImportError: If playwright is not installed.
        """
        try:
            from playwright.async_api import async_playwright

            self.async_playwright = async_playwright

            # Start browser
            self.playwright_instance = await self.async_playwright().start()
            self.browser = await self.playwright_instance.chromium.launch(headless=True)
            self.context = await self.browser.new_context()

            logger.info("✅ Playwright browser initialized")

        except ImportError:
            logger.error("❌ Playwright not installed. Run: pip install playwright && playwright install")
            raise
        except Exception as e:
            logger.error(f"❌ Failed to initialize Playwright: {str(e)}")
            raise

    async def close(self):
        """Close browser and context."""
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if hasattr(self, "playwright_instance"):
                await self.playwright_instance.stop()

            logger.info("✅ Playwright browser closed")

        except Exception as e:
            logger.error(f"⚠️  Error closing Playwright: {str(e)}")

    async def scrape_page(
        self,
        url: str,
        wait_selector: Optional[str] = None,
        timeout: int = 30000,
    ) -> Dict[str, Any]:
        """
        Scrape a web page and extract content.

        Args:
            url (str): URL to scrape.
            wait_selector (Optional[str]): CSS selector to wait for before extracting.
            timeout (int): Timeout in milliseconds.

        Returns:
            Dict containing:
                - 'success': bool
                - 'error': str - Error message if failed
                - 'title': str - Page title
                - 'content': str - Extracted text content
                - 'media_urls': List[str] - Found image and media URLs
                - 'metadata': Dict - Additional page info
        """
        if not self.browser or not self.context:
            return {
                "success": False,
                "error": "Playwright not initialized",
                "title": "",
                "content": "",
                "media_urls": [],
                "metadata": {},
            }

        page = None
        try:
            logger.info(f"🔄 Scraping page: {url}")

            page = await self.context.new_page()

            # Navigate to page
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout)

            # Wait for specific selector if provided
            if wait_selector:
                try:
                    await page.wait_for_selector(wait_selector, timeout=timeout)
                except Exception as e:
                    logger.warning(f"⚠️  Selector '{wait_selector}' not found: {str(e)}")

            # Extract content
            title = await page.title()
            text_content = await page.evaluate("document.body.innerText")
            html_content = await page.content()

            # Extract media URLs
            media_urls = await self._extract_media_urls(page, url)

            logger.info(f"✅ Scraped page: {url} ({len(text_content)} chars)")

            return {
                "success": True,
                "error": None,
                "title": title,
                "content": text_content[:5000],
                "media_urls": media_urls,
                "metadata": {
                    "url": url,
                    "status_code": page.url,
                    "html_length": len(html_content),
                },
            }

        except Exception as e:
            logger.error(f"❌ Error scraping {url}: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "title": "",
                "content": "",
                "media_urls": [],
                "metadata": {"url": url},
            }

        finally:
            if page:
                await page.close()

    async def scrape_social_page(
        self,
        url: str,
        platform: str,
    ) -> Dict[str, Any]:
        """
        Scrape a social media page and extract posts.

        Args:
            url (str): URL to social media page.
            platform (str): Platform name (facebook, x, instagram, etc).

        Returns:
            Dict with extracted posts and metadata.
        """
        if not self.browser or not self.context:
            return {
                "success": False,
                "error": "Playwright not initialized",
                "posts": [],
                "platform": platform,
            }

        page = None
        try:
            logger.info(f"🔄 Scraping {platform} page: {url}")

            page = await self.context.new_page()

            # Navigate with longer timeout for social pages
            await page.goto(url, wait_until="networkidle", timeout=60000)

            # Wait for content to load
            await page.wait_for_timeout(3000)

            # Extract posts based on platform
            posts = await self._extract_posts_by_platform(page, platform, url)

            logger.info(f"✅ Found {len(posts)} posts on {platform}")

            return {
                "success": True,
                "error": None,
                "posts": posts,
                "platform": platform,
                "url": url,
            }

        except Exception as e:
            logger.error(f"❌ Error scraping {platform} page {url}: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "posts": [],
                "platform": platform,
            }

        finally:
            if page:
                await page.close()

    async def _extract_media_urls(self, page: Any, base_url: str) -> List[str]:
        """
        Extract image and video URLs from page.

        Args:
            page: Playwright page object.
            base_url (str): Base URL for resolving relative links.

        Returns:
            List of media URLs.
        """
        try:
            # Get all image sources
            images = await page.evaluate(
                """() => {
                    return Array.from(document.querySelectorAll('img'))
                        .map(img => img.src)
                        .filter(src => src && src.length > 0);
                }"""
            )

            # Get video sources
            videos = await page.evaluate(
                """() => {
                    return Array.from(document.querySelectorAll('video source, [data-video]'))
                        .map(el => el.src || el.getAttribute('data-video'))
                        .filter(src => src && src.length > 0);
                }"""
            )

            # Combine and resolve relative URLs
            media = list(set(images + videos))
            media_urls = [urljoin(base_url, url) for url in media]

            return media_urls[:10]  # Limit to 10 media items

        except Exception as e:
            logger.debug(f"⚠️  Error extracting media URLs: {str(e)}")
            return []

    async def _extract_posts_by_platform(
        self,
        page: Any,
        platform: str,
        url: str,
    ) -> List[Dict[str, Any]]:
        """
        Extract posts from social media page using platform-specific selectors.

        Args:
            page: Playwright page object.
            platform (str): Platform name.
            url (str): Page URL.

        Returns:
            List of extracted posts.
        """
        posts = []

        try:
            # Platform-specific selectors (simplified)
            selectors = {
                "facebook": {
                    "post": "[data-testid='post']",
                    "content": "[data-testid='post_message']",
                    "author": "[data-testid='post_author']",
                },
                "x": {
                    "post": "[data-testid='Tweet']",
                    "content": "[data-testid='tweetText']",
                    "author": "[data-testid='User-Name']",
                },
                "instagram": {
                    "post": "article [role='button']",
                    "content": "span",
                    "author": "a[title]",
                },
            }

            if platform not in selectors:
                logger.warning(f"⚠️  Platform '{platform}' not specifically handled")
                return posts

            # Extract posts using selectors
            posts_data = await page.evaluate(
                """(selectors) => {
                    const posts = [];
                    const postElements = document.querySelectorAll(selectors.post);
                    
                    postElements.forEach((post, idx) => {
                        const content = post.querySelector(selectors.content)?.innerText || '';
                        const author = post.querySelector(selectors.author)?.innerText || 'Unknown';
                        
                        if (content.length > 0) {
                            posts.push({
                                external_id: `${Date.now()}_${idx}`,
                                author: author.split('\\n')[0],
                                content: content.substring(0, 1000),
                            });
                        }
                    });
                    
                    return posts;
                }""",
                selectors[platform],
            )

            # Format into Post objects
            for post_data in posts_data[:10]:  # Limit to 10 posts
                posts.append({
                    "external_id": post_data.get("external_id", ""),
                    "platform": platform,
                    "author": post_data.get("author", "Unknown"),
                    "content": post_data.get("content", ""),
                    "post_url": url,
                    "published_at": datetime.now(timezone.utc),
                    "media_urls": [],
                })

        except Exception as e:
            logger.debug(f"⚠️  Error extracting posts from {platform}: {str(e)}")

        return posts
