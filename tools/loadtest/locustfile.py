"""
SignalDesk load / stress / soak test suite (Locust).

Targets the three bottlenecks this audit found:
  1. read-path latency on the dashboard/feed (SQLite scan + N+1)
  2. the AI analysis batch, which currently blocks the event loop
  3. concurrent ingest writes (SQLite journal_mode=delete contention)

Install:  pip install locust
Run:      locust -f tools/loadtest/locustfile.py --host http://127.0.0.1:8000
Headless: locust -f tools/loadtest/locustfile.py --host http://127.0.0.1:8000 \
            --headless -u 50 -r 10 -t 10m --html loadtest.html

IMPORTANT: run the event-loop probe (EventLoopStallUser) in its own run.
It deliberately measures /health latency while an analysis batch executes.
"""

from __future__ import annotations

import os
import random
import time
from typing import Iterator

from locust import HttpUser, between, events, task, constant_passthrough

BASE = os.getenv("LOADTEST_BASE", "http://127.0.0.1:8000")
TOKEN = os.getenv("LOADTEST_TOKEN", "")
SEVERITIES = ["low", "medium", "high", "critical"]


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}


class ReadPathUser(HttpUser):
    """Dashboard / feed / posts traffic -- the p95 a human actually feels."""

    host = BASE
    wait_time = between(0.5, 2.0)

    @task(5)
    def dashboard(self):
        self.client.get("/api/dashboard/stats", headers=_auth_headers(),
                        name="GET /api/dashboard/stats")

    @task(4)
    def list_posts(self):
        page = random.randint(1, 40)
        self.client.get("/api/posts/", params={"page": page, "page_size": 50},
                        headers=_auth_headers(), name="GET /api/posts/ [paged]")

    @task(3)
    def flagged_posts(self):
        # Hits the un-indexed is_flagged / severity_level scan.
        sev = random.choice(SEVERITIES)
        self.client.get("/api/ai/flagged", params={"severity_level": sev, "limit": 50},
                        headers=_auth_headers(), name="GET /api/ai/flagged [unindexed]")

    @task(2)
    def analytics(self):
        self.client.get("/api/analytics/overview", headers=_auth_headers(),
                        name="GET /api/analytics/overview")

    @task(1)
    def health(self):
        # Control group: should stay fast unless the event loop is blocked.
        self.client.get("/health", name="GET /health")


class WritePathUser(HttpUser):
    """Concurrent ingest -- exposes SQLite write-lock contention."""

    host = BASE
    wait_time = between(1.0, 3.0)

    @task
    def quick_ingest(self):
        payload = {
            "topic_id": random.randint(1, 5),
            "url": f"https://example.com/article/{random.randint(1, 10**9)}",
            "backfill": random.choice([True, False]),
        }
        with self.client.post(
            "/api/ingestion/quick-url", json=payload,
            headers=_auth_headers(), name="POST /api/ingestion/quick-url",
            catch_response=True,
        ) as r:
            if r.status_code >= 500:
                r.failure(f"5xx: {r.text[:120]}")
            elif "locked" in r.text.lower():
                r.failure("SQLITE 'database is locked'")


class AnalysisBatchUser(HttpUser):
    """Kicks the AI analysis batch -- the #1 latency offender."""

    host = BASE
    wait_time = constant_passthrough(1)

    @task
    def analyze_pending(self):
        with self.client.post("/api/ai/analyze", json={"batch_size": 50},
                              headers=_auth_headers(), name="POST /api/ai/analyze",
                              catch_response=True, timeout=1800) as r:
            if r.elapsed.total_seconds() > 300:
                r.failure(f"batch exceeded 300s (took {r.elapsed.total_seconds():.0f}s)")


class EventLoopStallUser(HttpUser):
    """
    Control-group probe. Polls /health at a fixed 50ms cadence and records
    the worst gap. A healthy server keeps every sample well under 100ms.

    Run this ALONE (--headless -u 1 -t 5m) while driving AnalysisBatchUser
    from a second locust process. Any sample > 1s means the loop is blocked.
    """

    host = BASE
    wait_time = constant_passthrough(0.05)
    max_gap = 0.0
    stall_count = 0
    total = 0

    @task
    def probe(self):
        t0 = time.perf_counter()
        try:
            self.client.get("/health", name="GET /health [stall probe]")
        finally:
            dt = time.perf_counter() - t0
            type(self).total += 1
            if dt > type(self).max_gap:
                type(self).max_gap = dt
            if dt > 1.0:
                type(self).stall_count += 1


@events.quitting.add_listener
def _report(environment, **_):
    cls = EventLoopStallUser
    if cls.total:
        print(f"\n=== EVENT LOOP STALL REPORT ===")
        print(f"  samples          : {cls.total}")
        print(f"  samples > 1s    : {cls.stall_count}")
        print(f"  worst /health   : {cls.max_gap * 1000:.0f} ms")
        print(f"  verdict         : {'FAIL - loop blocked' if cls.stall_count else 'PASS'}")
