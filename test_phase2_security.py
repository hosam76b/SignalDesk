"""Phase 2 RBAC and topic authorization security tests."""


def source_payload(name="Updated Feed"):
    return {"platform": "rss", "name": name, "url_or_handle": "https://example.com/updated"}


def keyword_payload(word="updated keyword"):
    return {"word_or_phrase": word, "category": "general"}


def test_cross_topic_access_is_forbidden(topic_a_admin_client, seeded_db):
    topic_b_id = seeded_db["topic_b"].id
    source_id = seeded_db["topic_b"].sources[0].id
    keyword_id = seeded_db["topic_b"].keywords[0].id
    for method, path, payload in (
        ("get", f"/api/v1/topics/{topic_b_id}/sources", None),
        ("post", f"/api/v1/topics/{topic_b_id}/sources", source_payload()),
        ("put", f"/api/v1/topics/{topic_b_id}/sources/{source_id}", source_payload()),
        ("delete", f"/api/v1/topics/{topic_b_id}/sources/{source_id}", None),
        ("get", f"/api/v1/topics/{topic_b_id}/keywords", None),
        ("post", f"/api/v1/topics/{topic_b_id}/keywords", keyword_payload()),
        ("put", f"/api/v1/topics/{topic_b_id}/keywords/{keyword_id}", keyword_payload()),
        ("delete", f"/api/v1/topics/{topic_b_id}/keywords/{keyword_id}", None),
        ("get", f"/api/v1/topics/{topic_b_id}/news", None),
        ("get", f"/api/v1/topics/{topic_b_id}/stats", None),
    ):
        response = getattr(topic_a_admin_client, method)(path, json=payload) if payload else getattr(topic_a_admin_client, method)(path)
        assert response.status_code == 403, f"Cross-topic {method.upper()} {path} must be forbidden, got {response.status_code}: {response.text}"


def test_monitor_cannot_modify_resources(topic_a_monitor_client, seeded_db):
    topic_a_id = seeded_db["topic_a"].id
    source = topic_a_monitor_client.get(f"/api/v1/topics/{topic_a_id}/sources")
    source_id = source.json()[0]["id"]
    keyword_id = topic_a_monitor_client.get(f"/api/v1/topics/{topic_a_id}/keywords").json()[0]["id"]
    for method, path, payload in (
        ("post", f"/api/v1/topics/{topic_a_id}/sources", source_payload()),
        ("put", f"/api/v1/topics/{topic_a_id}/sources/{source_id}", source_payload()),
        ("delete", f"/api/v1/topics/{topic_a_id}/sources/{source_id}", None),
        ("post", f"/api/v1/topics/{topic_a_id}/keywords", keyword_payload()),
        ("put", f"/api/v1/topics/{topic_a_id}/keywords/{keyword_id}", keyword_payload()),
        ("delete", f"/api/v1/topics/{topic_a_id}/keywords/{keyword_id}", None),
    ):
        response = getattr(topic_a_monitor_client, method)(path, json=payload) if payload else getattr(topic_a_monitor_client, method)(path)
        assert response.status_code == 403, f"Monitor {method.upper()} {path} must be forbidden, got {response.status_code}"


def test_unassigned_user_cannot_read_topic_data(unassigned_user_client, seeded_db):
    for suffix in ("news", "stats", "sources", "keywords"):
        response = unassigned_user_client.get(f"/api/v1/topics/{seeded_db['topic_a'].id}/{suffix}")
        assert response.status_code == 403, f"Unassigned user must not read {suffix}"


def test_super_admin_can_access_all_topics(super_admin_client, seeded_db):
    for topic in (seeded_db["topic_a"], seeded_db["topic_b"]):
        response = super_admin_client.get(f"/api/v1/topics/{topic.id}/sources")
        assert response.status_code == 200, f"SuperAdmin must access topic {topic.id}"
    topics = super_admin_client.get("/api/v1/topics")
    assert topics.status_code == 200, "SuperAdmin must list all topics"
    assert {topic["title"] for topic in topics.json()} >= {"Topic A", "Topic B"}, "SuperAdmin must see every topic"


def test_news_endpoint_does_not_leak_other_topics(super_admin_client, seeded_db):
    response = super_admin_client.get(f"/api/v1/topics/{seeded_db['topic_a'].id}/news")
    assert response.status_code == 200
    assert all(item["topic_id"] == seeded_db["topic_a"].id for item in response.json()), "Topic A news must contain no Topic B records"


def test_topic_admin_can_manage_only_assigned_topic(topic_a_admin_client, seeded_db):
    topic_a_id = seeded_db["topic_a"].id
    source = topic_a_admin_client.post(f"/api/v1/topics/{topic_a_id}/sources", json=source_payload())
    keyword = topic_a_admin_client.post(f"/api/v1/topics/{topic_a_id}/keywords", json=keyword_payload())
    assert source.status_code == 201, f"Assigned topic admin source creation failed: {source.text}"
    assert keyword.status_code == 201, f"Assigned topic admin keyword creation failed: {keyword.text}"
