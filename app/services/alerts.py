"""Real-time alert evaluation and topic-scoped incident detection."""

from __future__ import annotations

import hashlib
import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.post import Post
from app.models.topic import Topic

logger = logging.getLogger(__name__)


class AlertManager:
    """Detect topic-level spikes, severity escalations, and coordinated behavior alerts."""

    @staticmethod
    def _hash_content(value: str | None) -> str:
        normalized = " ".join((value or "").strip().lower().split())
        if not normalized:
            return "empty"
        return hashlib.sha256(normalized[:500].encode("utf-8")).hexdigest()[:32]

    @staticmethod
    def evaluate_topic_alerts(db: Session, topic_id: int) -> dict[str, Any]:
        topic = db.query(Topic).filter(Topic.id == topic_id).first()
        if topic is None:
            return {
                "success": False,
                "topic_id": topic_id,
                "alerts": [],
                "summary": {"total_alerts": 0, "unread": 0, "acknowledged": 0, "resolved": 0},
                "error": f"Topic {topic_id} not found",
            }

        posts = (
            db.query(Post)
            .filter(Post.topic_id == topic_id)
            .order_by(Post.published_at.asc(), Post.id.asc())
            .all()
        )
        alerts: list[dict[str, Any]] = []

        hourly_counts: Counter[datetime] = Counter()
        for post in posts:
            if post.published_at is None:
                continue
            bucket = post.published_at.replace(minute=0, second=0, microsecond=0)
            hourly_counts[bucket] += 1

        sorted_hours = sorted(hourly_counts)
        for idx, hour in enumerate(sorted_hours):
            current = hourly_counts[hour]
            previous = hourly_counts.get(hour - timedelta(hours=1), 0)
            if previous and current > previous * 2:
                increase_pct = round(((current - previous) / previous) * 100, 1)
                alerts.append({
                    "id": f"volume-{hour.strftime('%Y%m%d%H')}",
                    "type": "volume_spike",
                    "severity": "high",
                    "status": "unread",
                    "title": "Volume Spike Alert",
                    "description": f"Post volume increased by {increase_pct}% over the last hour within topic {topic.title}.",
                    "topic_id": topic_id,
                    "created_at": hour.isoformat(),
                    "metadata": {"current_volume": current, "baseline_volume": previous, "window_hours": 1},
                })

        for post in posts:
            severity = (post.severity_level or "low").lower()
            if severity in {"high", "critical"} or post.is_flagged or post.is_dangerous:
                alerts.append({
                    "id": f"critical-{post.id}",
                    "type": "critical_content",
                    "severity": severity if severity in {"high", "critical"} else "high",
                    "status": "unread",
                    "title": "Critical Content Alert",
                    "description": f"High-risk post from {post.author} on {post.platform} requires analyst review.",
                    "topic_id": topic_id,
                    "created_at": (post.published_at or datetime.now(timezone.utc)).isoformat(),
                    "metadata": {"author": post.author, "platform": post.platform, "post_id": post.id, "severity": severity},
                })

        groups: defaultdict[str, list[Post]] = defaultdict(list)
        for post in posts:
            if post.content is None:
                continue
            groups[AlertManager._hash_content(post.content)].append(post)

        for content_key, cluster in groups.items():
            if len(cluster) < 5:
                continue
            within_window = sorted(cluster, key=lambda p: p.published_at or datetime.now(timezone.utc))
            if not within_window:
                continue
            earliest = within_window[0].published_at or datetime.now(timezone.utc)
            latest = within_window[-1].published_at or earliest
            if (latest - earliest) <= timedelta(minutes=10):
                authors = {item.author for item in within_window if item.author}
                if len(authors) >= 5:
                    alerts.append({
                        "id": f"cib-{content_key}",
                        "type": "cib_coordination",
                        "severity": "critical",
                        "status": "unread",
                        "title": "CIB Coordination Alert",
                        "description": f"{len(authors)} distinct accounts published nearly identical text within a 10-minute window.",
                        "topic_id": topic_id,
                        "created_at": latest.isoformat(),
                        "metadata": {"content_hash": content_key, "distinct_accounts": len(authors), "window_minutes": 10},
                    })

        deduped: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for alert in sorted(alerts, key=lambda item: item["created_at"], reverse=True):
            alert_id = alert["id"]
            if alert_id in seen_ids:
                continue
            seen_ids.add(alert_id)
            deduped.append(alert)

        summary = {
            "total_alerts": len(deduped),
            "unread": sum(1 for item in deduped if item["status"] == "unread"),
            "acknowledged": sum(1 for item in deduped if item["status"] == "acknowledged"),
            "resolved": sum(1 for item in deduped if item["status"] == "resolved"),
            "by_type": {alert_type: sum(1 for item in deduped if item["type"] == alert_type) for alert_type in {"volume_spike", "critical_content", "cib_coordination"}},
        }

        return {
            "success": True,
            "topic_id": topic_id,
            "topic_title": topic.title,
            "alerts": deduped,
            "summary": summary,
        }
