import asyncio
import json
from types import SimpleNamespace

from app.core.config import settings
from app.modules.assistant import tools
from app.modules.assistant.schemas import ChatRequest
from app.modules.assistant import service as assistant_service
from app.modules.assistant.tools import ToolContext
from app.modules.screen_assistant import service as screen_service
from app.modules.screen_assistant.service import ScreenInspection


def test_overlay_foreground_uses_visible_app_window_for_capture():
    selected = screen_service._select_capture_window(
        foreground_hwnd=100,
        foreground_title="V.I.P.E.R. - Personal Assistant",
        visible_windows=[
            (100, "V.I.P.E.R. - Personal Assistant"),
            (200, "main.py - Visual Studio Code"),
            (300, "Desktop"),
        ],
    )

    assert selected == 200


def test_non_overlay_foreground_remains_capture_target():
    selected = screen_service._select_capture_window(
        foreground_hwnd=200,
        foreground_title="main.py - Visual Studio Code",
        visible_windows=[(200, "main.py - Visual Studio Code")],
    )

    assert selected == 200


def test_screen_privacy_exclusions_match_app_and_window_title(monkeypatch):
    monkeypatch.setattr(settings, "screen_blocked_apps", "1password,authenticator")
    monkeypatch.setattr(settings, "screen_blocked_keywords", "password,otp,login")

    assert screen_service._privacy_block_reason("1Password.exe", "Vault") is not None
    assert screen_service._privacy_block_reason("chrome.exe", "Login - Example") is not None
    assert screen_service._privacy_block_reason("chrome.exe", "Documentation") is None


def test_desktop_actions_require_a_fresh_screen_read_and_post_action_check(monkeypatch):
    calls = []

    async def inspect():
        return ScreenInspection(
            available=True,
            app_name="chrome.exe",
            window_title="Example tab",
            description="A browser window is visible.",
            captured_at="2026-11-14T09:00:00+05:30",
        )

    def open_app(arguments, _context):
        calls.append(arguments["app_name"])
        return "Opened Notepad."

    monkeypatch.setattr(tools, "inspect_current_screen", inspect)
    monkeypatch.setitem(tools.TOOL_HANDLERS, "open_desktop_app", open_app)
    context = ToolContext()

    blocked = asyncio.run(tools.run_tool_async("open_desktop_app", {"app_name": "Notepad"}, context))
    assert "Inspect the current screen" in blocked
    assert calls == []

    asyncio.run(tools.run_tool_async("inspect_current_screen", {}, context))
    assert context.screen_preflight_complete is True

    result = asyncio.run(tools.run_tool_async("open_desktop_app", {"app_name": "Notepad"}, context))
    assert result == "Opened Notepad."
    assert context.screen_verification_pending is True
    assert calls == ["Notepad"]

    blocked = asyncio.run(tools.run_tool_async("open_desktop_app", {"app_name": "Calculator"}, context))
    assert "verify the previous action" in blocked
    assert calls == ["Notepad"]

    asyncio.run(tools.run_tool_async("inspect_current_screen", {}, context))
    assert context.screen_verification_pending is False
    assert context.screen_preflight_complete is False


def test_unavailable_screen_read_does_not_authorize_actions(monkeypatch):
    async def inspect():
        return ScreenInspection(
            available=False,
            reason="Screen inspection skipped because the active window matches a privacy exclusion. No screenshot was taken.",
        )

    monkeypatch.setattr(tools, "inspect_current_screen", inspect)
    context = ToolContext()

    asyncio.run(tools.run_tool_async("inspect_current_screen", {}, context))
    result = asyncio.run(tools.run_tool_async("open_desktop_app", {"app_name": "Notepad"}, context))

    assert context.screen_preflight_complete is False
    assert "No app or tab action was performed" in result


def test_close_tool_requires_confirmation_from_the_viper_flow(monkeypatch):
    calls = []

    def close_app(*args, **kwargs):
        calls.append((args, kwargs))
        return True, "Windows requested the app close."

    monkeypatch.setattr(tools, "close_app_window_status", close_app)
    arguments = {"target": "Notepad", "kind": "app", "confirmed": True}
    unconfirmed_context = ToolContext(screen_preflight_complete=True)

    refused = asyncio.run(tools.run_tool_async("close_target", arguments, unconfirmed_context))
    assert "not confirmed" in refused
    assert calls == []

    confirmed_context = ToolContext(
        screen_preflight_complete=True,
        close_confirmation_allowed=True,
    )
    result = asyncio.run(tools.run_tool_async("close_target", arguments, confirmed_context))
    assert result == "Windows requested the app close."
    assert confirmed_context.screen_verification_pending is True
    assert len(calls) == 1


def test_chat_runs_screen_read_before_and_after_app_action(monkeypatch):
    class FakeMessage:
        def __init__(self, tool_name=None, arguments=None, content=None):
            self.content = content
            self.tool_calls = None
            self._dump = {"role": "assistant", "content": content}
            if tool_name:
                self.tool_calls = [
                    SimpleNamespace(
                        id=f"call-{tool_name}",
                        function=SimpleNamespace(
                            name=tool_name,
                            arguments=json.dumps(arguments or {}),
                        ),
                    )
                ]
                self._dump["tool_calls"] = [
                    {
                        "id": f"call-{tool_name}",
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": json.dumps(arguments or {}),
                        },
                    }
                ]

        def model_dump(self, exclude_none=False):
            return self._dump

    responses = [
        FakeMessage("inspect_current_screen"),
        FakeMessage("open_desktop_app", {"app_name": "Notepad"}),
        FakeMessage("inspect_current_screen"),
        FakeMessage(content="Notepad is open and visible."),
    ]

    class FakeClient:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=self.create_completion),
            )

        async def create_completion(self, **_kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=responses.pop(0))])

        async def close(self):
            pass

    async def inspect():
        return ScreenInspection(
            available=True,
            app_name="notepad.exe",
            window_title="Untitled - Notepad",
            description="Notepad is visible.",
            captured_at="2026-11-14T09:00:00+05:30",
        )

    monkeypatch.setattr(assistant_service, "AsyncOpenAI", FakeClient)
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(tools, "inspect_current_screen", inspect)
    monkeypatch.setitem(tools.TOOL_HANDLERS, "open_desktop_app", lambda _args, _ctx: "Opened Notepad.")

    result = asyncio.run(assistant_service.reply_to_chat(ChatRequest(message="Open Notepad")))

    assert result.reply == "Notepad is open and visible."
    assert result.used_tools == [
        "inspect_current_screen",
        "open_desktop_app",
        "inspect_current_screen",
    ]


def test_direct_screen_read_is_inspected_before_calling_the_chat_model(monkeypatch):
    async def inspect():
        return ScreenInspection(
            available=True,
            app_name="notepad.exe",
            window_title="Untitled - Notepad",
            description="A blank Notepad document is visible.",
            captured_at="2026-11-14T09:00:00+05:30",
        )

    def unexpected_client(**_kwargs):
        raise AssertionError("A direct screen read should return the vision observation directly.")

    monkeypatch.setattr(assistant_service, "AsyncOpenAI", unexpected_client)
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(tools, "inspect_current_screen", inspect)

    result = asyncio.run(
        assistant_service.reply_to_chat(ChatRequest(message="Can you read my screen?"))
    )

    assert "Active application: notepad.exe" in result.reply
    assert "A blank Notepad document is visible." in result.reply
    assert result.used_tools == ["inspect_current_screen"]


def test_direct_screen_read_reports_privacy_block_without_calling_chat_model(monkeypatch):
    async def inspect():
        return ScreenInspection(
            available=False,
            reason="Screen inspection skipped because the active window matches a privacy exclusion. No screenshot was taken.",
        )

    def unexpected_client(**_kwargs):
        raise AssertionError("Chat model should not be called when screen inspection is blocked.")

    monkeypatch.setattr(assistant_service, "AsyncOpenAI", unexpected_client)
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(tools, "inspect_current_screen", inspect)

    result = asyncio.run(
        assistant_service.reply_to_chat(ChatRequest(message="Please read my screen"))
    )

    assert "No screenshot was taken" in result.reply
    assert result.used_tools == ["inspect_current_screen"]


def test_viper_screen_guidance_does_not_trigger_capture_for_other_commands(monkeypatch):
    class FakeClient:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=self.create_completion),
            )

        async def create_completion(self, **_kwargs):
            message = SimpleNamespace(content="I can help close ChatGPT.", tool_calls=None)
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

        async def close(self):
            pass

    async def unexpected_inspection():
        raise AssertionError("A non-screen request must not capture the screen.")

    monkeypatch.setattr(assistant_service, "AsyncOpenAI", FakeClient)
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(tools, "inspect_current_screen", unexpected_inspection)

    result = asyncio.run(
        assistant_service.reply_to_chat(
            ChatRequest(
                message=(
                    "When asked to read or describe the screen, use the screen observation. "
                    "Current user turn: Close ChatGPT app"
                )
            ),
            context=ToolContext(screen_read_requested=False),
        )
    )

    assert result.reply == "I can help close ChatGPT."
    assert result.used_tools == []
