def test_health_reports_application_status(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_registration_login_and_authenticated_profile(client):
    registration = client.post(
        "/api/auth/register",
        json={"email": "dev@example.com", "password": "a-long-test-password"},
    )
    assert registration.status_code == 201
    assert registration.json()["email"] == "dev@example.com"
    assert "password" not in registration.json()
    assert "password_hash" not in registration.json()

    login = client.post(
        "/api/auth/token",
        data={"username": "dev@example.com", "password": "a-long-test-password"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    profile = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert profile.status_code == 200
    assert profile.json()["email"] == "dev@example.com"


def test_duplicate_account_is_rejected(client):
    payload = {"email": "dev@example.com", "password": "a-long-test-password"}
    assert client.post("/api/auth/register", json=payload).status_code == 201
    duplicate = client.post("/api/auth/register", json=payload)
    assert duplicate.status_code == 409


def test_assistant_requires_authentication(client):
    response = client.post("/api/assistant/chat", json={"message": "Hello"})

    assert response.status_code == 401
