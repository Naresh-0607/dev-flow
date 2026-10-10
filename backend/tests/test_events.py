from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Branch, Event, Project


def test_create_project_and_branch_from_commit_event(
    client: TestClient,
    db_session: Session,
    user_factory,
):
    """An incoming commit event creates the project and branch, and updates commit info."""
    user, api_key = user_factory(username="commituser")

    payload = {
        "type": "commit",
        "project": "dev-flow",
        "repo_path": "C:/Users/Naresh/Projects/dev-flow",
        "remote_url": "https://github.com/me/dev-flow.git",
        "branch": "main",
        "commit_hash": "a1b2c3d4",
        "message": "initial commit",
        "author": "naresh",
        "timestamp": "2026-10-10T10:00:00+00:00",
        "previous_branch": None,
    }

    response = client.post("/events", json=payload, headers={"X-API-Key": api_key})
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "created"
    assert data["event_id"] is not None

    # Verify project record
    project = (
        db_session.query(Project)
        .filter(Project.owner_id == user.id, Project.name == "dev-flow")
        .first()
    )
    assert project is not None
    assert project.identity_key == "https://github.com/me/dev-flow.git"

    # Verify branch record
    branch = (
        db_session.query(Branch)
        .filter(Branch.project_id == project.id, Branch.name == "main")
        .first()
    )
    assert branch is not None
    assert branch.last_commit_hash == "a1b2c3d4"
    assert branch.last_commit_message == "initial commit"
    assert branch.last_commit_author == "naresh"
    assert branch.is_active is True


def test_checkout_switches_active_branch(client: TestClient, db_session: Session, user_factory):
    """Checkout event marks the new branch active and sets previous branches inactive."""
    user, api_key = user_factory(username="checkoutuser")

    # Step 1: Commit on main
    client.post(
        "/events",
        json={
            "type": "commit",
            "project": "flow-app",
            "repo_path": "/path/to/flow-app",
            "branch": "main",
            "timestamp": "2026-10-10T10:00:00Z",
        },
        headers={"X-API-Key": api_key},
    )

    # Step 2: Checkout feature branch
    res = client.post(
        "/events",
        json={
            "type": "checkout",
            "project": "flow-app",
            "repo_path": "/path/to/flow-app",
            "branch": "feature-auth",
            "previous_branch": "main",
            "timestamp": "2026-10-10T10:05:00Z",
        },
        headers={"X-API-Key": api_key},
    )
    assert res.status_code == 201

    project = db_session.query(Project).filter(Project.owner_id == user.id).first()
    main_b = db_session.query(Branch).filter(Branch.project_id == project.id, Branch.name == "main").first()
    feat_b = db_session.query(Branch).filter(Branch.project_id == project.id, Branch.name == "feature-auth").first()

    assert main_b.is_active is False
    assert feat_b.is_active is True


def test_duplicate_events_are_idempotent(client: TestClient, db_session: Session, user_factory):
    """Sending the exact same event returns 200 duplicate without adding a second row."""
    user, api_key = user_factory(username="dedupeuser")

    payload = {
        "type": "commit",
        "project": "dedupe-proj",
        "repo_path": "/path/dedupe",
        "branch": "main",
        "commit_hash": "c0ffee",
        "timestamp": "2026-10-10T12:00:00+00:00",
    }

    # First attempt: created (201)
    res1 = client.post("/events", json=payload, headers={"X-API-Key": api_key})
    assert res1.status_code == 201
    assert res1.json()["status"] == "created"

    # Second attempt: duplicate (200)
    res2 = client.post("/events", json=payload, headers={"X-API-Key": api_key})
    assert res2.status_code == 200
    assert res2.json()["status"] == "duplicate"

    # Verify only 1 event row exists
    count = db_session.query(Event).count()
    assert count == 1


def test_duplicate_checkout_without_commit_hash(client: TestClient, db_session: Session, user_factory):
    """Checkout events without commit_hash are also properly deduplicated."""
    user, api_key = user_factory(username="dedupecheckout")

    payload = {
        "type": "checkout",
        "project": "dedupe-checkout-proj",
        "repo_path": "/path/checkout",
        "branch": "develop",
        "commit_hash": None,
        "timestamp": "2026-10-10T14:00:00Z",
    }

    res1 = client.post("/events", json=payload, headers={"X-API-Key": api_key})
    assert res1.status_code == 201

    res2 = client.post("/events", json=payload, headers={"X-API-Key": api_key})
    assert res2.status_code == 200
    assert res2.json()["status"] == "duplicate"

    count = db_session.query(Event).count()
    assert count == 1


def test_late_event_does_not_move_last_activity_backward(
    client: TestClient,
    db_session: Session,
    user_factory,
):
    """An event with an older timestamp must not move branch last_activity_at backward."""
    user, api_key = user_factory(username="lateuser")

    # Event 1: Newer timestamp (12:00)
    client.post(
        "/events",
        json={
            "type": "commit",
            "project": "timetravel-proj",
            "repo_path": "/path/timetravel",
            "branch": "main",
            "commit_hash": "newer",
            "timestamp": "2026-10-10T12:00:00Z",
        },
        headers={"X-API-Key": api_key},
    )

    # Event 2: Older timestamp (10:00) arriving later
    res = client.post(
        "/events",
        json={
            "type": "commit",
            "project": "timetravel-proj",
            "repo_path": "/path/timetravel",
            "branch": "main",
            "commit_hash": "older",
            "timestamp": "2026-10-10T10:00:00Z",
        },
        headers={"X-API-Key": api_key},
    )
    assert res.status_code == 201

    branch = db_session.query(Branch).filter(Branch.name == "main").first()
    expected_dt = datetime(2026, 10, 10, 12, 0, 0, tzinfo=timezone.utc)
    assert branch.last_activity_at == expected_dt


def test_invalid_event_payloads_return_422(client: TestClient, user_factory):
    """Invalid payloads (empty project, bad type, timestamp missing timezone) return 422."""
    user, api_key = user_factory(username="validationuser")
    headers = {"X-API-Key": api_key}

    # Empty project
    res1 = client.post(
        "/events",
        json={
            "type": "commit",
            "project": "   ",
            "repo_path": "/path/valid",
            "branch": "main",
            "timestamp": "2026-10-10T12:00:00Z",
        },
        headers=headers,
    )
    assert res1.status_code == 422

    # Invalid event type
    res2 = client.post(
        "/events",
        json={
            "type": "unsupported_type",
            "project": "my-project",
            "repo_path": "/path/valid",
            "branch": "main",
            "timestamp": "2026-10-10T12:00:00Z",
        },
        headers=headers,
    )
    assert res2.status_code == 422

    # Naive timestamp without timezone
    res3 = client.post(
        "/events",
        json={
            "type": "commit",
            "project": "my-project",
            "repo_path": "/path/valid",
            "branch": "main",
            "timestamp": "2026-10-10T12:00:00",
        },
        headers=headers,
    )
    assert res3.status_code == 422


def test_batch_events_endpoint(client: TestClient, user_factory):
    """Batch endpoint handles mixed valid and duplicate events independently."""
    user, api_key = user_factory(username="batchuser")
    headers = {"X-API-Key": api_key}

    batch_payload = [
        {
            "type": "commit",
            "project": "batch-proj",
            "repo_path": "/path/batch",
            "branch": "main",
            "commit_hash": "hash1",
            "timestamp": "2026-10-10T10:00:00Z",
        },
        {
            "type": "commit",
            "project": "batch-proj",
            "repo_path": "/path/batch",
            "branch": "main",
            "commit_hash": "hash1",
            "timestamp": "2026-10-10T10:00:00Z",  # Duplicate of first
        },
        {
            "type": "commit",
            "project": "batch-proj",
            "repo_path": "/path/batch",
            "branch": "main",
            "commit_hash": "hash2",
            "timestamp": "2026-10-10T10:05:00Z",
        },
    ]

    response = client.post("/events/batch", json=batch_payload, headers=headers)
    assert response.status_code == 200
    results = response.json()
    assert len(results) == 3
    assert results[0]["status"] == "created"
    assert results[1]["status"] == "duplicate"
    assert results[2]["status"] == "created"
