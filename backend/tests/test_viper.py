import pytest


def test_viper_telemetry_endpoint(client):
    response = client.get("/api/viper/telemetry")
    assert response.status_code == 200
    data = response.json()
    assert "memory_percent" in data
    assert "status" in data
    assert data["status"] == "all systems nominal"
    assert "hostname" in data


def test_viper_system_diagnostics_command(client):
    response = client.post(
        "/api/viper/command",
        json={"message": "viper run system diagnostics", "voice_mode": False},
    )
    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
    assert "systems nominal" in data["reply"].lower()
    assert data["system_status"] is not None


def test_viper_time_command(client):
    response = client.post(
        "/api/viper/command",
        json={"message": "Hey Viper, what time is it?", "voice_mode": True},
    )
    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
    assert "currently" in data["reply"].lower()


def test_viper_take_note_and_read(client):
    note_resp = client.post(
        "/api/viper/command",
        json={"message": "Viper take note meeting with Stark Industries at 3 PM"},
    )
    assert note_resp.status_code == 200
    assert "noted" in note_resp.json()["reply"].lower()

    read_resp = client.post(
        "/api/viper/command",
        json={"message": "Viper read notes"},
    )
    assert read_resp.status_code == 200
    assert "Stark Industries" in read_resp.json()["reply"]


def test_viper_direct_action_trigger(client):
    response = client.post(
        "/api/viper/action",
        json={"action": "take_note", "target": "Diagnostic check passed."},
    )
    assert response.status_code == 200
    assert response.json()["success"] is True


@pytest.mark.parametrize("message", ["open Chrome", "close current tab", "Read my screen"])
def test_screen_dependent_commands_use_assistant_tool_flow(client, monkeypatch, message):
    from app.modules.viper import service as viper_service
    from app.modules.viper.schemas import ViperCommandResponse

    async def screen_aware_response(cleaned, user, db, history, telemetry):
        return ViperCommandResponse(
            reply="Handled through screen-aware tools.",
            action_taken="screen-aware",
            audio_text="Handled through screen-aware tools.",
            system_status=telemetry,
        )

    monkeypatch.setattr(viper_service, "_respond_with_conversation", screen_aware_response)
    response = client.post("/api/viper/command", json={"message": message})

    assert response.status_code == 200
    assert response.json()["action_taken"] == "screen-aware"


@pytest.mark.parametrize(
    ("message", "expected_screen_read"),
    [("Read my screen", True), ("close ChatGPT app", False)],
)
def test_viper_only_marks_explicit_screen_read_requests(
    client,
    monkeypatch,
    message,
    expected_screen_read,
):
    from app.modules.viper import service as viper_service
    from app.modules.assistant.schemas import ChatResponse

    read_flags = []

    async def fake_reply(_request, context):
        read_flags.append(context.screen_read_requested)
        return ChatResponse(reply="Handled.", used_tools=[])

    monkeypatch.setattr(viper_service, "reply_to_chat", fake_reply)
    response = client.post("/api/viper/command", json={"message": message})

    assert response.status_code == 200
    assert read_flags == [expected_screen_read]


def test_close_confirmation_is_forwarded_only_after_a_pending_request(client, monkeypatch):
    from app.modules.viper import service as viper_service
    from app.modules.viper.schemas import ViperCommandResponse

    confirmation_values = []

    async def screen_aware_response(
        cleaned,
        user,
        db,
        history,
        telemetry,
        close_confirmation_allowed=False,
    ):
        confirmation_values.append(close_confirmation_allowed)
        return ViperCommandResponse(
            reply="Handled through screen-aware tools.",
            action_taken="screen-aware",
            audio_text="Handled through screen-aware tools.",
            system_status=telemetry,
        )

    monkeypatch.setattr(viper_service, "_respond_with_conversation", screen_aware_response)
    response = client.post(
        "/api/viper/command",
        json={
            "message": "yes",
            "history": [
                {"role": "user", "content": "close current tab"},
                {"role": "assistant", "content": "Should I close the current tab? Say yes to confirm."},
            ],
        },
    )

    assert response.status_code == 200
    assert confirmation_values == [True]
