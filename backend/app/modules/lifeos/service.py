from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modules.lifeos.models import Task
from app.modules.lifeos.schemas import TaskCreate, TaskSummaryRead, TaskUpdate


def _get_tz(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return ZoneInfo("UTC")


def create_task(db: Session, user_id: int, payload: TaskCreate) -> Task:
    tags_str = ",".join(payload.tags) if payload.tags else None
    task = Task(
        user_id=user_id,
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        due_date=payload.due_date,
        reminder_at=payload.reminder_at,
        timezone=payload.timezone,
        tags=tags_str,
        status="pending",
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def list_tasks(
    db: Session,
    user_id: int,
    status: str | None = None,
    priority: str | None = None,
    search: str | None = None,
    tag: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Task]:
    query = select(Task).where(Task.user_id == user_id)
    if status:
        query = query.where(Task.status == status)
    if priority:
        query = query.where(Task.priority == priority)
    if tag:
        query = query.where(Task.tags.ilike(f"%{tag}%"))
    if search:
        pattern = f"%{search}%"
        query = query.where(or_(Task.title.ilike(pattern), Task.description.ilike(pattern)))

    # Order by status (pending first), then due_date, then created_at desc
    query = query.order_by(
        Task.status.desc(),
        Task.due_date.asc().nulls_last(),
        Task.created_at.desc(),
    ).offset(offset).limit(limit)

    return list(db.scalars(query).all())


def get_task(db: Session, user_id: int, task_id: int) -> Task | None:
    return db.scalar(select(Task).where(Task.user_id == user_id, Task.id == task_id))


def update_task(db: Session, user_id: int, task_id: int, payload: TaskUpdate) -> Task | None:
    task = get_task(db, user_id, task_id)
    if not task:
        return None

    if payload.title is not None:
        task.title = payload.title
    if payload.description is not None:
        task.description = payload.description
    if payload.priority is not None:
        task.priority = payload.priority
    if payload.due_date is not None:
        task.due_date = payload.due_date
    if payload.reminder_at is not None:
        task.reminder_at = payload.reminder_at
    if payload.timezone is not None:
        task.timezone = payload.timezone
    if payload.tags is not None:
        task.tags = ",".join(payload.tags) if payload.tags else None

    if payload.status is not None:
        if payload.status == "completed" and task.status != "completed":
            task.completed_at = datetime.now(timezone.utc)
        elif payload.status != "completed" and task.status == "completed":
            task.completed_at = None
        task.status = payload.status

    db.commit()
    db.refresh(task)
    return task


def delete_task(db: Session, user_id: int, task_id: int) -> bool:
    task = get_task(db, user_id, task_id)
    if not task:
        return False
    db.delete(task)
    db.commit()
    return True


def get_task_summary(db: Session, user_id: int, user_tz_name: str = "UTC") -> TaskSummaryRead:
    now_utc = datetime.now(timezone.utc)
    tz = _get_tz(user_tz_name)
    now_local = now_utc.astimezone(tz)
    start_of_today_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_today_local = now_local.replace(hour=23, minute=59, second=59, microsecond=999999)

    start_of_today_utc = start_of_today_local.astimezone(timezone.utc)
    end_of_today_utc = end_of_today_local.astimezone(timezone.utc)

    all_tasks = list(db.scalars(select(Task).where(Task.user_id == user_id)).all())

    total = len(all_tasks)
    pending = 0
    in_progress = 0
    completed = 0
    overdue = 0
    due_today = 0

    for t in all_tasks:
        if t.status == "completed":
            completed += 1
        elif t.status == "in_progress":
            in_progress += 1
        else:
            pending += 1

        if t.status in ("pending", "in_progress") and t.due_date:
            due_utc = t.due_date if t.due_date.tzinfo else t.due_date.replace(tzinfo=timezone.utc)
            if due_utc < now_utc:
                overdue += 1
            if start_of_today_utc <= due_utc <= end_of_today_utc:
                due_today += 1

    return TaskSummaryRead(
        total=total,
        pending=pending,
        in_progress=in_progress,
        completed=completed,
        overdue=overdue,
        due_today=due_today,
    )
