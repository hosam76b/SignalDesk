from __future__ import annotations

from app.services import update_service


def test_update_status_reports_new_commit(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"sha": "new-commit-sha"}

    monkeypatch.setattr(update_service, "_current_version", lambda: "old-commit-sha")
    monkeypatch.setattr(update_service.httpx, "get", lambda *args, **kwargs: Response())
    monkeypatch.setattr(update_service.settings, "update_check_enabled", True)
    monkeypatch.setattr(update_service.settings, "update_check_interval_seconds", 0)
    update_service._cache.update({"checked_at": 0.0, "status": None})

    result = update_service.get_update_status()

    assert result["update_available"] is True
    assert result["current_version"] == "old-commit-sha"
    assert result["latest_version"] == "new-commit-sha"


def test_update_status_is_current_when_commit_matches(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"sha": "same-commit-sha"}

    monkeypatch.setattr(update_service, "_current_version", lambda: "same-commit-sha")
    monkeypatch.setattr(update_service.httpx, "get", lambda *args, **kwargs: Response())
    monkeypatch.setattr(update_service.settings, "update_check_enabled", True)
    monkeypatch.setattr(update_service.settings, "update_check_interval_seconds", 0)
    update_service._cache.update({"checked_at": 0.0, "status": None})

    result = update_service.get_update_status()

    assert result["update_available"] is False
    assert result["error"] is None
