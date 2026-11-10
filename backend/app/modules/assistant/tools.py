from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
import json
import urllib.parse

from sqlalchemy.orm import Session

from app.core.app_launcher import (
    launch_desktop_app,
    navigate_current_browser_tab,
    open_url_with_preferred_browser,
)
from app.core.config import settings
from app.modules.auth.models import User
from app.modules.autoflow.service import (
    execute_workflow as autoflow_execute,
    get_morning_briefing as autoflow_get_briefing,
    list_workflows as autoflow_list,
    seed_demo_workflows_if_empty as autoflow_seed_demo,
)
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
from app.modules.mealmind.schemas import GroceryItemCreate
from app.modules.mealmind.service import (
    add_grocery_item as mealmind_add_grocery,
    get_grocery_summary as mealmind_get_grocery_summary,
    list_grocery_items as mealmind_list_grocery,
    list_meal_plans as mealmind_list_plans,
    seed_demo_mealmind_if_empty as mealmind_seed_demo,
)
from app.modules.pricepilot.service import (
    compare_item_prices as pricepilot_compare,
    seed_demo_prices_if_empty as pricepilot_seed_demo,
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


def _open_desktop_app(arguments: dict[str, object], _: ToolContext) -> str:
    app_name = str(arguments.get("app_name", "")).strip()
    success, message = launch_desktop_app(app_name)
    return message if success else f"I couldn't open that app. {message}"


def _open_url(arguments: dict[str, object], _: ToolContext) -> str:
    url = str(arguments.get("url", "")).strip()
    if not url:
        return "Please provide a website address."
    if not url.startswith(("https://", "http://")):
        url = "https://" + url
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "I can only open valid HTTP or HTTPS website addresses."
    if open_url_with_preferred_browser(url, settings.preferred_browser):
        return f"Opened {url} in {settings.preferred_browser}."
    return f"Couldn't open {url} in {settings.preferred_browser}."


def _search_web(arguments: dict[str, object], _: ToolContext) -> str:
    query = str(arguments.get("query", "")).strip()
    if not query:
        return "Please provide something to search for."
    url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
    if open_url_with_preferred_browser(url, settings.preferred_browser):
        return f"Opened web search results for: {query}"
    return "Couldn't open the preferred browser for that search."


def _navigate_current_tab(arguments: dict[str, object], _: ToolContext) -> str:
    url = str(arguments.get("url", "")).strip()
    if not url:
        return "Please provide a website address."
    if not url.startswith(("https://", "http://")):
        url = "https://" + url
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "I can only navigate to valid HTTP or HTTPS website addresses."
    if navigate_current_browser_tab(url, settings.preferred_browser):
        return f"Navigated the current {settings.preferred_browser} tab to {url}."
    return f"I couldn't access an open {settings.preferred_browser} window to navigate its current tab."


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


# --- MealMind & PricePilot Tools ---
def _plan_meals(arguments: dict[str, object], context: ToolContext) -> str:
    if not context.user or not context.db:
        return "Authentication or database session is missing."
    mealmind_seed_demo(context.db, context.user.id)
    plans = mealmind_list_plans(context.db, context.user.id)
    if not plans:
        return "No meals currently planned in MealMind."

    lines = ["Upcoming Meal Plan:"]
    for p in plans[:8]:
        name = p.recipe_title or p.custom_meal_name or "Custom Meal"
        lines.append(f"- {p.plan_date.isoformat()} [{p.meal_type.upper()}]: {name}")
    return "\n".join(lines)


def _get_grocery_list(arguments: dict[str, object], context: ToolContext) -> str:
    if not context.user or not context.db:
        return "Authentication or database session is missing."
    mealmind_seed_demo(context.db, context.user.id)
    items = mealmind_list_grocery(context.db, context.user.id)
    if not items:
        return "Your grocery list is empty."

    lines = [f"Grocery List ({len(items)} item(s)):"]
    for i in items:
        status_sym = "✓" if i.is_purchased else "○"
        lines.append(f"- [{status_sym}] {i.item_name} ({i.quantity}) [{i.category}] ~${i.estimated_cost:.2f}")
    return "\n".join(lines)


def _add_grocery_item(arguments: dict[str, object], context: ToolContext) -> str:
    if not context.user or not context.db:
        return "Authentication or database session is missing."
    name = str(arguments.get("item_name", "")).strip()
    if not name:
        return "item_name is required."
    quantity = str(arguments.get("quantity", "1"))
    category = str(arguments.get("category", "produce"))
    item = mealmind_add_grocery(
        context.db,
        context.user.id,
        GroceryItemCreate(item_name=name, quantity=quantity, category=category, estimated_cost=3.0),
    )
    return f"Added '{item.item_name}' ({item.quantity}) to your MealMind grocery list."


def _search_product_prices(arguments: dict[str, object], context: ToolContext) -> str:
    if not context.user or not context.db:
        return "Authentication or database session is missing."
    query = str(arguments.get("item_name", "")).strip()
    if not query:
        return "item_name is required to search prices."
    pricepilot_seed_demo(context.db, context.user.id)
    comp = pricepilot_compare(context.db, context.user.id, query=query)
    if not comp:
        return f"No store price comparisons found matching '{query}' in PricePilot."

    lines = [
        f"Price Comparison for '{comp.matched_item}':",
        f"Best deal at {comp.cheapest_store}: ${comp.lowest_price:.2f} (Save up to ${comp.potential_savings:.2f})",
        "Store Breakdown:",
    ]
    for o in comp.offers:
        badge = " [BEST DEAL]" if o.is_best_price else ""
        deal = f" ({o.deal_description})" if o.deal_description else ""
        lines.append(f"- {o.store_name}: ${o.price:.2f}/{o.unit}{deal}{badge}")
    return "\n".join(lines)


# --- AutoFlow Tools ---
def _get_morning_briefing(arguments: dict[str, object], context: ToolContext) -> str:
    if not context.user or not context.db:
        return "Authentication or database session is missing."
    autoflow_seed_demo(context.db, context.user.id)
    briefing = autoflow_get_briefing(context.db, context.user.id)
    return briefing.summary_markdown


def _list_workflows(arguments: dict[str, object], context: ToolContext) -> str:
    if not context.user or not context.db:
        return "Authentication or database session is missing."
    autoflow_seed_demo(context.db, context.user.id)
    workflows = autoflow_list(context.db, context.user.id)
    if not workflows:
        return "No workflows configured in AutoFlow."

    lines = [f"Configured Workflows ({len(workflows)}):"]
    for w in workflows:
        status = "Active" if w.is_active else "Inactive"
        sched = f" [{w.schedule_cron}]" if w.schedule_cron else ""
        lines.append(f"- ID {w.id}: {w.name} ({w.trigger_type}{sched}) — {status}")
    return "\n".join(lines)


def _trigger_workflow(arguments: dict[str, object], context: ToolContext) -> str:
    if not context.user or not context.db:
        return "Authentication or database session is missing."
    autoflow_seed_demo(context.db, context.user.id)
    workflows = autoflow_list(context.db, context.user.id)
    target = None

    wf_id = arguments.get("workflow_id")
    if wf_id is not None:
        try:
            target_id = int(wf_id)  # type: ignore[arg-type]
            target = next((w for w in workflows if w.id == target_id), None)
        except (ValueError, TypeError):
            pass

    if not target:
        wf_name = str(arguments.get("workflow_name", "")).strip().lower()
        if wf_name:
            target = next((w for w in workflows if wf_name in w.name.lower()), None)

    if not target:
        return "Workflow not found. Available: " + ", ".join(w.name for w in workflows)

    run = autoflow_execute(context.db, context.user.id, target.id, triggered_by="assistant")
    approval_notice = " (Awaiting your approval in dashboard)" if run.requires_approval else ""
    return f"Triggered workflow '{target.name}'. Status: {run.status}{approval_notice}.\nSummary: {run.results_summary}"


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "open_desktop_app",
            "description": "Open a locally installed desktop application on the user's computer by its Start menu name, such as Chrome, Word, Spotify, Notepad, or Calculator. Use this when the user asks to open or launch an app. If it is not installed or cannot be found, report that clearly and do not claim success.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {"type": "string", "description": "The installed application name to open"},
                },
                "required": ["app_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_url",
            "description": "Open an HTTP or HTTPS website, including a website mentioned in a follow-up request. Use the user's preferred browser. Do not use this for unsupported browser automation or claim page contents were inspected.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Complete website URL to open"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "navigate_current_tab",
            "description": "Navigate the already-open/current tab in the user's preferred browser. Use this when the user explicitly says same tab, current tab, already-open tab, or do not open a new tab. Do not use open_url for those requests.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Complete website URL to navigate the current tab to"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Open web search results for a query in the user's preferred browser. Use for general web searches or when a follow-up asks to find something online.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to search for"},
                },
                "required": ["query"],
            },
        },
    },
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
    {
        "type": "function",
        "function": {
            "name": "plan_meals",
            "description": "View planned meals or weekly meal schedule in MealMind.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_grocery_list",
            "description": "Retrieve active grocery items needed on the MealMind grocery list.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_grocery_item",
            "description": "Add an item to the MealMind grocery list.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_name": {"type": "string", "description": "Name of grocery item or ingredient"},
                    "quantity": {"type": "string", "description": "Quantity or packaging, e.g. '2 bags', '1 dozen'"},
                    "category": {"type": "string", "description": "Category (produce, dairy, meat, pantry, bakery, other)"},
                },
                "required": ["item_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_product_prices",
            "description": "Search and compare product prices across stores in PricePilot to find the best deal.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_name": {"type": "string", "description": "Product or ingredient name to compare prices for"},
                },
                "required": ["item_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_morning_briefing",
            "description": "Get a consolidated executive daily briefing combining LifeOS tasks, InboxZero emails, MealMind dinners, and SpendWise budget alerts.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_workflows",
            "description": "List all configured cross-module automations and scheduled workflows in AutoFlow.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trigger_workflow",
            "description": "Run a cross-module workflow in AutoFlow by name or ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "workflow_name": {"type": "string", "description": "Name or keyword of the workflow to run"},
                    "workflow_id": {"type": "integer", "description": "Optional workflow ID"},
                },
                "required": [],
            },
        },
    },
]

TOOL_HANDLERS: dict[str, ToolHandler] = {
    "open_desktop_app": _open_desktop_app,
    "open_url": _open_url,
    "navigate_current_tab": _navigate_current_tab,
    "search_web": _search_web,
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
    "plan_meals": _plan_meals,
    "get_grocery_list": _get_grocery_list,
    "add_grocery_item": _add_grocery_item,
    "search_product_prices": _search_product_prices,
    "get_morning_briefing": _get_morning_briefing,
    "list_workflows": _list_workflows,
    "trigger_workflow": _trigger_workflow,
}


def run_tool(name: str, arguments: dict[str, object], context: ToolContext | None = None) -> str:
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return "Tool is not available."
    ctx = context or ToolContext()
    return handler(arguments, ctx)
