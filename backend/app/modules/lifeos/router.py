from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.lifeos.schemas import TaskCreate, TaskRead, TaskSummaryRead, TaskUpdate
from app.modules.lifeos.service import (
    create_task,
    delete_task,
    get_task,
    get_task_summary,
    list_tasks,
    update_task,
)

router = APIRouter(prefix="/lifeos/tasks", tags=["lifeos"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_new_task(payload: TaskCreate, current_user: CurrentUser, db: DbSession) -> TaskRead:
    task = create_task(db, current_user.id, payload)
    return TaskRead.model_validate(task)


@router.get("", response_model=list[TaskRead])
def get_user_tasks(
    current_user: CurrentUser,
    db: DbSession,
    status: str | None = Query(default=None, pattern="^(pending|in_progress|completed|cancelled)$"),
    priority: str | None = Query(default=None, pattern="^(low|medium|high|urgent)$"),
    search: str | None = Query(default=None, max_length=100),
    tag: str | None = Query(default=None, max_length=50),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[TaskRead]:
    tasks = list_tasks(
        db,
        current_user.id,
        status=status,
        priority=priority,
        search=search,
        tag=tag,
        limit=limit,
        offset=offset,
    )
    return [TaskRead.model_validate(t) for t in tasks]


@router.get("/summary", response_model=TaskSummaryRead)
def get_user_tasks_summary(
    current_user: CurrentUser,
    db: DbSession,
    tz: str = Query(default="UTC", alias="timezone"),
) -> TaskSummaryRead:
    return get_task_summary(db, current_user.id, user_tz_name=tz)


@router.get("/{task_id}", response_model=TaskRead)
def get_single_task(task_id: int, current_user: CurrentUser, db: DbSession) -> TaskRead:
    task = get_task(db, current_user.id, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return TaskRead.model_validate(task)


@router.patch("/{task_id}", response_model=TaskRead)
def update_existing_task(
    task_id: int,
    payload: TaskUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> TaskRead:
    task = update_task(db, current_user.id, task_id, payload)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return TaskRead.model_validate(task)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_task(task_id: int, current_user: CurrentUser, db: DbSession) -> None:
    deleted = delete_task(db, current_user.id, task_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
