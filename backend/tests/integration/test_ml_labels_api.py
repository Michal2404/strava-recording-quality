from __future__ import annotations

import pytest

from app.models.activity import Activity
from app.models.activity_quality_label import ActivityQualityLabel
from app.models.user import User


def _seed_activity(db_session) -> Activity:
    user = User(
        strava_athlete_id=777001,
        firstname="Label",
        lastname="Tester",
    )
    db_session.add(user)
    db_session.flush()

    activity = Activity(
        strava_activity_id=888001,
        user_id=user.id,
        name="Label Target",
        sport_type="Run",
    )
    db_session.add(activity)
    db_session.commit()
    db_session.refresh(activity)
    return activity


@pytest.mark.integration
def test_upsert_label_creates_and_lists(api_client, db_session):
    activity = _seed_activity(db_session)

    create_payload = {
        "label_bad": True,
        "label_source": "manual",
        "label_reason": "Multiple GPS teleports",
        "label_confidence": 0.9,
        "label_version": 1,
        "created_by": "michal",
    }
    create_response = api_client.post(f"/ml/activities/{activity.id}/label", json=create_payload)

    assert create_response.status_code == 200
    created = create_response.json()
    assert created["activity_id"] == activity.id
    assert created["label_bad"] is True
    assert created["label_source"] == "manual"
    assert created["label_reason"] == "Multiple GPS teleports"
    assert created["label_confidence"] == 0.9
    assert created["created_by"] == "michal"

    list_response = api_client.get("/ml/labels")
    assert list_response.status_code == 200
    items = list_response.json()
    assert len(items) == 1
    assert items[0]["id"] == created["id"]
    assert items[0]["activity_id"] == activity.id

    filtered_response = api_client.get("/ml/labels?label_bad=true&label_source=manual")
    assert filtered_response.status_code == 200
    filtered = filtered_response.json()
    assert len(filtered) == 1
    assert filtered[0]["id"] == created["id"]


@pytest.mark.integration
def test_upsert_label_updates_existing_row(api_client, db_session):
    activity = _seed_activity(db_session)

    first = api_client.post(
        f"/ml/activities/{activity.id}/label",
        json={
            "label_bad": True,
            "label_source": "manual",
            "label_reason": "first",
            "label_confidence": 0.8,
            "label_version": 1,
            "created_by": "michal",
        },
    )
    assert first.status_code == 200
    first_payload = first.json()

    second = api_client.post(
        f"/ml/activities/{activity.id}/label",
        json={
            "label_bad": False,
            "label_source": "manual",
            "label_reason": "updated",
            "label_confidence": 0.6,
            "label_version": 1,
            "created_by": "michal",
        },
    )
    assert second.status_code == 200
    second_payload = second.json()

    assert second_payload["id"] == first_payload["id"]
    assert second_payload["label_bad"] is False
    assert second_payload["label_reason"] == "updated"
    assert second_payload["label_confidence"] == 0.6

    db_session.expire_all()
    labels = db_session.query(ActivityQualityLabel).all()
    assert len(labels) == 1
    assert labels[0].activity_id == activity.id
    assert labels[0].label_bad is False


@pytest.mark.integration
def test_upsert_label_requires_existing_activity(api_client):
    response = api_client.post(
        "/ml/activities/99999/label",
        json={
            "label_bad": True,
            "label_source": "manual",
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Activity not found"


@pytest.mark.integration
def test_upsert_label_validates_source(api_client, db_session):
    activity = _seed_activity(db_session)

    response = api_client.post(
        f"/ml/activities/{activity.id}/label",
        json={
            "label_bad": True,
            "label_source": "not_allowed",
        },
    )

    assert response.status_code == 400
    assert "label_source must be one of:" in response.json()["detail"]
