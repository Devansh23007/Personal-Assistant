from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import json

from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.inboxzero.service import (
    generate_draft_reply as inboxzero_generate_draft_reply,
    get_or_create_account as inboxzero_get_or_create_account,
    list_drafts as inboxzero_list_drafts,
    list_messages as inboxzero_list_messages,
    seed_demo_inbox_if_empty as inboxzero_seed_demo,
)
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


# --- Starter Tools ---
def _local_date(_: dict[str, object], __: ToolContext) -> str:
    now = datetime.now().astimezone()
    return now.strftime("%A, %B %d, %Y %H:%M %Z")


# --- LifeOS Tools ---
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


# --- InboxZero Tools ---
def _summarize_inbox(_: dict[str, object], context: ToolContext) -> str:
    if not context.user or not context.db:
        return "Authentication or database session is missing."
    account = inboxzero_get_or_create_account(context.db, context.user.id, context.user.email)
    inboxzero_seed_demo(context.db, context.user.id, account)
    unread = inboxzero_list_messages(context.db, context.user.id, is_read=False, limit=10)
    if not unread:
        return "Your inbox is clear! No unread messages."
    lines = [f"Found {len(unread)} unread message(s):"]
    for m in unread:
        cat_badge = f"[{m.category.upper()}]"
        lines.append(
            f"- ID {m.id} {cat_badge} from {m.sender_name or m.sender}: '{m.subject}'\n  Summary: {m.summary or m.snippet}"
        )
    return "\n".join(lines)


def _search_emails(arguments: dict[str, object], context: ToolContext) -> str:
    if not context.user or not context.db:
        return "Authentication or database session is missing."
    query = str(arguments.get("query", "")).strip()
    if not query:
        return "Search query is required."
    account = inboxzero_get_or_create_account(context.db, context.user.id, context.user.email)
    inboxzero_seed_demo(context.db, context.user.id, account)
    results = inboxzero_list_messages(context.db, context.user.id, search=query, limit=10)
    if not results:
        return f"No emails matched '{query}'."
    lines = [f"Found {len(results)} matching email(s):"]
    for m in results:
        status_label = "READ" if m.is_read else "UNREAD"
        lines.append(f"- ID {m.id} [{status_label}] from {m.sender}: '{m.subject}'")
    return "\n".join(lines)


def _draft_email_reply(arguments: dict[str, object], context: ToolContext) -> str:
    if not context.user or not context.db:
        return "Authentication or database session is missing."
    message_id = arguments.get("message_id")
    if not message_id:
        return "message_id is required."
    try:
        msg_id_int = int(message_id)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return "Invalid message_id."
    instructions = str(arguments.get("instructions", "Draft a polite and concise response."))
    try:
        draft = inboxzero_generate_draft_reply(context.db, context.user.id, msg_id_int, instructions=instructions)
        return (
            f"Created Draft ID {draft.id} for message ID {msg_id_int} to {draft.recipient}.\n"
            f"Subject: {draft.subject}\n"
            f"Status: awaiting_approval (Requires manual user review and approval in InboxZero before sending)."
        )
    except ValueError as err:
        return str(err)


def _list_pending_drafts(_: dict[str, object], context: ToolContext) -> str:
    if not context.user or not context.db:
        return "Authentication or database session is missing."
    drafts = inboxzero_list_drafts(context.db, context.user.id, status="awaiting_approval")
    if not drafts:
        return "No drafts currently awaiting approval."
    lines = [f"You have {len(drafts)} draft(s) awaiting approval:"]
    for d in drafts:
        lines.append(f"- Draft ID {d.id} to {d.recipient}: '{d.subject}'")
    return "\n".join(lines)


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
    {
        "type": "function",
        "function": {
            "name": "summarize_inbox",
            "description": "Summarize unread emails and highlight urgent or action-needed messages in InboxZero.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_emails",
            "description": "Search user's emails by sender or keyword in InboxZero.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keywords or sender to search for"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "draft_email_reply",
            "description": "Draft a response to an email in InboxZero. Note: Sending is gated by explicit user approval.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message_id": {"type": "integer", "description": "ID of the email to reply to"},
                    "instructions": {"type": "string", "description": "Optional tone or reply instructions"},
                },
                "required": ["message_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_pending_drafts",
            "description": "List all email drafts currently awaiting human review and approval.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

TOOL_HANDLERS: dict[str, ToolHandler] = {
    "get_server_date": _local_date,
    "list_my_tasks": _list_tasks,
    "create_task": _create_task,
    "complete_task": _complete_task,
    "summarize_inbox": _summarize_inbox,
    "search_emails": _search_emails,
    "draft_email_reply": _draft_email_reply,
    "list_pending_drafts": _list_pending_drafts,
}


def run_tool(name: str, arguments: dict[str, object], context: ToolContext | None = None) -> str:
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return "Tool is not available."
    ctx = context or ToolContext()
    return handler(arguments, ctx)
