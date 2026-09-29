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

Single source of truth for the port
-----------------------------------
The probe must target the port this process actually binds, and that number is
now passed in (``start(port=...)``) from ``main.py``, which reads it from
``SIGNALDESK_PORT`` -- the same value NSSM hands to uvicorn's ``--port``. A
hard-coded default here is what made the loop kill a perfectly healthy server:
the probe was pointed at 8010 while uvicorn served 8000, so three probes found
no listener, the check declared a dead accept loop, and the process exited
while it was still serving traffic. The configured value is only a fallback
now, and any disagreement between the two is logged instead of being fatal.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Callable

from config import settings

logger = logging.getLogger(__name__)

#: Last-resort probe target, used only when neither the caller nor the settings
#: supply one. Never the normal path: main.py always passes the bound port.
_DEFAULT_PORT = 8000

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
        self._port: int = _DEFAULT_PORT
        self._consecutive_failures = 0
        self._probes = 0
        self._failures = 0

    # -- lifecycle -----------------------------------------------------
    def start(self, port: int | None = None) -> bool:
        """Start the loop. Returns False when disabled or already running.

        ``port`` is the port uvicorn binds and must be the authoritative one.
        Resolution order: the explicit argument, then ``SELF_CHECK_PORT`` from
        the environment, then the built-in default. Passing it explicitly is
        what keeps the probe from drifting onto a port this process does not
        serve; a disagreement with the configured value is logged loudly
        because that disagreement is the exact cause of a false "the accept
        loop is dead" verdict.
        """
        if not bool(getattr(settings, "self_check_enabled", True)):
            logger.info("Socket self-check disabled; relying on external monitoring")
            return False
        if self._task is not None and not self._task.done():
            return False
        configured = getattr(settings, "self_check_port", None)
        self._port = self._resolve_port(port, configured)
        self._consecutive_failures = 0
        self._task = asyncio.get_running_loop().create_task(
            self._run(), name="socket-self-check"
        )
        logger.info(
            "Socket self-check started: %s:%s every %ss, exit after %s failure(s) "
            "(port source: %s)",
            getattr(settings, "self_check_host", "127.0.0.1"),
            self._port,
            getattr(settings, "self_check_interval_seconds", 30),
            getattr(settings, "self_check_failure_threshold", 3),
            "argument" if port else "settings" if configured else "default",
        )
        return True

    @staticmethod
    def _resolve_port(port: int | None, configured: int | None) -> int:
        """Pick the probe target and warn when the two sources disagree."""
        if port:
            resolved = int(port)
            if configured and int(configured) != resolved:
                logger.warning(
                    "Self-check port %s (passed by the caller, i.e. the port "
                    "uvicorn binds) differs from SELF_CHECK_PORT=%s in the "
                    "environment; probing %s. Point SELF_CHECK_PORT at the "
                    "bound port too, or the next reader will be misled.",
                    resolved,
                    configured,
                    resolved,
                )
            return resolved
        if configured:
            return int(configured)
        return _DEFAULT_PORT

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
        # Read through self._port rather than settings: start() already
        # resolved the authoritative target from the caller.
        port = self._port
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
            "port": self._port,
            "probes": self._probes,
            "failures": self._failures,
            "consecutive_failures": self._consecutive_failures,
        }


#: Process-wide singleton wired into the FastAPI lifespan.
self_check = SocketSelfCheck()
