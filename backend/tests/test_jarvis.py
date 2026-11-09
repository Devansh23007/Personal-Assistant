def test_jarvis_telemetry_endpoint(client):
    response = client.get("/api/jarvis/telemetry")
    assert response.status_code == 200
    data = response.json()
    assert "memory_percent" in data
    assert "status" in data
    assert data["status"] == "all systems nominal"
    assert "hostname" in data


def test_jarvis_system_diagnostics_command(client):
    response = client.post(
        "/api/jarvis/command",
        json={"message": "jarvis run system diagnostics", "voice_mode": False},
    )
    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
    assert "systems nominal" in data["reply"].lower()
    assert data["system_status"] is not None


def test_jarvis_time_command(client):
    response = client.post(
        "/api/jarvis/command",
        json={"message": "Hey Jarvis, what time is it?", "voice_mode": True},
    )
    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
    assert "currently" in data["reply"].lower()


def test_jarvis_take_note_and_read(client):
    note_resp = client.post(
        "/api/jarvis/command",
        json={"message": "Jarvis take note meeting with Stark Industries at 3 PM"},
    )
    assert note_resp.status_code == 200
    assert "noted" in note_resp.json()["reply"].lower()

    read_resp = client.post(
        "/api/jarvis/command",
        json={"message": "Jarvis read notes"},
    )
    assert read_resp.status_code == 200
    assert "Stark Industries" in read_resp.json()["reply"]


def test_jarvis_direct_action_trigger(client):
    response = client.post(
        "/api/jarvis/action",
        json={"action": "take_note", "target": "Diagnostic check passed."},
    )
    assert response.status_code == 200
    assert response.json()["success"] is True
