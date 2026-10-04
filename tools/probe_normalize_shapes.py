"""Check normalize_post identity and field extraction across actor item shapes."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.scraper_service import ScraperService as S  # noqa: E402


def main() -> None:
    src = "https://www.facebook.com/NSD.Tripoli"

    print("=== dedup identity across actor field-name variants ===")
    # Same logical post, as two different actors would report it, with the
    # text edited in between. A stable platform id must still dedup.
    a = {"post_id": "pfbid01", "url": f"{src}/posts/1", "text": "original", "author": {"name": "NSD"}}
    b = {"id": "pfbid01", "url": f"{src}/posts/1", "text": "EDITED", "author": {"name": "NSD"}}
    na = S.normalize_post(a, "facebook", src)
    nb = S.normalize_post(b, "facebook", src)
    print(f"  actor A external_id : {na['external_id']}")
    print(f"  actor B external_id : {nb['external_id']}")
    print(f"  dedup matches       : {na['external_id'] == nb['external_id']}")

    print()
    print("=== author shapes ===")
    shapes = [
        {"author": {"name": "NSD"}},
        {"author": "NSD"},
        {"owner": {"username": "nsd"}},
        {"pageName": "flat page"},
        {},
    ]
    for shape in shapes:
        out = S.normalize_post(shape, "facebook", src)
        print(f"  {str(shape):30} -> {out['author']}")

    print()
    print("=== media shapes ===")
    media_shapes = [
        {"photos": ["u1", "u2"]},
        {"media_urls": "single.jpg"},
        {"media": {"url": "obj.jpg"}},
        {"videos": ["v1"]},
        {"images": []},
        {},
    ]
    for shape in media_shapes:
        out = S.normalize_post(shape, "facebook", src)
        print(f"  {str(shape):30} -> {out['media_urls']}")

    print()
    print("=== text shapes ===")
    text_shapes = [
        {"text": "منشور بالعربية"},
        {"message": "رسالة"},
        {"caption": "تعليق"},
        {"description": "وصف"},
    ]
    for shape in text_shapes:
        out = S.normalize_post(shape, "facebook", src)
        print(f"  {str(shape):30} -> {out['content']!r}")

    print()
    print("=== no-id items still get a deterministic fallback ===")
    x1 = S.normalize_post({"url": f"{src}/posts/9", "text": "hi"}, "facebook", src)
    x2 = S.normalize_post({"url": f"{src}/posts/9", "text": "hi"}, "facebook", src)
    print(f"  {x1['external_id']}")
    print(f"  stable across calls  : {x1['external_id'] == x2['external_id']}")
    print(f"  length (sha256 hex)  : {len(x1['external_id'])}")


if __name__ == "__main__":
    main()
