from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
import json

from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.docuvault.service import (
    search_documents_rag as docuvault_search_rag,
    seed_demo_documents_if_empty as docuvault_seed_demo,
)
from app.modules.inboxzero.service import (
    generate_draft_reply as inboxzero_generate_draft_reply,
    get_or_create_account as inboxzero_get_or_create_account,
    list_drafts as inboxzero_list_drafts,
    list_messages as inboxzero_list_messages,
    seed_demo_inbox_if_empty as inboxzero_seed_demo,
)
from app.modules.learnloop.service import (
    generate_deck_from_document as learnloop_generate_deck,
    list_cards_for_deck as learnloop_list_cards,
    list_decks_with_stats as learnloop_list_decks,
    seed_demo_deck_if_empty as learnloop_seed_demo,
)
from app.modules.lifeos.schemas import TaskCreate, TaskUpdate
from app.modules.lifeos.service import (
    create_task as lifeos_create_task,
    list_tasks as lifeos_list_tasks,
    update_task as lifeos_update_task,
)
from app.modules.spendwise.schemas import TransactionCreate
from app.modules.spendwise.service import (
    create_transaction as spendwise_create_tx,
    get_spend_summary as spendwise_get_summary,
    list_budgets_with_progress as spendwise_list_budgets,
    seed_demo_transactions_if_empty as spendwise_seed_demo,
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


# --- SpendWise Tools ---
def _log_expense(arguments: dict[str, object], context: ToolContext) -> str:
    if not context.user or not context.db:
        return "Authentication or database session is missing."
    amount = arguments.get("amount")
    if amount is None:
        return "Amount is required."
    try:
        amt_float = float(amount)  # type: ignore[arg-type]
        if amt_float <= 0:
            return "Amount must be greater than zero."
    except (ValueError, TypeError):
        return "Invalid amount."

    description = str(arguments.get("description", "")).strip()
    if not description:
        return "Description is required."

    category = str(arguments.get("category", "Other")).strip() or "Other"
    payment_method = str(arguments.get("payment_method", "Credit Card")).strip() or "Credit Card"

    tx = spendwise_create_tx(
        context.db,
        context.user.id,
        TransactionCreate(
            amount=amt_float,
            type="expense",
            category=category,
            description=description,
            payment_method=payment_method,
        ),
    )
    return (
        f"Logged expense of ${tx.amount:.2f} for '{tx.description}' in '{tx.category}' "
        f"via {tx.payment_method} (ID: {tx.id})."
    )


def _get_spending_summary(arguments: dict[str, object], context: ToolContext) -> str:
    if not context.user or not context.db:
        return "Authentication or database session is missing."
    month = str(arguments["month"]).strip() if "month" in arguments and arguments["month"] else None
    spendwise_seed_demo(context.db, context.user.id)
    summary = spendwise_get_summary(context.db, context.user.id, month=month)

    lines = [
        f"Spending Summary for {summary.month}:",
        f"- Total Income: ${summary.total_income:.2f}",
        f"- Total Expenses: ${summary.total_expenses:.2f}",
        f"- Net Savings: ${summary.net_savings:.2f} (Savings Rate: {summary.savings_rate}%)",
        "- Top Categories:",
    ]
    for tc in summary.top_categories:
        lines.append(f"  • {tc['category']}: ${float(tc['amount']):.2f}")
    if summary.over_budget_count > 0:
        lines.append(f"⚠️ Warning: You are over budget in {summary.over_budget_count} category/categories!")
    return "\n".join(lines)


def _check_budget_status(arguments: dict[str, object], context: ToolContext) -> str:
    if not context.user or not context.db:
        return "Authentication or database session is missing."
    month = str(arguments["month"]).strip() if "month" in arguments and arguments["month"] else None
    if not month:
        month = date.today().strftime("%Y-%m")
    spendwise_seed_demo(context.db, context.user.id)
    budgets = spendwise_list_budgets(context.db, context.user.id, month=month)
    if not budgets:
        return f"No budgets configured for {month}."

    lines = [f"Budget Status for {month}:"]
    for b in budgets:
        status_flag = (
            "🚨 OVER BUDGET"
            if b.spent > b.monthly_limit
            else "⚠️ Close to Limit"
            if b.percentage_used >= 80
            else "✅ On Track"
        )
        lines.append(
            f"- {b.category}: Spent ${b.spent:.2f} of ${b.monthly_limit:.2f} ({b.percentage_used}%) [{status_flag}]"
        )
    return "\n".join(lines)


# --- DocuVault Tools ---
def _search_documents(arguments: dict[str, object], context: ToolContext) -> str:
    if not context.user or not context.db:
        return "Authentication or database session is missing."
    query = str(arguments.get("query", "")).strip()
    if not query:
        return "Search query is required."
    docuvault_seed_demo(context.db, context.user.id)
    result = docuvault_search_rag(context.db, context.user.id, query=query, limit=4)
    if result.total_matches == 0:
        return f"No documents matched '{query}' in DocuVault."
    lines = [f"Found {result.total_matches} citation(s) in DocuVault for '{query}':"]
    for cit in result.citations:
        lines.append(f"- [Doc {cit.document_id}: {cit.title}]\n  Excerpt: {cit.snippet}")
    return "\n".join(lines)


# --- LearnLoop Tools ---
def _get_study_flashcards(arguments: dict[str, object], context: ToolContext) -> str:
    if not context.user or not context.db:
        return "Authentication or database session is missing."
    learnloop_seed_demo(context.db, context.user.id)
    decks = learnloop_list_decks(context.db, context.user.id)
    if not decks:
        return "No study decks found in LearnLoop."

    target_deck_id = arguments.get("deck_id")
    if target_deck_id:
        try:
            target_id = int(target_deck_id)  # type: ignore[arg-type]
            target_deck = next((d for d in decks if d.id == target_id), None)
        except (ValueError, TypeError):
            target_deck = decks[0]
    else:
        target_deck = decks[0]

    if not target_deck:
        return "Study deck not found."

    cards = learnloop_list_cards(context.db, context.user.id, target_deck.id, due_only=True)
    if not cards:
        cards = learnloop_list_cards(context.db, context.user.id, target_deck.id, due_only=False)

    lines = [f"Flashcards from '{target_deck.title}' ({len(cards)} card(s)):"]
    for i, c in enumerate(cards[:5], 1):
        lines.append(f"{i}. Q: {c.front}\n   A: {c.back} [Status: {c.status}]")
    return "\n".join(lines)


def _create_deck_from_document(arguments: dict[str, object], context: ToolContext) -> str:
    if not context.user or not context.db:
        return "Authentication or database session is missing."
    doc_id = arguments.get("document_id")
    if not doc_id:
        return "document_id is required."
    try:
        doc_id_int = int(doc_id)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return "Invalid document_id."

    deck = learnloop_generate_deck(context.db, context.user.id, doc_id_int)
    if not deck:
        return f"Document ID {doc_id_int} not found in DocuVault."
    return f"Created LearnLoop study deck '{deck.title}' (Deck ID {deck.id}) from document ID {doc_id_int}."


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
    {
        "type": "function",
        "function": {
            "name": "log_expense",
            "description": "Log an expense transaction in SpendWise with amount, description, and category.",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {"type": "number", "description": "The expense amount"},
                    "description": {"type": "string", "description": "Short description of what was purchased"},
                    "category": {
                        "type": "string",
                        "description": "Expense category (e.g. Food & Dining, Transportation, Shopping, Entertainment, Housing & Utilities, Healthcare, Other)",
                    },
                    "payment_method": {
                        "type": "string",
                        "description": "Payment method used (e.g. Credit Card, Debit Card, UPI, Cash)",
                    },
                },
                "required": ["amount", "description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_spending_summary",
            "description": "Get spending summary, savings rate, and category breakdown for a month in SpendWise.",
            "parameters": {
                "type": "object",
                "properties": {
                    "month": {
                        "type": "string",
                        "description": "Month in YYYY-MM format (e.g. 2026-11). Defaults to current month.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_budget_status",
            "description": "Check if user is on track or over budget in SpendWise.",
            "parameters": {
                "type": "object",
                "properties": {
                    "month": {
                        "type": "string",
                        "description": "Month in YYYY-MM format (e.g. 2026-11). Defaults to current month.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_documents",
            "description": "Search saved documents in DocuVault by keywords or concepts with source citations and text excerpts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query keywords or concepts"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_study_flashcards",
            "description": "Get study flashcards from LearnLoop for revision and active recall.",
            "parameters": {
                "type": "object",
                "properties": {
                    "deck_id": {"type": "integer", "description": "Optional study deck ID"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_deck_from_document",
            "description": "Generate a new study deck of revision flashcards from a document in DocuVault.",
            "parameters": {
                "type": "object",
                "properties": {
                    "document_id": {"type": "integer", "description": "DocuVault document ID to convert into flashcards"},
                },
                "required": ["document_id"],
            },
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
    "log_expense": _log_expense,
    "get_spending_summary": _get_spending_summary,
    "check_budget_status": _check_budget_status,
    "search_documents": _search_documents,
    "get_study_flashcards": _get_study_flashcards,
    "create_deck_from_document": _create_deck_from_document,
}


def run_tool(name: str, arguments: dict[str, object], context: ToolContext | None = None) -> str:
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return "Tool is not available."
    ctx = context or ToolContext()
    return handler(arguments, ctx)
