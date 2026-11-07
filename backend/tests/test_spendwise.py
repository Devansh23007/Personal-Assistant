from datetime import date, timedelta

from app.core.database import get_db
from app.modules.assistant.tools import ToolContext, run_tool
from app.modules.auth.models import User


def _get_auth_headers(client, email="spend_user@example.com", password="a-strong-password-123"):
    client.post("/api/auth/register", json={"email": email, "password": password})
    res = client.post("/api/auth/token", data={"username": email, "password": password})
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_spendwise_summary_and_seeding(client):
    headers = _get_auth_headers(client, "spend1@example.com")

    summary_res = client.get("/api/spendwise/summary", headers=headers)
    assert summary_res.status_code == 200
    summary = summary_res.json()
    assert summary["total_income"] >= 4000.0
    assert summary["total_expenses"] > 0.0
    assert summary["net_savings"] > 0.0
    assert "Food & Dining" in summary["category_breakdown"]


def test_create_and_filter_transactions(client):
    headers = _get_auth_headers(client, "spend2@example.com")

    # Add transaction
    create_res = client.post(
        "/api/spendwise/transactions",
        headers=headers,
        json={
            "amount": 65.50,
            "type": "expense",
            "category": "Healthcare",
            "description": "Pharmacy Prescription",
            "payment_method": "Credit Card",
            "tags": ["medicine", "health"],
        },
    )
    assert create_res.status_code == 201
    tx = create_res.json()
    assert tx["amount"] == 65.50
    assert tx["category"] == "Healthcare"
    assert "medicine" in tx["tags"]

    # Filter by category
    filter_res = client.get("/api/spendwise/transactions?category=Healthcare", headers=headers)
    assert filter_res.status_code == 200
    txs = filter_res.json()
    assert len(txs) == 1
    assert txs[0]["description"] == "Pharmacy Prescription"

    # Search
    search_res = client.get("/api/spendwise/transactions?search=Prescription", headers=headers)
    assert search_res.status_code == 200
    assert len(search_res.json()) == 1


def test_update_and_delete_transaction(client):
    headers = _get_auth_headers(client, "spend3@example.com")

    create_res = client.post(
        "/api/spendwise/transactions",
        headers=headers,
        json={
            "amount": 25.00,
            "type": "expense",
            "category": "Food & Dining",
            "description": "Lunch with colleague",
        },
    )
    tx_id = create_res.json()["id"]

    # Update
    patch_res = client.patch(
        f"/api/spendwise/transactions/{tx_id}",
        headers=headers,
        json={"amount": 28.50, "description": "Team lunch"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["amount"] == 28.50
    assert patch_res.json()["description"] == "Team lunch"

    # Delete
    del_res = client.delete(f"/api/spendwise/transactions/{tx_id}", headers=headers)
    assert del_res.status_code == 204

    # Get should 404
    assert client.get(f"/api/spendwise/transactions/{tx_id}", headers=headers).status_code == 404


def test_import_csv(client):
    headers = _get_auth_headers(client, "spend_csv@example.com")

    csv_data = (
        "Date,Description,Amount,Category,Type,Payment Method\n"
        "2026-11-01,Client Consulting Payment,1500.00,Income,credit,Bank Transfer\n"
        "2026-11-02,Coworking Space Pass,45.00,Work,debit,Card\n"
        "2026-11-03,Office Supplies,32.40,Shopping,expense,Card\n"
    )

    res = client.post(
        "/api/spendwise/transactions/import-csv",
        headers={**headers, "Content-Type": "text/plain"},
        content=csv_data,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["imported_count"] == 3
    assert data["error_count"] == 0

    # Verify transactions are in the list
    txs = client.get("/api/spendwise/transactions", headers=headers).json()
    descriptions = [t["description"] for t in txs]
    assert "Client Consulting Payment" in descriptions
    assert "Coworking Space Pass" in descriptions


def test_budgets_tracking(client):
    headers = _get_auth_headers(client, "spend_budget@example.com")
    current_month = date.today().strftime("%Y-%m")

    # Add an expense
    client.post(
        "/api/spendwise/transactions",
        headers=headers,
        json={
            "amount": 120.00,
            "type": "expense",
            "category": "Electronics",
            "description": "USB-C Monitor Cable",
        },
    )

    # Set budget for Electronics
    budget_res = client.post(
        "/api/spendwise/budgets",
        headers=headers,
        json={
            "category": "Electronics",
            "monthly_limit": 200.00,
            "month": current_month,
        },
    )
    assert budget_res.status_code == 201
    budget = budget_res.json()
    assert budget["spent"] == 120.00
    assert budget["remaining"] == 80.00
    assert budget["percentage_used"] == 60.0

    # Delete budget
    del_res = client.delete(f"/api/spendwise/budgets/{budget['id']}", headers=headers)
    assert del_res.status_code == 204


def test_user_isolation_spendwise(client):
    headers_u1 = _get_auth_headers(client, "spend_u1@example.com")
    headers_u2 = _get_auth_headers(client, "spend_u2@example.com")

    create_res = client.post(
        "/api/spendwise/transactions",
        headers=headers_u1,
        json={"amount": 500.0, "description": "Secret Transfer", "category": "Other"},
    )
    tx_id = create_res.json()["id"]

    # User 2 cannot access user 1's transaction
    assert client.get(f"/api/spendwise/transactions/{tx_id}", headers=headers_u2).status_code == 404
    assert client.delete(f"/api/spendwise/transactions/{tx_id}", headers=headers_u2).status_code == 404


def test_spendwise_tools_direct(client):
    _get_auth_headers(client, "spend_tool_user@example.com")
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        user = db.query(User).filter(User.email == "spend_tool_user@example.com").first()
        ctx = ToolContext(user=user, db=db)

        # 1. Log expense tool
        log_res = run_tool("log_expense", {"amount": 55.00, "description": "Dinner at Thai bistro", "category": "Food & Dining"}, ctx)
        assert "Logged expense of $55.00" in log_res

        # 2. Spending summary tool
        summary_res = run_tool("get_spending_summary", {}, ctx)
        assert "Spending Summary for" in summary_res
        assert "Total Expenses:" in summary_res

        # 3. Budget status tool
        budget_status = run_tool("check_budget_status", {}, ctx)
        assert "Budget Status for" in budget_status
    finally:
        db.close()
