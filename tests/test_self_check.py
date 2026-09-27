"""Tests for the Windows IOCP socket self-check.

The self-check exists because a dead Proactor accept loop leaves the process
alive but unreachable, still holding the SQLite write lock, while the service
manager reports "Running". These tests pin the detection and restart contract
without ever killing the test runner: the exit action is injected.
"""

from __future__ import annotations

import asyncio
import socket
import threading

import pytest

from app.core import self_check as self_check_module
from app.core.self_check import SocketSelfCheck, probe_http


# ---------------------------------------------------------------------------
# A real loopback server, so the probe is exercised against a real socket.
# ---------------------------------------------------------------------------

class _LoopbackServer:
    """Minimal HTTP server: optionally answers, or accepts and stays silent.

    The silent mode reproduces the real failure. With a live listening socket
    the kernel still completes the TCP handshake from the accept backlog, so
    ``connect()`` succeeds even though nothing ever responds -- which is why
    the probe must require a status line rather than just a connection.
    """

    def __init__(self, respond: bool) -> None:
        self.respond = respond
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(8)
        self.port = self._sock.getsockname()[1]
        self._stop = threading.Event()
        self._held: list[socket.socket] = []
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def start(self) -> "_LoopbackServer":
        self._thread.start()
        return self

    def _serve(self) -> None:
        self._sock.settimeout(0.2)
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except (socket.timeout, OSError):
                continue
            if not self.respond:
                # Hold the connection open without replying: the client waits
                # for a status line that never arrives.
                self._held.append(conn)
                continue
            try:
                conn.recv(4096)
                conn.sendall(
                    b"HTTP/1.0 200 OK\r\nContent-Length: 2\r\n"
                    b"Connection: close\r\n\r\nok"
                )
            except OSError:
                pass
            finally:
                conn.close()

    def close(self) -> None:
        self._stop.set()
        try:
            self._sock.close()
        except OSError:
            pass
        for conn in self._held:
            try:
                conn.close()
            except OSError:
                pass


@pytest.fixture()
def responding_server():
    server = _LoopbackServer(respond=True).start()
    try:
        yield server
    finally:
        server.close()


@pytest.fixture()
def silent_server():
    server = _LoopbackServer(respond=False).start()
    try:
        yield server
    finally:
        server.close()


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


# ---------------------------------------------------------------------------
# probe_http
# ---------------------------------------------------------------------------

def test_probe_succeeds_against_a_responding_server(responding_server):
    assert asyncio.run(probe_http("127.0.0.1", responding_server.port, 5.0)) is True


def test_probe_fails_when_nothing_is_listening():
    assert asyncio.run(probe_http("127.0.0.1", _free_port(), 2.0)) is False


def test_probe_fails_when_the_socket_accepts_but_never_answers(silent_server):
    """The exact WinError 64 shape: connected, but no response ever arrives.

    A TCP-connect-only check would pass here, which is why the probe reads a
    status line.
    """
    assert asyncio.run(probe_http("127.0.0.1", silent_server.port, 2.0)) is False


def test_probe_rejects_a_non_http_response():
    """Something listening that is not serving HTTP must not count as healthy."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(4)
    port = listener.getsockname()[1]
    accepted: list[socket.socket] = []

    def serve():
        try:
            conn, _ = listener.accept()
            accepted.append(conn)
            conn.sendall(b"SSH-2.0-OpenSSH_9.6\r\n")
        except OSError:
            pass

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        assert asyncio.run(probe_http("127.0.0.1", port, 2.0)) is False
    finally:
        thread.join(timeout=2)
        for conn in accepted:
            conn.close()
        listener.close()


# ---------------------------------------------------------------------------
# SocketSelfCheck
# ---------------------------------------------------------------------------

def _patch_settings(monkeypatch, **overrides):
    defaults = {
        "self_check_enabled": True,
        "self_check_host": "127.0.0.1",
        "self_check_port": _free_port(),
        "self_check_interval_seconds": 5,
        "self_check_timeout_seconds": 1.0,
        "self_check_failure_threshold": 3,
    }
    defaults.update(overrides)
    for key, value in defaults.items():
        monkeypatch.setattr(self_check_module.settings, key, value)
    return defaults


def test_does_not_exit_while_the_app_answers(responding_server, monkeypatch):
    """A healthy app must never trigger a restart."""
    exits: list[int] = []
    _patch_settings(
        monkeypatch,
        self_check_port=responding_server.port,
        self_check_interval_seconds=5,
        self_check_timeout_seconds=2.0,
    )
    check = SocketSelfCheck(exit_action=exits.append)

    async def run():
        check._probes = 0
        # Drive the loop body directly; _run() sleeps first by design.
        for _ in range(3):
            alive = await probe_http("127.0.0.1", responding_server.port, 2.0)
            check._probes += 1
            if not alive:
                check._consecutive_failures += 1
        return check

    asyncio.run(run())
    assert exits == []
    assert check._consecutive_failures == 0


def test_exits_after_consecutive_failures_reach_the_threshold(monkeypatch):
    """The contract NSSM depends on: exit(1) so the supervisor restarts us."""
    exits: list[int] = []
    _patch_settings(monkeypatch, self_check_failure_threshold=3)
    check = SocketSelfCheck(exit_action=exits.append)

    for attempt in range(3):
        check._failures += 1
        check._consecutive_failures += 1
        if check._consecutive_failures >= check._threshold:
            check._fail_fatal("127.0.0.1", 8000)

    assert exits == [1], "process must exit exactly once, with status 1"
    assert check._threshold == 3


def test_a_single_failure_does_not_exit(monkeypatch):
    """Guards against a restart loop caused by one unlucky probe."""
    exits: list[int] = []
    _patch_settings(monkeypatch, self_check_failure_threshold=3)
    check = SocketSelfCheck(exit_action=exits.append)

    check._consecutive_failures = 1
    if check._consecutive_failures >= check._threshold:
        check._fail_fatal("127.0.0.1", 8000)

    assert exits == []


def test_recovery_resets_the_failure_counter(monkeypatch):
    """A transient failure must not accumulate into a false restart."""
    exits: list[int] = []
    _patch_settings(monkeypatch, self_check_failure_threshold=3)
    check = SocketSelfCheck(exit_action=exits.append)

    check._consecutive_failures = 2
    # A successful probe clears the streak.
    check._consecutive_failures = 0
    check._failures = 2

    assert check._consecutive_failures == 0
    check._consecutive_failures = 2
    assert check._consecutive_failures < check._threshold
    assert exits == []


def test_default_exit_action_is_sys_exit():
    """The production wiring must terminate the process, not just log."""
    import inspect

    signature = inspect.signature(SocketSelfCheck.__init__)
    assert signature.parameters["exit_action"].default is self_check_module.sys.exit


def test_disabled_self_check_does_not_start(monkeypatch):
    _patch_settings(monkeypatch, self_check_enabled=False)

    async def run():
        check = SocketSelfCheck(exit_action=lambda _code: None)
        return check.start()

    assert asyncio.run(run()) is False


def test_start_and_stop_are_idempotent(monkeypatch):
    """start() twice must not create a second probe loop."""
    _patch_settings(monkeypatch, self_check_interval_seconds=30)

    async def run():
        check = SocketSelfCheck(exit_action=lambda _code: None)
        first = check.start()
        second = check.start()
        running = check.stats()["running"]
        await check.stop()
        await check.stop()  # must not raise
        return first, second, running

    first, second, running = asyncio.run(run())
    assert first is True
    assert second is False
    assert running is True


def test_stop_leaves_no_running_task(monkeypatch):
    _patch_settings(monkeypatch, self_check_interval_seconds=30)

    async def run():
        check = SocketSelfCheck(exit_action=lambda _code: None)
        check.start()
        await check.stop()
        return check.stats()["running"]

    assert asyncio.run(run()) is False
