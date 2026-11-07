from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import json

from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.lifeos.schemas import TaskCreate, TaskUpdate
from app.modules.lifeos.service import (
    create_task as lifeos_create_task,
    list_tasks as lifeos_list_tasks,
    update_task as lifeos_update_task,
)


@dataclass
class ToolContext:
    user: User | None = None
    db: Session | None = None


ToolHandler = Callable[[dict[str, object], ToolContext], str]


def _local_date(_: dict[str, object], __: ToolContext) -> str:
    now = datetime.now().astimezone()
    return now.strftime("%A, %B %d, %Y %H:%M %Z")


def _list_tasks(arguments: dict[str, object], context: ToolContext) -> str:
    if not context.user or not context.db:
        return "Authentication or database session is missing."

    status = str(arguments["status"]) if "status" in arguments and arguments["status"] else None
    search = str(arguments["search"]) if "search" in arguments and arguments["search"] else None

    tasks = lifeos_list_tasks(context.db, context.user.id, status=status, search=search, limit=20)
    if not tasks:
        return "No tasks found."

    results = []
    for t in tasks:
        due = t.due_date.isoformat() if t.due_date else "none"
        results.append(
            f"ID {t.id}: [{t.status.upper()}] '{t.title}' (Priority: {t.priority}, Due: {due})"
        )
    return "\n".join(results)


def _create_task(arguments: dict[str, object], context: ToolContext) -> str:
    if not context.user or not context.db:
        return "Authentication or database session is missing."

    title = str(arguments.get("title", "")).strip()
    if not title:
        return "Task title is required."

    description = str(arguments.get("description", "")) if arguments.get("description") else None
    priority = str(arguments.get("priority", "medium")).lower()
    if priority not in ("low", "medium", "high", "urgent"):
        priority = "medium"

    due_date = None
    if arguments.get("due_date"):
        try:
            due_date = datetime.fromisoformat(str(arguments["due_date"]))
        except ValueError:
            pass

    tags: list[str] = []
    raw_tags = arguments.get("tags")
    if isinstance(raw_tags, list):
        tags = [str(x) for x in raw_tags]
    elif isinstance(raw_tags, str):
        tags = [x.strip() for x in raw_tags.split(",") if x.strip()]

    task = lifeos_create_task(
        context.db,
        context.user.id,
        TaskCreate(
            title=title,
            description=description,
            priority=priority,
            due_date=due_date,
            tags=tags,
        ),
    )
    return f"Created task ID {task.id}: '{task.title}' with priority '{task.priority}'."


def _complete_task(arguments: dict[str, object], context: ToolContext) -> str:
    if not context.user or not context.db:
        return "Authentication or database session is missing."

    task_id = arguments.get("task_id")
    if task_id is None:
        return "task_id is required."

    try:
        task_id_int = int(task_id)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return "Invalid task_id."

    task = lifeos_update_task(
        context.db,
        context.user.id,
        task_id_int,
        TaskUpdate(status="completed"),
    )
    if not task:
        return f"Task ID {task_id_int} not found."
    return f"Marked task ID {task.id} ('{task.title}') as completed."


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_server_date",
            "description": "Get the current date and time on the application server.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_my_tasks",
            "description": "List the authenticated user's tasks with optional status or keyword filter.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Filter by status: 'pending', 'in_progress', or 'completed'",
                        "enum": ["pending", "in_progress", "completed"],
                    },
                    "search": {
                        "type": "string",
                        "description": "Search keyword matching task title or description",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "Create a new task in LifeOS for the current user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Title of the task"},
                    "description": {"type": "string", "description": "Optional notes or details"},
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "urgent"],
                        "description": "Priority level of the task",
                    },
                    "due_date": {
                        "type": "string",
                        "description": "ISO 8601 formatted due date/time, e.g. 2026-11-08T17:00:00Z",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of tags or categories",
                    },
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": "Mark a task as completed in LifeOS.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer", "description": "The ID of the task to complete"},
                },
                "required": ["task_id"],
            },
        },
    },
]

TOOL_HANDLERS: dict[str, ToolHandler] = {
    "get_server_date": _local_date,
    "list_my_tasks": _list_tasks,
    "create_task": _create_task,
    "complete_task": _complete_task,
}


def run_tool(name: str, arguments: dict[str, object], context: ToolContext | None = None) -> str:
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return "Tool is not available."
    ctx = context or ToolContext()
    return handler(arguments, ctx)
