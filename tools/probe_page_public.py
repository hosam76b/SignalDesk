"""Check whether a Facebook page is publicly readable without a login."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

PROBES = [
    ("login wall", "login"),
    ("Log in", "Log in"),
    ("checkpoint", "checkpoint"),
    ("content meta", 'content="'),
    ("og:title", "og:title"),
    ("page slug", "NSD"),
    ("posts permalink", "/posts/"),
]


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else "https://www.facebook.com/NSD.Tripoli"
    try:
        response = httpx.get(target, headers=HEADERS, timeout=30, follow_redirects=True)
    except httpx.HTTPError as exc:
        print(f"request failed: {exc}")
        return

    body = response.text
    print(f"target      : {target}")
    print(f"status      : {response.status_code}")
    print(f"final url   : {str(response.url)[:140]}")
    print(f"body length : {len(body)}")
    print()
    for label, needle in PROBES:
        print(f"  {label:18} {'FOUND' if needle in body else 'absent'}")
    print()

    lower = body.lower()
    if "login" in lower or "checkpoint" in lower:
        print("VERDICT: Facebook served a login wall / checkpoint.")
        print("This page is NOT publicly scrapable without an authenticated session.")
    elif len(body) > 50_000:
        print("VERDICT: page returned real public HTML.")
    else:
        print("VERDICT: thin response; likely blocked or redirected.")


if __name__ == "__main__":
    main()
