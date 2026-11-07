from collections.abc import Callable
from datetime import datetime

from app.core.config import settings

ToolHandler = Callable[[dict[str, object]], str]


def _local_date(_: dict[str, object]) -> str:
    # The client's local date/time should be used for scheduling. This is only a server clock utility.
    now = datetime.now().astimezone()
    return now.strftime("%A, %B %d, %Y %H:%M %Z")


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_server_date",
            "description": "Get the current date and time on the application server. This is not the user's local time zone.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    }
]

TOOL_HANDLERS: dict[str, ToolHandler] = {"get_server_date": _local_date}


def run_tool(name: str, arguments: dict[str, object]) -> str:
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return "Tool is not available."
    return handler(arguments)
