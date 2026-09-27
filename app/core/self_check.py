"""Socket self-check: detect a dead accept loop and exit for a restart.

Why this exists
---------------
On Windows, asyncio's Proactor event loop accepts connections through IOCP.
That accept can fail with::

    ERROR:asyncio:Accept failed on a socket
    OSError: [WinError 64] The specified network name is no longer available

The failure is not fatal to the process. Uvicorn stops accepting, but the
process keeps running: the AI worker and the scraper keep going, and because
the AI worker holds SQLite's single write lock, every other writer in the
process starts failing with ``database is locked``. Meanwhile the Windows
service manager still reports the service as ``Running``.

The observable failure mode is an application that is completely unreachable
while every status command says it is fine. This was seen twice in one day.

Recovery
--------
A probe loop connects to the app's own port and requires a real HTTP response.
A bare TCP connect is not enough: with a live listening socket the kernel
still completes the handshake from the accept backlog, so ``connect()``
succeeds even when nothing ever calls ``accept()``. Requiring the status line
catches both shapes of failure -- no listener at all, and a listener that never
answers.

When ``self_check_failure_threshold`` consecutive probes fail, the process calls
``sys.exit(1)``. NSSM is configured with ``AppExit Default: Restart``, so the
service comes back within seconds rather than staying wedged indefinitely.

The exit action is injectable so the behaviour can be tested without killing
the test runner.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Callable

from config import settings

logger = logging.getLogger(__name__)

#: Minimal request that forces a real response. HTTP/1.0 plus ``Connection:
#: close`` makes the server close the connection after replying, so the read
#: below terminates instead of waiting on a keep-alive socket.
_PROBE_REQUEST = (
    "GET /health HTTP/1.0\r\n"
    "Host: {host}\r\n"
    "User-Agent: SignalDesk-SelfCheck\r\n"
    "Connection: close\r\n"
    "\r\n"
)


async def probe_http(host: str, port: int, timeout: float) -> bool:
    """Return True when the app answers an HTTP request on ``host:port``.

    Any failure -- refused connection, reset, or a timeout with no status line
    -- returns False. A response that is not an HTTP status line also returns
    False, because that means something is listening but not serving.
    """
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
    except (OSError, asyncio.TimeoutError):
        return False

    try:
        writer.write(_PROBE_REQUEST.format(host=host).encode("ascii"))
        await asyncio.wait_for(writer.drain(), timeout=timeout)
        status_line = await asyncio.wait_for(reader.readline(), timeout=timeout)
    except (OSError, asyncio.TimeoutError):
        return False
    finally:
        writer.close()
        try:
            # Give the close a moment; a wedged socket must not block the loop.
            await asyncio.wait_for(writer.wait_closed(), timeout=timeout)
        except (OSError, asyncio.TimeoutError):
            pass

    return status_line.startswith(b"HTTP/")


class SocketSelfCheck:
    """Background loop that exits the process once the listener stops answering."""

    def __init__(
        self,
        exit_action: Callable[[int], None] = sys.exit,
    ) -> None:
        self._exit = exit_action
        self._task: asyncio.Task | None = None
        self._consecutive_failures = 0
        self._probes = 0
        self._failures = 0

    # -- lifecycle -----------------------------------------------------
    def start(self) -> bool:
        """Start the loop. Returns False when disabled or already running."""
        if not bool(getattr(settings, "self_check_enabled", True)):
            logger.info("Socket self-check disabled; relying on external monitoring")
            return False
        if self._task is not None and not self._task.done():
            return False
        self._consecutive_failures = 0
        self._task = asyncio.get_running_loop().create_task(
            self._run(), name="socket-self-check"
        )
        logger.info(
            "Socket self-check started: %s:%s every %ss, exit after %s failure(s)",
            getattr(settings, "self_check_host", "127.0.0.1"),
            getattr(settings, "self_check_port", 8000),
            getattr(settings, "self_check_interval_seconds", 30),
            getattr(settings, "self_check_failure_threshold", 3),
        )
        return True

    async def stop(self) -> None:
        """Cancel the loop and wait for it to unwind."""
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # -- internals -----------------------------------------------------
    @property
    def _interval(self) -> float:
        return max(5.0, float(getattr(settings, "self_check_interval_seconds", 30) or 30))

    @property
    def _timeout(self) -> float:
        return max(0.5, float(getattr(settings, "self_check_timeout_seconds", 5.0) or 5.0))

    @property
    def _threshold(self) -> int:
        return max(1, int(getattr(settings, "self_check_failure_threshold", 3) or 3))

    async def _run(self) -> None:
        host = str(getattr(settings, "self_check_host", "127.0.0.1") or "127.0.0.1")
        port = int(getattr(settings, "self_check_port", 8000) or 8000)
        # The first probe is delayed: the socket is guaranteed to be listening
        # by the time the lifespan yields, but a probe issued in the same tick
        # would race the server task that is still entering its accept loop.
        await asyncio.sleep(self._interval)
        while True:
            alive = await probe_http(host, port, self._timeout)
            self._probes += 1
            if alive:
                if self._consecutive_failures:
                    logger.info(
                        "Socket self-check recovered after %s failure(s)",
                        self._consecutive_failures,
                    )
                self._consecutive_failures = 0
            else:
                self._failures += 1
                self._consecutive_failures += 1
                logger.warning(
                    "Socket self-check failed (%s/%s): no HTTP response from %s:%s",
                    self._consecutive_failures,
                    self._threshold,
                    host,
                    port,
                )
                if self._consecutive_failures >= self._threshold:
                    self._fail_fatal(host, port)
            await asyncio.sleep(self._interval)

    def _fail_fatal(self, host: str, port: int) -> None:
        """Log why we are going down, then exit so NSSM restarts the service."""
        logger.critical(
            "Socket self-check gave up after %s consecutive failures: %s:%s is not "
            "answering while this process is still alive, which means the accept "
            "loop is dead (Windows IOCP WinError 64). Exiting with status 1 so the "
            "service supervisor restarts the application.",
            self._consecutive_failures,
            host,
            port,
        )
        self._exit(1)

    # -- introspection -------------------------------------------------
    def stats(self) -> dict[str, int | bool]:
        return {
            "running": self._task is not None and not self._task.done(),
            "probes": self._probes,
            "failures": self._failures,
            "consecutive_failures": self._consecutive_failures,
        }


#: Process-wide singleton wired into the FastAPI lifespan.
self_check = SocketSelfCheck()
