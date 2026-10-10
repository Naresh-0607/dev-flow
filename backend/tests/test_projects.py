from fastapi.testclient import TestClient


def test_projects_ordering_and_summary(client: TestClient, user_factory):
    """GET /projects returns projects ordered by last_activity_at DESC with correct branch counts."""
    user, api_key = user_factory(username="projorderuser")
    headers = {"X-API-Key": api_key}

    # Project 1: Older activity
    client.post(
        "/events",
        json={
            "type": "commit",
            "project": "older-project",
            "repo_path": "/path/older",
            "branch": "main",
            "timestamp": "2026-10-10T10:00:00Z",
        },
        headers=headers,
    )

    # Project 2: Newer activity with multiple branches
    client.post(
        "/events",
        json={
            "type": "commit",
            "project": "newer-project",
            "repo_path": "/path/newer",
            "branch": "main",
            "timestamp": "2026-10-10T12:00:00Z",
        },
        headers=headers,
    )
    client.post(
        "/events",
        json={
            "type": "checkout",
            "project": "newer-project",
            "repo_path": "/path/newer",
            "branch": "feature",
            "previous_branch": "main",
            "timestamp": "2026-10-10T13:00:00Z",
        },
        headers=headers,
    )

    res = client.get("/projects", headers=headers)
    assert res.status_code == 200
    projects = res.json()
    assert len(projects) == 2

    # Newest first
    assert projects[0]["name"] == "newer-project"
    assert projects[0]["branch_count"] == 2
    assert projects[0]["active_branch"] == "feature"

    assert projects[1]["name"] == "older-project"
    assert projects[1]["branch_count"] == 1
    assert projects[1]["active_branch"] == "main"


def test_get_project_detail_and_404(client: TestClient, user_factory):
    """GET /projects/{project_id} returns project detail, and 404 for unknown id."""
    user, api_key = user_factory(username="detailuser")
    headers = {"X-API-Key": api_key}

    res_post = client.post(
        "/events",
        json={
            "type": "commit",
            "project": "detail-project",
            "repo_path": "/path/detail",
            "branch": "main",
            "timestamp": "2026-10-10T10:00:00Z",
        },
        headers=headers,
    )
    assert res_post.status_code == 201

    projects = client.get("/projects", headers=headers).json()
    proj_id = projects[0]["id"]

    res_get = client.get(f"/projects/{proj_id}", headers=headers)
    assert res_get.status_code == 200
    assert res_get.json()["id"] == proj_id

    # Unknown ID returns 404
    res_404 = client.get("/projects/999999", headers=headers)
    assert res_404.status_code == 404


def test_project_branches_filtering_and_pagination(client: TestClient, user_factory):
    """GET /projects/{project_id}/branches supports search query 'q' and pagination."""
    user, api_key = user_factory(username="branchfilteruser")
    headers = {"X-API-Key": api_key}

    branches = ["main", "feature-login", "feature-signup", "bugfix-typo"]
    for idx, b_name in enumerate(branches):
        client.post(
            "/events",
            json={
                "type": "commit",
                "project": "multi-branch-proj",
                "repo_path": "/path/multibranch",
                "branch": b_name,
                "timestamp": f"2026-10-10T10:0{idx}:00Z",
            },
            headers=headers,
        )

    projects = client.get("/projects", headers=headers).json()
    proj_id = projects[0]["id"]

    # Search with q='feature'
    res_q = client.get(f"/projects/{proj_id}/branches?q=feature", headers=headers)
    assert res_q.status_code == 200
    q_branches = res_q.json()
    assert len(q_branches) == 2
    assert all("feature" in b["name"] for b in q_branches)

    # Pagination: limit=2
    res_paged = client.get(f"/projects/{proj_id}/branches?limit=2&offset=0", headers=headers)
    assert res_paged.status_code == 200
    assert len(res_paged.json()) == 2


def test_branch_events_timeline(client: TestClient, user_factory):
    """GET /branches/{branch_id}/events returns event history newest first with pagination."""
    user, api_key = user_factory(username="eventshistoryuser")
    headers = {"X-API-Key": api_key}

    for i in range(5):
        client.post(
            "/events",
            json={
                "type": "commit",
                "project": "timeline-proj",
                "repo_path": "/path/timeline",
                "branch": "main",
                "commit_hash": f"hash{i}",
                "message": f"commit number {i}",
                "timestamp": f"2026-10-10T10:0{i}:00Z",
            },
            headers=headers,
        )

    projects = client.get("/projects", headers=headers).json()
    proj_id = projects[0]["id"]
    branches = client.get(f"/projects/{proj_id}/branches", headers=headers).json()
    branch_id = branches[0]["id"]

    res_events = client.get(f"/branches/{branch_id}/events?limit=3", headers=headers)
    assert res_events.status_code == 200
    events = res_events.json()
    assert len(events) == 3
    # Newest first
    assert events[0]["commit_hash"] == "hash4"
    assert events[1]["commit_hash"] == "hash3"
    assert events[2]["commit_hash"] == "hash2"


def test_multi_user_isolation(client: TestClient, user_factory):
    """
    User A cannot view or write into User B's projects.
    The same repository name/path creates two distinct isolated projects.
    Accessing another user's project/branch returns 404 (not 403).
    """
    user_a, key_a = user_factory(username="user-a")
    user_b, key_b = user_factory(username="user-b")

    common_payload = {
        "type": "commit",
        "project": "shared-repo-name",
        "repo_path": "C:/Projects/shared-repo",
        "branch": "main",
        "timestamp": "2026-10-10T12:00:00Z",
    }

    # User A creates the project
    res_a = client.post("/events", json=common_payload, headers={"X-API-Key": key_a})
    assert res_a.status_code == 201

    # User B creates project with same repo_path
    res_b = client.post("/events", json=common_payload, headers={"X-API-Key": key_b})
    assert res_b.status_code == 201

    # Check User A's projects
    projects_a = client.get("/projects", headers={"X-API-Key": key_a}).json()
    assert len(projects_a) == 1
    proj_id_a = projects_a[0]["id"]

    # Check User B's projects
    projects_b = client.get("/projects", headers={"X-API-Key": key_b}).json()
    assert len(projects_b) == 1
    proj_id_b = projects_b[0]["id"]

    # IDs must be separate projects
    assert proj_id_a != proj_id_b

    # User A attempting to access User B's project receives 404 (anti-probing)
    res_cross_project = client.get(f"/projects/{proj_id_b}", headers={"X-API-Key": key_a})
    assert res_cross_project.status_code == 404

    # User A attempting to access User B's branches receives 404
    res_cross_branches = client.get(f"/projects/{proj_id_b}/branches", headers={"X-API-Key": key_a})
    assert res_cross_branches.status_code == 404

    # User A attempting to access User B's branch events receives 404
    branches_b = client.get(f"/projects/{proj_id_b}/branches", headers={"X-API-Key": key_b}).json()
    branch_id_b = branches_b[0]["id"]
    res_cross_events = client.get(f"/branches/{branch_id_b}/events", headers={"X-API-Key": key_a})
    assert res_cross_events.status_code == 404
