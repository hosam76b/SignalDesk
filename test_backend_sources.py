"""Backend source CRUD, validation, and authorization integration tests."""


def source_payload(name="New Source", url="https://example.com/feed.xml"):
    return {
        "platform": "rss",
        "name": name,
        "url_or_handle": url,
        "target_type": "url",
        "is_active": True,
    }


def test_source_crud_toggle_and_validation(topic_a_admin_client, seeded_db):
    topic_id = seeded_db["topic_a"].id
    created = topic_a_admin_client.post(
        f"/api/v1/topics/{topic_id}/sources",
        json=source_payload(),
    )
    assert created.status_code == 201, f"Valid source creation failed: {created.text}"
    source = created.json()
    source_id = source["id"]
    assert source["status"] == "active", "New sources must start active"

    listed = topic_a_admin_client.get(f"/api/v1/topics/{topic_id}/sources")
    assert listed.status_code == 200, f"Source list failed: {listed.text}"
    assert any(item["id"] == source_id for item in listed.json()), "Created source must be listable"

    updated = topic_a_admin_client.put(
        f"/api/v1/topics/{topic_id}/sources/{source_id}",
        json=source_payload(name="Updated Source"),
    )
    assert updated.status_code == 200, f"Source update failed: {updated.text}"
    assert updated.json()["name"] == "Updated Source", "Source update must persist"

    toggled = topic_a_admin_client.patch(f"/api/v1/topics/{topic_id}/sources/{source_id}/toggle")
    assert toggled.status_code == 200, f"Source toggle failed: {toggled.text}"
    assert toggled.json()["is_active"] is False, "Toggle must deactivate an active source"
    assert toggled.json()["status"] == "disabled", "Disabled source must expose disabled status"

    deleted = topic_a_admin_client.delete(f"/api/v1/topics/{topic_id}/sources/{source_id}")
    assert deleted.status_code == 204, f"Source delete failed: {deleted.text}"
    assert not any(item["id"] == source_id for item in topic_a_admin_client.get(f"/api/v1/topics/{topic_id}/sources").json()), "Deleted source must disappear"

    invalid = topic_a_admin_client.post(
        f"/api/v1/topics/{topic_id}/sources",
        json=source_payload(url="javascript:alert(1)"),
    )
    assert invalid.status_code == 422, "Non-HTTP source targets must be rejected"

    duplicate = topic_a_admin_client.post(
        f"/api/v1/topics/{topic_id}/sources",
        json=source_payload(name="Duplicate Source", url="https://example.com/a"),
    )
    assert duplicate.status_code == 409, "A source target must be globally unique"


def test_source_management_is_topic_isolated(topic_a_admin_client, seeded_db):
    topic_b_id = seeded_db["topic_b"].id
    response = topic_a_admin_client.get(f"/api/v1/topics/{topic_b_id}/sources")
    assert response.status_code == 403, "Topic admins must not read sources outside their assignment"
