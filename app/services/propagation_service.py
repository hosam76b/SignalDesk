"""Network propagation graph service for tracking content spread and Coordinated Inauthentic Behavior (CIB)."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from sqlalchemy.orm import Session

from app.models.post import Post
from app.models.source import MonitoredSource
from app.models.topic import Topic

logger = logging.getLogger(__name__)


def compute_content_key(post: Post) -> str:
    """Generate a stable clustering key from fingerprint or normalized text."""
    if post.content_fingerprint:
        return f"fp:{post.content_fingerprint}"
    cleaned = " ".join((post.content or "").strip().lower().split())
    if len(cleaned) < 20:
        return f"post:{post.id}"
    return f"hash:{sha256(cleaned[:250].encode('utf-8')).hexdigest()[:24]}"


def format_delay(seconds: float) -> str:
    """Format delay in seconds into human-readable representation."""
    if seconds < 60:
        return f"+{int(seconds)}s"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"+{minutes}m"
    hours = int(minutes // 60)
    remaining_mins = minutes % 60
    if hours < 24:
        return f"+{hours}h {remaining_mins}m" if remaining_mins else f"+{hours}h"
    days = int(hours // 24)
    return f"+{days}d"


def analyze_topic_propagation_graph(
    db: Session,
    topic_id: int,
    cib_window_minutes: int = 60,
) -> dict[str, Any]:
    """
    Construct a propagation graph of posts belonging to a topic.
    Identifies Patient Zero nodes and secondary amplifiers sharing identical/hashed content.
    """
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if topic is None:
        return {
            "success": False,
            "error": f"Topic {topic_id} not found",
            "nodes": [],
            "edges": [],
            "summary": {},
        }

    posts = (
        db.query(Post)
        .filter(Post.topic_id == topic_id)
        .order_by(Post.published_at.asc(), Post.id.asc())
        .all()
    )

    if not posts:
        return {
            "success": True,
            "topic_id": topic_id,
            "topic_title": topic.title,
            "nodes": [],
            "edges": [],
            "summary": {
                "total_nodes": 0,
                "total_edges": 0,
                "total_clusters": 0,
                "cib_clusters_count": 0,
                "top_amplifiers": [],
            },
        }

    # Group posts by cluster key
    clusters: dict[str, list[Post]] = defaultdict(list)
    for post in posts:
        key = compute_content_key(post)
        clusters[key].append(post)

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    cib_clusters_count = 0
    amplifier_counts: dict[str, int] = defaultdict(int)

    cluster_index = 0
    for key, cluster_posts in clusters.items():
        # Sort chronologically
        sorted_posts = sorted(
            cluster_posts,
            key=lambda p: p.published_at or datetime.fromtimestamp(0, tz=timezone.utc),
        )
        patient_zero = sorted_posts[0]
        is_multi_post = len(sorted_posts) > 1

        if is_multi_post:
            cluster_index += 1
            cluster_label = f"Cluster #{cluster_index}"
        else:
            cluster_label = "Single Post"

        # Check for CIB heuristic: distinct authors/sources within cib_window_minutes
        distinct_sources = {p.source_id for p in sorted_posts}
        distinct_authors = {p.author for p in sorted_posts if p.author}
        time_span_seconds = (
            (sorted_posts[-1].published_at - sorted_posts[0].published_at).total_seconds()
            if is_multi_post and sorted_posts[-1].published_at and sorted_posts[0].published_at
            else 0
        )
        is_cib = bool(
            is_multi_post
            and (len(distinct_sources) >= 3 or len(distinct_authors) >= 3)
            and time_span_seconds <= (cib_window_minutes * 60)
        )
        if is_cib:
            cib_clusters_count += 1

        # Build nodes
        for idx, post in enumerate(sorted_posts):
            is_pz = idx == 0 and is_multi_post
            delay_sec = (
                (post.published_at - patient_zero.published_at).total_seconds()
                if (post.published_at and patient_zero.published_at and idx > 0)
                else 0.0
            )

            if idx > 0:
                amplifier_counts[f"{post.platform}:{post.author}"] += 1

            nodes.append({
                "id": post.id,
                "label": post.author or f"Source {post.source_id}",
                "author": post.author,
                "platform": post.platform,
                "source_id": post.source_id,
                "title": post.title,
                "content_preview": (post.content or "")[:200],
                "post_url": post.post_url,
                "published_at": post.published_at.isoformat() if post.published_at else None,
                "is_patient_zero": is_pz,
                "is_amplifier": idx > 0,
                "severity_level": post.severity_level or "low",
                "is_dangerous": post.is_dangerous,
                "is_important": post.is_important,
                "sentiment": post.sentiment or "neutral",
                "cluster_key": key if is_multi_post else None,
                "cluster_label": cluster_label if is_multi_post else None,
                "is_cib": is_cib,
                "delay_from_origin": format_delay(delay_sec) if idx > 0 else "Origin",
                "delay_seconds": delay_sec,
            })

            # Build directed edges
            if idx > 0:
                # Link to previous spreader or patient zero
                parent_post = sorted_posts[idx - 1]
                edge_delay = (
                    (post.published_at - parent_post.published_at).total_seconds()
                    if (post.published_at and parent_post.published_at)
                    else delay_sec
                )
                edges.append({
                    "id": f"e_{parent_post.id}_{post.id}",
                    "source": parent_post.id,
                    "target": post.id,
                    "origin_id": patient_zero.id,
                    "delay_seconds": edge_delay,
                    "delay_formatted": format_delay(edge_delay),
                    "total_delay_formatted": format_delay(delay_sec),
                    "is_coordinated": is_cib,
                    "cluster_key": key,
                    "cluster_label": cluster_label,
                })

    top_amplifiers = [
        {"account": acc, "amplified_count": count}
        for acc, count in sorted(amplifier_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    ]

    return {
        "success": True,
        "topic_id": topic_id,
        "topic_title": topic.title,
        "nodes": nodes,
        "edges": edges,
        "summary": {
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "total_clusters": cluster_index,
            "cib_clusters_count": cib_clusters_count,
            "patient_zero_count": cluster_index,
            "top_amplifiers": top_amplifiers,
        },
    }

