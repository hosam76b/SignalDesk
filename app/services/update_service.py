"""Check whether a newer SignalDesk commit is available on GitHub."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from threading import Lock
from typing import Any

import httpx

from config import settings

_project_root = Path(__file__).resolve().parents[2]
_cache: dict[str, Any] = {"checked_at": 0.0, "status": None}
_cache_lock = Lock()


def _current_version() -> str:
    """Use the checked-out commit when available, otherwise app_version."""
    try:
        result = subprocess.run(
            ["git", "-C", str(_project_root), "rev-parse", "HEAD"],
            capture_output=True,
            check=True,
            text=True,
            timeout=3,
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return str(settings.app_version)


def _unavailable(current_version: str, error: str) -> dict[str, Any]:
    return {
        "update_check_enabled": bool(settings.update_check_enabled),
        "update_available": False,
        "current_version": current_version,
        "latest_version": None,
        "release_url": None,
        "error": error,
    }


def get_update_status() -> dict[str, Any]:
    """Return cached GitHub update information without raising to the API."""
    current_version = _current_version()
    if not settings.update_check_enabled:
        return _unavailable(current_version, "Update checks are disabled")

    now = time.monotonic()
    with _cache_lock:
        cached = _cache["status"]
        if cached is not None and now - _cache["checked_at"] < settings.update_check_interval_seconds:
            return {**cached, "current_version": current_version}

    repository = str(settings.update_repository).strip()
    branch = str(settings.update_branch).strip() or "main"
    if "/" not in repository:
        return _unavailable(current_version, "Update repository is invalid")

    url = f"https://api.github.com/repos/{repository}/commits/{branch}"
    try:
        response = httpx.get(
            url,
            headers={"Accept": "application/vnd.github+json"},
            timeout=5,
            follow_redirects=True,
            trust_env=False,
        )
        response.raise_for_status()
        payload = response.json()
        latest_version = str(payload.get("sha") or "").strip()
        if not latest_version:
            raise ValueError("GitHub did not return a commit SHA")
        status = {
            "update_check_enabled": True,
            "update_available": latest_version != current_version,
            "current_version": current_version,
            "latest_version": latest_version,
            "release_url": f"https://github.com/{repository}/commits/{branch}",
            "error": None,
        }
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        status = _unavailable(current_version, str(exc) or type(exc).__name__)

    with _cache_lock:
        _cache["checked_at"] = time.monotonic()
        _cache["status"] = status
    return status