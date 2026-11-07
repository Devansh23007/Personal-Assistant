from datetime import datetime, timedelta, timezone

from app.core.database import SessionLocal, get_db
from app.modules.assistant.tools import ToolContext, run_tool
from app.modules.auth.models import User


def _get_auth_headers(client, email="user@example.com", password="a-strong-password-123"):
    client.post("/api/auth/register", json={"email": email, "password": password})
    res = client.post("/api/auth/token", data={"username": email, "password": password})
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_and_get_task(client):
    headers = _get_auth_headers(client, "alice@example.com")
    due = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()

    create_res = client.post(
        "/api/lifeos/tasks",
        headers=headers,
        json={
            "title": "Prepare weekly review",
            "description": "Collect metrics and notes",
            "priority": "high",
            "due_date": due,
            "timezone": "America/New_York",
            "tags": ["review", "planning"],
        },
    )
    assert create_res.status_code == 201
    task = create_res.json()
    assert task["id"] is not None
    assert task["title"] == "Prepare weekly review"
    assert task["priority"] == "high"
    assert task["status"] == "pending"
    assert task["timezone"] == "America/New_York"
    assert "review" in task["tags"]
    assert "planning" in task["tags"]

    task_id = task["id"]
    get_res = client.get(f"/api/lifeos/tasks/{task_id}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["title"] == "Prepare weekly review"


def test_list_tasks_and_filters(client):
    headers = _get_auth_headers(client, "bob@example.com")

    client.post(
        "/api/lifeos/tasks",
        headers=headers,
        json={"title": "Fix bug in payment flow", "priority": "urgent", "tags": ["code", "bug"]},
    )
    client.post(
        "/api/lifeos/tasks",
        headers=headers,
        json={"title": "Write documentation", "priority": "low", "tags": ["docs"]},
    )

    all_tasks = client.get("/api/lifeos/tasks", headers=headers).json()
    assert len(all_tasks) == 2

    # Filter by priority
    urgent_tasks = client.get("/api/lifeos/tasks?priority=urgent", headers=headers).json()
    assert len(urgent_tasks) == 1
    assert urgent_tasks[0]["title"] == "Fix bug in payment flow"

    # Search keyword
    doc_tasks = client.get("/api/lifeos/tasks?search=documentation", headers=headers).json()
    assert len(doc_tasks) == 1
    assert doc_tasks[0]["title"] == "Write documentation"


def test_update_task_and_completion(client):
    headers = _get_auth_headers(client, "carol@example.com")

    create_res = client.post(
        "/api/lifeos/tasks",
        headers=headers,
        json={"title": "Clean desktop", "priority": "medium"},
    )
    task_id = create_res.json()["id"]

    # Update title and mark in progress
    update_res = client.patch(
        f"/api/lifeos/tasks/{task_id}",
        headers=headers,
        json={"title": "Clean desktop workspace", "status": "in_progress"},
    )
    assert update_res.status_code == 200
    assert update_res.json()["title"] == "Clean desktop workspace"
    assert update_res.json()["status"] == "in_progress"
    assert update_res.json()["completed_at"] is None

    # Complete task
    complete_res = client.patch(
        f"/api/lifeos/tasks/{task_id}",
        headers=headers,
        json={"status": "completed"},
    )
    assert complete_res.status_code == 200
    assert complete_res.json()["status"] == "completed"
    assert complete_res.json()["completed_at"] is not None


def test_delete_task(client):
    headers = _get_auth_headers(client, "dave@example.com")

    create_res = client.post(
        "/api/lifeos/tasks",
        headers=headers,
        json={"title": "Temporary task"},
    )
    task_id = create_res.json()["id"]

    del_res = client.delete(f"/api/lifeos/tasks/{task_id}", headers=headers)
    assert del_res.status_code == 204

    # Verify not found
    get_res = client.get(f"/api/lifeos/tasks/{task_id}", headers=headers)
    assert get_res.status_code == 404


def test_user_task_isolation(client):
    headers_u1 = _get_auth_headers(client, "u1@example.com")
    headers_u2 = _get_auth_headers(client, "u2@example.com")

    create_res = client.post(
        "/api/lifeos/tasks",
        headers=headers_u1,
        json={"title": "User 1 Secret Task"},
    )
    task_id = create_res.json()["id"]

    # User 2 cannot get user 1's task
    get_res = client.get(f"/api/lifeos/tasks/{task_id}", headers=headers_u2)
    assert get_res.status_code == 404

    # User 2 list does not include user 1's task
    list_res = client.get("/api/lifeos/tasks", headers=headers_u2)
    assert len(list_res.json()) == 0

    # User 2 cannot update or delete user 1's task
    assert client.patch(f"/api/lifeos/tasks/{task_id}", headers=headers_u2, json={"title": "Hacked"}).status_code == 404
    assert client.delete(f"/api/lifeos/tasks/{task_id}", headers=headers_u2).status_code == 404


def test_task_summary(client):
    headers = _get_auth_headers(client, "eve@example.com")
    now = datetime.now(timezone.utc)

    # 1 overdue task
    client.post(
        "/api/lifeos/tasks",
        headers=headers,
        json={"title": "Overdue task", "due_date": (now - timedelta(days=2)).isoformat()},
    )
    # 1 today task
    client.post(
        "/api/lifeos/tasks",
        headers=headers,
        json={"title": "Today task", "due_date": (now + timedelta(hours=2)).isoformat()},
    )
    # 1 completed task
    completed_task = client.post(
        "/api/lifeos/tasks",
        headers=headers,
        json={"title": "Done task"},
    ).json()
    client.patch(f"/api/lifeos/tasks/{completed_task['id']}", headers=headers, json={"status": "completed"})

    summary = client.get("/api/lifeos/tasks/summary?timezone=UTC", headers=headers).json()
    assert summary["total"] == 3
    assert summary["completed"] == 1
    assert summary["pending"] == 2
    assert summary["overdue"] == 1
    assert summary["due_today"] >= 1


def test_lifeos_tools_direct(client):
    _get_auth_headers(client, "frank@example.com")
    # Grab db and user directly from test client overrides
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        user = db.query(User).filter(User.email == "frank@example.com").first()
        ctx = ToolContext(user=user, db=db)

        # 1. Create task tool
        msg = run_tool("create_task", {"title": "Assistant created task", "priority": "high"}, ctx)
        assert "Created task ID" in msg

        # 2. List tasks tool
        list_msg = run_tool("list_my_tasks", {}, ctx)
        assert "Assistant created task" in list_msg

        # 3. Complete task tool
        # Extract task ID
        task_id = int(list_msg.split("ID ")[1].split(":")[0])
        complete_msg = run_tool("complete_task", {"task_id": task_id}, ctx)
        assert "Marked task ID" in complete_msg
    finally:
        db.close()
