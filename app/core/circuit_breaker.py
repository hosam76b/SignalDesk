"""Per-provider circuit breaker for outbound AI calls.

A provider that times out, refuses connections, or returns garbage should fail
fast instead of consuming the full request timeout on every post. Without this,
a dead provider costs ``batch_size x ai_request_timeout`` seconds of wall clock
per batch (measured: 50 posts x 180s = 2.5 hours with a stalled endpoint).

States
------
closed      -> normal operation, failures counted
open        -> short-circuit: calls fail immediately with a fast, clear error
half_open   -> one trial call allowed through; success closes, failure re-opens

The breaker is intentionally simple and in-process. A desktop deployment has a
single worker, so a shared store would add complexity without benefit.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Literal

logger = logging.getLogger(__name__)

CircuitState = Literal["closed", "open", "half_open"]


class CircuitOpenError(RuntimeError):
    """Raised instead of calling a provider whose breaker is open."""

    def __init__(self, provider: str, retry_in: float) -> None:
        super().__init__(
            f"Circuit open for provider '{provider}'; retry in {retry_in:.0f}s"
        )
        self.provider = provider
        self.retry_in = retry_in


@dataclass
class CircuitStats:
    state: CircuitState = "closed"
    consecutive_failures: int = 0
    total_failures: int = 0
    total_successes: int = 0
    opened_at: float | None = None
    last_error: str | None = None

    def as_dict(self) -> dict:
        return {
            "state": self.state,
            "consecutive_failures": self.consecutive_failures,
            "total_failures": self.total_failures,
            "total_successes": self.total_successes,
            "last_error": self.last_error,
        }


class CircuitBreaker:
    """Thread-safe circuit breaker guarding a single dependency."""

    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._clock = clock
        self._lock = threading.Lock()
        self._stats = CircuitStats()

    # -- introspection -------------------------------------------------
    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._maybe_half_open_locked()
            return self._stats.state

    def stats(self) -> dict:
        with self._lock:
            self._maybe_half_open_locked()
            return self._stats.as_dict()

    def reset(self) -> None:
        with self._lock:
            self._stats = CircuitStats()

    # -- gate ----------------------------------------------------------
    def _maybe_half_open_locked(self) -> None:
        """Promote open -> half_open once the cooldown has elapsed."""
        stats = self._stats
        if stats.state != "open" or stats.opened_at is None:
            return
        if self._clock() - stats.opened_at >= self.recovery_timeout:
            stats.state = "half_open"
            logger.info("Circuit '%s' entering half-open trial", self.name)

    def before_call(self) -> None:
        """Raise CircuitOpenError when the breaker is rejecting traffic."""
        with self._lock:
            self._maybe_half_open_locked()
            stats = self._stats
            if stats.state == "closed":
                return
            if stats.state == "half_open":
                return  # allow exactly one trial; concurrent trials are
                         # naturally limited by the caller's own concurrency cap
            retry_in = max(
                0.0,
                self.recovery_timeout - (self._clock() - (stats.opened_at or 0.0)),
            )
            raise CircuitOpenError(self.name, retry_in)

    # -- outcome reporting ---------------------------------------------
    def record_success(self) -> None:
        with self._lock:
            self._stats.total_successes += 1
            self._stats.consecutive_failures = 0
            if self._stats.state != "closed":
                logger.info("Circuit '%s' closed after successful trial", self.name)
            self._stats.state = "closed"
            self._stats.opened_at = None
            self._stats.last_error = None

    def record_failure(self, error: str | None = None) -> None:
        with self._lock:
            stats = self._stats
            stats.total_failures += 1
            stats.consecutive_failures += 1
            stats.last_error = error
            if stats.state == "half_open" or (
                stats.consecutive_failures >= self.failure_threshold
            ):
                if stats.state != "open":
                    logger.warning(
                        "Circuit '%s' opened after %d consecutive failures: %s",
                        self.name,
                        stats.consecutive_failures,
                        error,
                    )
                stats.state = "open"
                stats.opened_at = self._clock()
