from datetime import date, datetime, timedelta, timezone
import json

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.modules.autoflow.models import Workflow, WorkflowRun
from app.modules.autoflow.schemas import (
    MorningBriefingResponse,
    WorkflowCreate,
    WorkflowRead,
    WorkflowRunRead,
    WorkflowUpdate,
)
from app.modules.inboxzero.service import (
    get_or_create_account as inboxzero_get_or_create_account,
    list_messages as inboxzero_list_messages,
    seed_demo_inbox_if_empty as inboxzero_seed_demo,
)
from app.modules.learnloop.service import (
    list_decks_with_stats as learnloop_list_decks,
    seed_demo_deck_if_empty as learnloop_seed_demo,
)
from app.modules.lifeos.schemas import TaskCreate
from app.modules.lifeos.service import (
    create_task as lifeos_create_task,
    list_tasks as lifeos_list_tasks,
)
from app.modules.mealmind.service import (
    generate_grocery_from_plans as mealmind_generate_grocery,
    list_grocery_items as mealmind_list_grocery,
    list_meal_plans as mealmind_list_plans,
    seed_demo_mealmind_if_empty as mealmind_seed_demo,
)
from app.modules.pricepilot.service import (
    analyze_basket as pricepilot_analyze_basket,
    seed_demo_prices_if_empty as pricepilot_seed_demo,
)
from app.modules.spendwise.service import (
    list_budgets_with_progress as spendwise_list_budgets,
    seed_demo_transactions_if_empty as spendwise_seed_demo,
)


def seed_demo_workflows_if_empty(db: Session, user_id: int) -> None:
    count = db.scalar(select(func.count(Workflow.id)).where(Workflow.user_id == user_id))
    if count and count > 0:
        return

    w1 = Workflow(
        user_id=user_id,
        name="Consolidated Morning Briefing",
        description="Daily aggregation of urgent tasks, unread emails, today's dinner plan, and budget status.",
        trigger_type="scheduled",
        schedule_cron="0 8 * * *",
        is_active=True,
        config_json=json.dumps({"action": "morning_briefing"}),
    )

    w2 = Workflow(
        user_id=user_id,
        name="Smart Grocery Restock & Price Optimizer",
        description="Scans upcoming meal plans, syncs grocery needs, and runs PricePilot basket optimization across stores.",
        trigger_type="scheduled",
        schedule_cron="0 10 * * 6",
        is_active=True,
        config_json=json.dumps({"action": "grocery_restock_optimizer", "require_approval": True}),
    )

    w3 = Workflow(
        user_id=user_id,
        name="Weekly Financial Budget Guard",
        description="Audits all category budgets; flags categories over 80% and schedules an expense review task.",
        trigger_type="scheduled",
        schedule_cron="0 18 * * 0",
        is_active=True,
        config_json=json.dumps({"action": "budget_guard"}),
    )

    w4 = Workflow(
        user_id=user_id,
        name="Daily Study Spaced Repetition Loop",
        description="Checks LearnLoop flashcards due for review and logs a 15-minute study block into LifeOS.",
        trigger_type="scheduled",
        schedule_cron="0 19 * * *",
        is_active=True,
        config_json=json.dumps({"action": "study_loop"}),
    )

    db.add_all([w1, w2, w3, w4])
    db.commit()


def list_workflows(db: Session, user_id: int) -> list[Workflow]:
    return list(db.scalars(select(Workflow).where(Workflow.user_id == user_id).order_by(Workflow.id.asc())).all())


def get_workflow(db: Session, user_id: int, workflow_id: int) -> Workflow | None:
    return db.scalar(select(Workflow).where(Workflow.user_id == user_id, Workflow.id == workflow_id))


def create_workflow(db: Session, user_id: int, payload: WorkflowCreate) -> Workflow:
    workflow = Workflow(
        user_id=user_id,
        name=payload.name,
        description=payload.description,
        trigger_type=payload.trigger_type,
        schedule_cron=payload.schedule_cron,
        is_active=payload.is_active,
        config_json=json.dumps(payload.config),
    )
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    return workflow


def update_workflow(db: Session, user_id: int, workflow_id: int, payload: WorkflowUpdate) -> Workflow | None:
    wf = get_workflow(db, user_id, workflow_id)
    if not wf:
        return None
    if payload.name is not None:
        wf.name = payload.name
    if payload.description is not None:
        wf.description = payload.description
    if payload.trigger_type is not None:
        wf.trigger_type = payload.trigger_type
    if payload.schedule_cron is not None:
        wf.schedule_cron = payload.schedule_cron
    if payload.is_active is not None:
        wf.is_active = payload.is_active
    if payload.config is not None:
        wf.config_json = json.dumps(payload.config)

    db.commit()
    db.refresh(wf)
    return wf


def delete_workflow(db: Session, user_id: int, workflow_id: int) -> bool:
    wf = get_workflow(db, user_id, workflow_id)
    if not wf:
        return False
    db.delete(wf)
    db.commit()
    return True


def list_workflow_runs(db: Session, user_id: int, limit: int = 50) -> list[WorkflowRunRead]:
    runs = list(
        db.scalars(
            select(WorkflowRun)
            .where(WorkflowRun.user_id == user_id)
            .order_by(desc(WorkflowRun.created_at))
            .limit(limit)
        ).all()
    )

    results: list[WorkflowRunRead] = []
    for r in runs:
        results.append(
            WorkflowRunRead(
                id=r.id,
                workflow_id=r.workflow_id,
                workflow_name=r.workflow.name if r.workflow else None,
                user_id=r.user_id,
                status=r.status,
                triggered_by=r.triggered_by,
                results_summary=r.results_summary,
                details_json=r.details_json,
                requires_approval=r.requires_approval,
                approved_at=r.approved_at,
                created_at=r.created_at,
            )
        )
    return results


def get_morning_briefing(db: Session, user_id: int) -> MorningBriefingResponse:
    # 1. LifeOS Tasks
    tasks = lifeos_list_tasks(db, user_id, status="pending")
    urgent_tasks = [
        {"id": t.id, "title": t.title, "priority": t.priority, "due_date": t.due_date.isoformat() if t.due_date else None}
        for t in tasks if t.priority in ("urgent", "high") or (t.due_date and t.due_date.date() <= date.today())
    ]

    # 2. InboxZero Emails
    user_email = f"user_{user_id}@workspace.internal"
    account = inboxzero_get_or_create_account(db, user_id, email_address=user_email)
    inboxzero_seed_demo(db, user_id, account)
    messages = inboxzero_list_messages(db, user_id)
    unread_messages = [
        {"id": m.id, "from": m.sender, "subject": m.subject, "category": m.category}
        for m in messages if not m.is_read
    ]

    # 3. MealMind Dinner
    mealmind_seed_demo(db, user_id)
    plans = mealmind_list_plans(db, user_id, start_date=date.today(), end_date=date.today())
    dinner_plan = next((p for p in plans if p.meal_type == "dinner"), None)
    dinner_data = None
    if dinner_plan:
        dinner_data = {
            "meal": dinner_plan.recipe_title or dinner_plan.custom_meal_name,
            "notes": dinner_plan.notes,
        }

    # 4. SpendWise Budget Alerts
    spendwise_seed_demo(db, user_id)
    current_month = date.today().strftime("%Y-%m")
    budgets = spendwise_list_budgets(db, user_id, month=current_month)
    alerts = [
        {
            "category": b.category,
            "spent": b.spent_amount,
            "limit": b.monthly_limit,
            "percentage": b.percentage_used,
        }
        for b in budgets if b.percentage_used >= 75.0
    ]

    # 5. LearnLoop Due Cards
    learnloop_seed_demo(db, user_id)
    decks = learnloop_list_decks(db, user_id)
    total_due = sum(d.due_count for d in decks)

    # Build Markdown Summary
    lines = [
        f"### ☀️ Good Morning! Here is your Daily Workspace Briefing\n",
        f"**Tasks**: You have **{len(tasks)}** active task(s), with **{len(urgent_tasks)}** requiring prompt attention.",
    ]
    if urgent_tasks:
        for ut in urgent_tasks[:3]:
            lines.append(f"- 🔴 **{ut['title']}** (Priority: {ut['priority']})")

    lines.append(f"\n**Inbox**: **{len(unread_messages)}** unread email(s) awaiting review.")
    if unread_messages:
        for um in unread_messages[:2]:
            lines.append(f"- ✉️ *{um['subject']}* from {um['from']}")

    if dinner_data:
        lines.append(f"\n**Dinner Plan**: 🍽️ **{dinner_data['meal']}**")

    if alerts:
        lines.append(f"\n**Financial Warning**: {len(alerts)} category budget(s) nearing limit:")
        for al in alerts:
            lines.append(f"- ⚠️ {al['category']}: ${al['spent']:.2f} / ${al['limit']:.2f} ({al['percentage']}%)")

    if total_due > 0:
        lines.append(f"\n**Active Recall**: 🧠 **{total_due}** flashcard(s) due for spaced repetition review today.")

    md_summary = "\n".join(lines)

    return MorningBriefingResponse(
        generated_at=datetime.now(timezone.utc),
        headline=f"{len(urgent_tasks)} urgent items · {len(unread_messages)} unread messages · {total_due} study cards due",
        urgent_tasks=urgent_tasks,
        urgent_emails=unread_messages[:5],
        planned_dinner=dinner_data,
        budget_alerts=alerts,
        study_due_count=total_due,
        summary_markdown=md_summary,
    )


def execute_workflow(
    db: Session,
    user_id: int,
    workflow_id: int,
    triggered_by: str = "manual",
) -> WorkflowRunRead:
    wf = get_workflow(db, user_id, workflow_id)
    if not wf:
        raise ValueError("Workflow not found")

    try:
        config = json.loads(wf.config_json) if wf.config_json else {}
    except Exception:
        config = {}

    action = config.get("action", "custom")
    requires_approval = bool(config.get("require_approval", False))
    status = "pending_approval" if requires_approval else "completed"

    details: dict[str, object] = {"workflow": wf.name, "executed_at": datetime.now(timezone.utc).isoformat()}
    summary = ""

    if action == "morning_briefing":
        briefing = get_morning_briefing(db, user_id)
        summary = briefing.headline
        details["briefing"] = briefing.model_dump(mode="json")

    elif action == "grocery_restock_optimizer":
        mealmind_seed_demo(db, user_id)
        pricepilot_seed_demo(db, user_id)
        # Sync groceries from meal plans
        mealmind_generate_grocery(db, user_id)
        groceries = mealmind_list_grocery(db, user_id, purchased=False)
        item_names = [g.item_name for g in groceries[:6]]

        basket_comp = pricepilot_analyze_basket(db, user_id=user_id, item_names=item_names)
        summary = (
            f"Restock list ready ({len(item_names)} items). Best store: {basket_comp.best_overall_store} "
            f"at ${basket_comp.lowest_total_cost:.2f}. Approval required before finalizing purchase."
        )
        details["basket_comparison"] = basket_comp.model_dump(mode="json")
        details["items"] = item_names

    elif action == "budget_guard":
        spendwise_seed_demo(db, user_id)
        current_month = date.today().strftime("%Y-%m")
        budgets = spendwise_list_budgets(db, user_id, month=current_month)
        over_threshold = [b for b in budgets if b.percentage_used >= 80.0]
        if over_threshold:
            summary = f"Alert: {len(over_threshold)} budget category(s) exceeded 80% usage. Scheduled LifeOS financial review task."
            lifeos_create_task(
                db,
                user_id,
                TaskCreate(
                    title="Weekly Budget Review: Adjust spend on flagged categories",
                    description=f"Categories nearing ceiling: {', '.join(b.category for b in over_threshold)}",
                    priority="high",
                    due_date=datetime.now(timezone.utc) + timedelta(days=1),
                    tags=["finance", "autoflow"],
                ),
            )
        else:
            summary = f"All {len(budgets)} category budgets are currently healthy (<80% spend)."
        details["over_threshold_count"] = len(over_threshold)

    elif action == "study_loop":
        learnloop_seed_demo(db, user_id)
        decks = learnloop_list_decks(db, user_id)
        due_total = sum(d.due_count for d in decks)
        if due_total > 0:
            summary = f"Found {due_total} flashcard(s) due for recall. Scheduled 15m review session in LifeOS."
            lifeos_create_task(
                db,
                user_id,
                TaskCreate(
                    title=f"LearnLoop Active Recall: {due_total} cards due",
                    description="Spend 15 minutes reviewing active flashcards to maintain spaced repetition retention.",
                    priority="medium",
                    due_date=datetime.now(timezone.utc) + timedelta(hours=4),
                    tags=["study", "autoflow"],
                ),
            )
        else:
            summary = "All flashcards are up to date! No revision session needed today."
        details["due_count"] = due_total

    else:
        summary = f"Workflow '{wf.name}' executed successfully."

    run = WorkflowRun(
        workflow_id=wf.id,
        user_id=user_id,
        status=status,
        triggered_by=triggered_by,
        results_summary=summary,
        details_json=json.dumps(details),
        requires_approval=requires_approval,
        approved_at=None,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    return WorkflowRunRead(
        id=run.id,
        workflow_id=run.workflow_id,
        workflow_name=wf.name,
        user_id=run.user_id,
        status=run.status,
        triggered_by=run.triggered_by,
        results_summary=run.results_summary,
        details_json=run.details_json,
        requires_approval=run.requires_approval,
        approved_at=run.approved_at,
        created_at=run.created_at,
    )


def approve_workflow_run(db: Session, user_id: int, run_id: int) -> WorkflowRunRead | None:
    run = db.scalar(select(WorkflowRun).where(WorkflowRun.user_id == user_id, WorkflowRun.id == run_id))
    if not run:
        return None
    run.status = "completed"
    run.approved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(run)

    return WorkflowRunRead(
        id=run.id,
        workflow_id=run.workflow_id,
        workflow_name=run.workflow.name if run.workflow else None,
        user_id=run.user_id,
        status=run.status,
        triggered_by=run.triggered_by,
        results_summary=f"Approved by user. {run.results_summary}",
        details_json=run.details_json,
        requires_approval=False,
        approved_at=run.approved_at,
        created_at=run.created_at,
    )


def reject_workflow_run(db: Session, user_id: int, run_id: int) -> WorkflowRunRead | None:
    run = db.scalar(select(WorkflowRun).where(WorkflowRun.user_id == user_id, WorkflowRun.id == run_id))
    if not run:
        return None
    run.status = "rejected"
    db.commit()
    db.refresh(run)

    return WorkflowRunRead(
        id=run.id,
        workflow_id=run.workflow_id,
        workflow_name=run.workflow.name if run.workflow else None,
        user_id=run.user_id,
        status=run.status,
        triggered_by=run.triggered_by,
        results_summary="Rejected by user. Execution aborted.",
        details_json=run.details_json,
        requires_approval=False,
        approved_at=None,
        created_at=run.created_at,
    )
