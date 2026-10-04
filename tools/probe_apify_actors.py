"""Probe candidate Apify Facebook actors: build status and declared pricing."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402

CANDIDATES = [
    "apify/facebook-posts-scraper",
    "cleansyntax/facebook-posts-scraper",
    "cleansyntax/facebook-profile-posts-scraper",
    "curious_coder/facebook-post-scraper",
    "danek/facebook-posts-fast",
    "scraper_one/facebook-posts-scraper",
]


def main() -> None:
    token = settings.apify_api_token
    with httpx.Client(timeout=45.0) as client:
        for name in CANDIDATES:
            actor_id = name.replace("/", "~")
            url = f"https://api.apify.com/v2/acts/{actor_id}"
            try:
                meta = client.get(url, params={"token": token}).json().get("data", {})
                build = client.get(
                    f"{url}/builds/default", params={"token": token}
                ).json().get("data", {})
            except httpx.HTTPError as exc:
                print(f"{name:46} ERROR {exc}")
                continue

            pricing = meta.get("pricingInfos") or [{}]
            flat = next(
                (p for p in pricing if p.get("pricingModel") == "FLAT_PRICE_PER_MONTH"),
                None,
            )
            print(f"{name:46} build={build.get('status')}")
            print(f"    runs      : {meta.get('stats', {}).get('totalRuns')}")
            print(f"    flat price: {flat.get('pricePerUnitUsd') if flat else None} USD/month")
            print(f"    build used: {round(build.get('usageTotalUsd') or 0, 4)} USD")


if __name__ == "__main__":
    main()
