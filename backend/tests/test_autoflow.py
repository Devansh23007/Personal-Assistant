from app.core.database import get_db
from app.modules.assistant.tools import ToolContext, run_tool
from app.modules.auth.models import User


def _get_auth_headers(client, email="flow_user@example.com", password="a-strong-password-123"):
    client.post("/api/auth/register", json={"email": email, "password": password})
    res = client.post("/api/auth/token", data={"username": email, "password": password})
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_autoflow_seeding_and_list(client):
    headers = _get_auth_headers(client, "flow_seed@example.com")
    res = client.get("/api/autoflow/workflows", headers=headers)
    assert res.status_code == 200
    wfs = res.json()
    assert len(wfs) >= 4
    names = [w["name"] for w in wfs]
    assert any("Morning Briefing" in n for n in names)
    assert any("Grocery Restock" in n for n in names)


def test_autoflow_crud(client):
    headers = _get_auth_headers(client, "flow_crud@example.com")

    # Create custom workflow
    create_res = client.post(
        "/api/autoflow/workflows",
        headers=headers,
        json={
            "name": "Custom Evening Shutdown",
            "description": "Reviews tasks completed today and clears pending drafts.",
            "trigger_type": "scheduled",
            "schedule_cron": "0 21 * * *",
            "is_active": True,
            "config": {"action": "evening_shutdown"},
        },
    )
    assert create_res.status_code == 201
    wf = create_res.json()
    assert wf["name"] == "Custom Evening Shutdown"
    wf_id = wf["id"]

    # Patch workflow
    patch_res = client.patch(
        f"/api/autoflow/workflows/{wf_id}",
        headers=headers,
        json={"is_active": False},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["is_active"] is False

    # Delete workflow
    del_res = client.delete(f"/api/autoflow/workflows/{wf_id}", headers=headers)
    assert del_res.status_code == 204


def test_autoflow_morning_briefing(client):
    headers = _get_auth_headers(client, "flow_briefing@example.com")
    res = client.get("/api/autoflow/briefing", headers=headers)
    assert res.status_code == 200
    briefing = res.json()
    assert "headline" in briefing
    assert "summary_markdown" in briefing
    assert len(briefing["summary_markdown"]) > 20


def test_autoflow_execution_and_approval_gate(client):
    headers = _get_auth_headers(client, "flow_exec@example.com")
    wfs = client.get("/api/autoflow/workflows", headers=headers).json()

    # Find Grocery Restock workflow (requires approval)
    restock_wf = next(w for w in wfs if "Grocery Restock" in w["name"])
    run_res = client.post(f"/api/autoflow/workflows/{restock_wf['id']}/run", headers=headers)
    assert run_res.status_code == 200
    run_data = run_res.json()
    assert run_data["requires_approval"] is True
    assert run_data["status"] == "pending_approval"
    run_id = run_data["id"]

    # Approve run
    approve_res = client.post(f"/api/autoflow/runs/{run_id}/approve", headers=headers)
    assert approve_res.status_code == 200
    approved_run = approve_res.json()
    assert approved_run["status"] == "completed"
    assert approved_run["approved_at"] is not None

    # Test rejection on a second run
    run_res_2 = client.post(f"/api/autoflow/workflows/{restock_wf['id']}/run", headers=headers)
    run_2_id = run_res_2.json()["id"]
    reject_res = client.post(f"/api/autoflow/runs/{run_2_id}/reject", headers=headers)
    assert reject_res.status_code == 200
    assert reject_res.json()["status"] == "rejected"


def test_autoflow_tools_direct(client):
    headers = _get_auth_headers(client, "flow_tools@example.com")
    db = next(client.app.dependency_overrides[get_db]())
    user = db.query(User).filter(User.email == "flow_tools@example.com").first()
    context = ToolContext(user=user, db=db)

    # 1. list_workflows tool
    list_out = run_tool("list_workflows", {}, context=context)
    assert "Configured Workflows" in list_out
    assert "Morning Briefing" in list_out

    # 2. get_morning_briefing tool
    brief_out = run_tool("get_morning_briefing", {}, context=context)
    assert "Good Morning" in brief_out

    # 3. trigger_workflow tool
    trigger_out = run_tool("trigger_workflow", {"workflow_name": "Morning Briefing"}, context=context)
    assert "Triggered workflow" in trigger_out
