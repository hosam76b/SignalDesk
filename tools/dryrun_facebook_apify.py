"""Dry-run probe: facebook.com/NSD.Tripoli through the Apify route.

Read-only against the database. Prints the resolved actor, the exact payload
that would be sent, and the normalized post count.

Usage (from the project root):
    .venv\Scripts\python.exe tools\dryrun_facebook_apify.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.apify_service import ApifyService  # noqa: E402
from app.services.scraper_service import ScraperService  # noqa: E402
from config import settings  # noqa: E402

TARGET = "https://www.facebook.com/NSD.Tripoli"
PLATFORM = "facebook"


def banner(title: str) -> None:
    print()
    print(f"=== {title} " + "=" * max(0, 58 - len(title)))


def main() -> int:
    banner("configuration")
    apify = ApifyService()
    print(f"target                : {TARGET}")
    print(f"platform              : {PLATFORM}")
    print(f"apify.is_configured   : {apify.is_configured}")
    print(f"apify_api_token       : {'set (len %d)' % len(settings.apify_api_token) if settings.apify_api_token else 'EMPTY'}")
    print(f"max_items_per_run     : {settings.apify_max_items_per_run}")
    print(f"meta.is_configured    : {MetaGraphState()}")

    actor_id = apify.resolve_actor_id(PLATFORM)
    print(f"resolved actor_id     : {actor_id!r}")
    print(f"service routing       : facebook -> {'apify (only route)' if apify.is_configured else 'native'}")
    if not actor_id:
        print()
        print("BLOCKED: no actor ID resolves for facebook.")
        print("Set one of:")
        print("  APIFY_FACEBOOK_ACTOR_ID=apify~STORE~owner~actor-name   (per platform)")
        print("  APIFY_ACTOR_ID=...                                       (generic default)")
        return 2

    banner("payload that will be sent")
    # The real builder, so the dry run cannot drift from production.
    payload = apify._build_payload(TARGET, None, PLATFORM)
    print(json.dumps(payload, indent=2))
    # The cap key depends on the actor's schema (maxItems officially,
    # resultsLimit on scraper_one actors, max_posts on some others).
    cap = next(
        (
            payload[key]
            for key in ("maxItems", "resultsLimit", "max_posts", "maxPosts")
            if key in payload
        ),
        None,
    )
    if cap != settings.apify_max_items_per_run:
        print(f"UNEXPECTED item cap: {cap}")
        return 3
    print(f"item cap             : {cap}")

    banner("live actor run")
    service = ScraperService()
    result = asyncio.run(
        service.scrape_source(PLATFORM, TARGET, apify_actor_id=actor_id)
    )

    print(f"success   : {result.get('success')}")
    print(f"method    : {result.get('method')}")
    print(f"error     : {result.get('error')}")

    posts = result.get("posts") or []
    print(f"post count: {len(posts)}")

    if posts:
        banner("first 3 normalized posts")
        for post in posts[:3]:
            print(json.dumps({
                "external_id": post.get("external_id"),
                "author": post.get("author"),
                "post_url": post.get("post_url"),
                "published_at": str(post.get("published_at")),
                "content": (post.get("content") or "")[:120],
            }, indent=2, ensure_ascii=False))
            print("-" * 40)

    banner("result")
    if posts:
        print(f"OK: {len(posts)} posts extracted, maxItems={settings.apify_max_items_per_run} honoured.")
        return 0
    print(f"FAILED: 0 posts. error={result.get('error')}")
    return 1


def MetaGraphState() -> str:  # noqa: N802
    from app.services.meta_service import MetaGraphService

    return str(MetaGraphService().is_configured)


if __name__ == "__main__":
    raise SystemExit(main())
