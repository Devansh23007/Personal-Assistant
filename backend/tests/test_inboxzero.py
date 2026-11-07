from app.core.database import get_db
from app.modules.assistant.tools import ToolContext, run_tool
from app.modules.auth.models import User


def _get_auth_headers(client, email="inbox_user@example.com", password="a-strong-password-123"):
    client.post("/api/auth/register", json={"email": email, "password": password})
    res = client.post("/api/auth/token", data={"username": email, "password": password})
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_inbox_stats_and_seeding(client):
    headers = _get_auth_headers(client, "inbox1@example.com")

    # Stats call should automatically seed demo inbox
    stats_res = client.get("/api/inboxzero/stats", headers=headers)
    assert stats_res.status_code == 200
    stats = stats_res.json()
    assert stats["total"] >= 4
    assert stats["unread"] >= 2
    assert stats["action_needed"] >= 1


def test_list_messages_and_filtering(client):
    headers = _get_auth_headers(client, "inbox2@example.com")

    # List all
    all_res = client.get("/api/inboxzero/messages", headers=headers)
    assert all_res.status_code == 200
    messages = all_res.json()
    assert len(messages) >= 4

    # Filter by category: action_needed
    action_res = client.get("/api/inboxzero/messages?category=action_needed", headers=headers)
    assert action_res.status_code == 200
    action_msgs = action_res.json()
    assert len(action_msgs) == 1
    assert "Strategy Deck" in action_msgs[0]["subject"]

    # Search keyword
    search_res = client.get("/api/inboxzero/messages?search=Airline", headers=headers)
    assert search_res.status_code == 200
    search_msgs = search_res.json()
    assert len(search_msgs) == 1
    assert "Flight Confirmation" in search_msgs[0]["subject"]


def test_update_message_read_and_archive(client):
    headers = _get_auth_headers(client, "inbox3@example.com")

    messages = client.get("/api/inboxzero/messages", headers=headers).json()
    msg_id = messages[0]["id"]

    # Mark as read
    patch_res = client.patch(f"/api/inboxzero/messages/{msg_id}", headers=headers, json={"is_read": True})
    assert patch_res.status_code == 200
    assert patch_res.json()["is_read"] is True

    # Archive
    arch_res = client.patch(f"/api/inboxzero/messages/{msg_id}", headers=headers, json={"is_archived": True})
    assert arch_res.status_code == 200
    assert arch_res.json()["is_archived"] is True

    # Active messages should now have 1 less
    active_msgs = client.get("/api/inboxzero/messages", headers=headers).json()
    assert len(active_msgs) == len(messages) - 1


def test_draft_reply_and_approval_gate(client):
    headers = _get_auth_headers(client, "inbox4@example.com")

    messages = client.get("/api/inboxzero/messages", headers=headers).json()
    msg_id = messages[0]["id"]

    # 1. Generate AI draft
    draft_res = client.post(
        f"/api/inboxzero/messages/{msg_id}/draft-reply",
        headers=headers,
        json={"instructions": "Draft a confirmation reply."},
    )
    assert draft_res.status_code == 201
    draft = draft_res.json()
    assert draft["id"] is not None
    assert draft["status"] == "awaiting_approval"
    assert "Re:" in draft["subject"]
    assert draft["sent_at"] is None

    draft_id = draft["id"]

    # 2. Check draft list
    drafts = client.get("/api/inboxzero/drafts", headers=headers).json()
    assert len(drafts) == 1

    # 3. Explicit Approval Gate: Send
    send_res = client.post(f"/api/inboxzero/drafts/{draft_id}/send", headers=headers)
    assert send_res.status_code == 200
    assert send_res.json()["status"] == "sent"
    assert send_res.json()["sent_at"] is not None


def test_user_isolation_inbox(client):
    headers_u1 = _get_auth_headers(client, "inbox_u1@example.com")
    headers_u2 = _get_auth_headers(client, "inbox_u2@example.com")

    # User 1 loads inbox
    msgs_u1 = client.get("/api/inboxzero/messages", headers=headers_u1).json()
    msg1_id = msgs_u1[0]["id"]

    # User 2 cannot access user 1 message
    assert client.get(f"/api/inboxzero/messages/{msg1_id}", headers=headers_u2).status_code == 404
    assert client.patch(f"/api/inboxzero/messages/{msg1_id}", headers=headers_u2, json={"is_read": True}).status_code == 404


def test_inboxzero_tools_direct(client):
    _get_auth_headers(client, "tool_user@example.com")
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        user = db.query(User).filter(User.email == "tool_user@example.com").first()
        ctx = ToolContext(user=user, db=db)

        # 1. Summarize inbox
        summary = run_tool("summarize_inbox", {}, ctx)
        assert "unread message" in summary

        # 2. Search emails
        search = run_tool("search_emails", {"query": "strategy"}, ctx)
        assert "Strategy" in search

        # 3. Draft reply tool
        # Find message id
        msg_id = int(search.split("ID ")[1].split(" ")[0])
        draft_msg = run_tool("draft_email_reply", {"message_id": msg_id}, ctx)
        assert "Created Draft ID" in draft_msg
        assert "awaiting_approval" in draft_msg

        # 4. List pending drafts
        pending = run_tool("list_pending_drafts", {}, ctx)
        assert "draft(s) awaiting approval" in pending
    finally:
        db.close()
