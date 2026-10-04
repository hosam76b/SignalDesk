"""Resolve the default build of an actor and dump its declared input schema."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402


def main() -> None:
    actor = sys.argv[1] if len(sys.argv) > 1 else "cleansyntax/facebook-posts-scraper"
    actor_id = actor.replace("/", "~")
    token = settings.apify_api_token
    base = f"https://api.apify.com/v2/acts/{actor_id}"

    with httpx.Client(timeout=45.0) as client:
        meta = client.get(base, params={"token": token}).json().get("data", {})
        tags = [t for t in (meta.get("taggedBuilds") or []) if isinstance(t, str)]
        print("actor          :", actor)
        print("build option   :", (meta.get("defaultRunOptions") or {}).get("build"))
        print("tags           :", tags[:8])

        versions = client.get(f"{base}/versions", params={"token": token})
        print("versions status:", versions.status_code)
        items = versions.json().get("data", {}).get("items", []) if versions.status_code == 200 else []
        print("version count  :", len(items))

        if items:
            latest = items[-1]
            print("latest version :", latest.get("versionNumber"))
            schema = client.get(
                f"{base}/versions/{latest.get('versionNumber')}/input-schema",
                params={"token": token},
            )
            print("schema status  :", schema.status_code)
            if schema.status_code == 200:
                props = schema.json().get("data", {}).get("properties", {})
                for key in sorted(props):
                    print(f"    {key:22} default={props[key].get('default')!r}")


if __name__ == "__main__":
    main()
