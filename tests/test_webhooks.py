"""Tests for webhook settings, RBAC, HMAC signing, and delivery logging."""

import asyncio
import hashlib
import hmac
import json

import httpx
import pytest

from app.models.webhook import Webhook, WebhookDelivery
from app.services import webhook_service
from app.services.webhook_service import (
    WEBHOOK_EVENTS,
    build_headers,
    dispatch_event,
    normalize_events,
    sign_payload,
)


def test_normalize_events_defaults_and_dedup():
    assert normalize_events(None) == ["post_ingested"]
    assert normalize_events([]) == ["post_ingested"]
    assert normalize_events(["post_ingested", "post_ingested", "report_ready"]) == ["post_ingested", "report_ready"]


def test_normalize_events_rejects_unknown():
    with pytest.raises(ValueError):
        normalize_events(["not_an_event"])


def test_sign_payload_is_hmac_sha256():
    body = b'{"event": "test"}'
    expected = hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
    assert sign_payload("s3cret", body) == expected


def test_build_headers_signs_only_with_secret(db):
    webhook = Webhook(name="a", url="https://n8n.example.com/webhook/1", secret="topsecret", events=["post_ingested"])
    headers = build_headers(webhook, "post_ingested", "uid-1", b"{}")
    assert headers["X-Webhook-Event"] == "post_ingested"
    assert headers["X-Webhook-Delivery"] == "uid-1"
    assert headers["X-Webhook-Signature"].startswith("sha256=")

    unsigned = Webhook(name="b", url="https://n8n.example.com/webhook/2", secret="", events=["post_ingested"])
    assert "X-Webhook-Signature" not in build_headers(unsigned, "post_ingested", "uid-2", b"{}")


def test_admin_crud_webhooks(super_admin_client):
    created = super_admin_client.post(
        "/api/webhooks",
        json={
            "name": "n8n flow",
            "url": "https://n8n.example.com/webhook/abc",
            "secret": "topsecret",
            "events": ["post_ingested", "alert_triggered"],
        },
    )
    assert created.status_code == 201, created.text
    data = created.json()
    assert data["has_secret"] is True
    assert "secret" not in data
    assert data["events"] == ["post_ingested", "alert_triggered"]
    webhook_id = data["id"]

    listed = super_admin_client.get("/api/webhooks")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [webhook_id]

    updated = super_admin_client.patch(f"/api/webhooks/{webhook_id}", json={"name": "renamed", "is_active": False})
    assert updated.status_code == 200
    assert updated.json()["name"] == "renamed"
    assert updated.json()["is_active"] is False
    # Secret is kept unless explicitly provided.
    assert updated.json()["has_secret"] is True

    cleared = super_admin_client.patch(f"/api/webhooks/{webhook_id}", json={"secret": ""})
    assert cleared.status_code == 200
    assert cleared.json()["has_secret"] is False

    deleted = super_admin_client.delete(f"/api/webhooks/{webhook_id}")
    assert deleted.status_code == 204
    assert super_admin_client.get(f"/api/webhooks/{webhook_id}").status_code == 404


def test_webhook_crud_requires_admin(client, topic_a_admin_client, topic_a_monitor_client):
    assert client.get("/api/webhooks").status_code in {401, 403}
    for non_admin in (topic_a_admin_client, topic_a_monitor_client):
        assert non_admin.get("/api/webhooks").status_code == 403
        assert non_admin.post(
            "/api/webhooks", json={"name": "x", "url": "https://n8n.example.com/webhook/abc"}
        ).status_code == 403


def test_webhook_validation(super_admin_client):
    bad_url = super_admin_client.post("/api/webhooks", json={"name": "x", "url": "ftp://nope"})
    assert bad_url.status_code == 422

    bad_event = super_admin_client.post(
        "/api/webhooks", json={"name": "x", "url": "https://n8n.example.com/webhook/abc", "events": ["bogus"]}
    )
    assert bad_event.status_code == 422


def test_events_catalog(super_admin_client):
    response = super_admin_client.get("/api/webhooks/events")
    assert response.status_code == 200
    names = [event["name"] for event in response.json()["events"]]
    assert names == list(WEBHOOK_EVENTS)


def test_post_ingested_returns_503_when_nothing_configured(super_admin_client):
    response = super_admin_client.post("/api/webhooks/post-ingested", json={"post_ids": []})
    assert response.status_code == 503


@pytest.fixture()
def mock_http(monkeypatch):
    """Replace httpx clients in the webhook service with a MockTransport capture."""
    captured: dict = {"requests": []}
    status_code = {"value": 200}
    real_async_client = httpx.AsyncClient
    real_client = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        captured["requests"].append(
            {"headers": dict(request.headers), "body": json.loads(request.content.decode())}
        )
        return httpx.Response(status_code["value"], json={"ok": status_code["value"] == 200})

    def async_client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_async_client(*args, **kwargs)

    def sync_client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(webhook_service.httpx, "AsyncClient", async_client_factory)
    monkeypatch.setattr(webhook_service.httpx, "Client", sync_client_factory)
    captured["set_status"] = lambda code: status_code.update(value=code)
    return captured


def test_dispatch_event_delivers_signs_and_logs(db, seeded_db, mock_http):
    webhook = Webhook(
        name="n8n",
        url="https://n8n.example.com/webhook/abc",
        secret="s3cret",
        events=["post_ingested"],
        is_active=True,
    )
    inactive = Webhook(
        name="off",
        url="https://n8n.example.com/webhook/off",
        secret="",
        events=["post_ingested"],
        is_active=False,
    )
    other_event = Webhook(
        name="reports-only",
        url="https://n8n.example.com/webhook/reports",
        secret="",
        events=["report_ready"],
        is_active=True,
    )
    db.add_all([webhook, inactive, other_event])
    db.commit()

    result = asyncio.run(dispatch_event(db, "post_ingested", {"posts": [{"id": 1}]}))

    assert result["attempted"] == 1
    assert result["delivered"] == 1
    assert len(mock_http["requests"]) == 1

    sent = mock_http["requests"][0]
    assert sent["headers"]["x-webhook-event"] == "post_ingested"
    body_bytes = json.dumps(sent["body"], ensure_ascii=False).encode()
    expected = hmac.new(b"s3cret", body_bytes, hashlib.sha256).hexdigest()
    assert sent["headers"]["x-webhook-signature"] == f"sha256={expected}"
    assert sent["body"]["event"] == "post_ingested"
    assert sent["body"]["data"]["posts"] == [{"id": 1}]

    deliveries = db.query(WebhookDelivery).all()
    assert len(deliveries) == 1
    assert deliveries[0].success is True
    assert deliveries[0].status_code == 200
    assert deliveries[0].event == "post_ingested"


def test_dispatch_event_logs_failures(db, seeded_db, mock_http):
    webhook = Webhook(
        name="n8n",
        url="https://n8n.example.com/webhook/abc",
        secret="",
        events=["alert_triggered"],
        is_active=True,
    )
    db.add(webhook)
    db.commit()
    mock_http["set_status"](500)

    result = asyncio.run(dispatch_event(db, "alert_triggered", {"topic_id": 1}))

    assert result["delivered"] == 0
    assert result["success"] is False
    delivery = db.query(WebhookDelivery).one()
    assert delivery.success is False
    assert delivery.status_code == 500
    assert delivery.error
