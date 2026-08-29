"""Database enum values used by the topic-centric schema."""

from enum import Enum


class UserRole(str, Enum):
    SUPER_ADMIN = "super_admin"
    TOPIC_MANAGER = "topic_manager"
    ANALYST = "analyst"
    OBSERVER = "observer"
    TOPIC_ADMIN = "topic_admin"
    TOPIC_MONITOR = "topic_monitor"


class TopicRole(str, Enum):
    TOPIC_MANAGER = "topic_manager"
    ANALYST = "analyst"
    OBSERVER = "observer"
    TOPIC_ADMIN = "topic_admin"
    TOPIC_MONITOR = "topic_monitor"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"