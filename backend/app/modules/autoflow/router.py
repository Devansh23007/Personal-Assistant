from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.autoflow.schemas import (
    MorningBriefingResponse,
    WorkflowCreate,
    WorkflowRead,
    WorkflowRunRead,
    WorkflowUpdate,
)
from app.modules.autoflow.service import (
    approve_workflow_run,
    create_workflow,
    delete_workflow,
    execute_workflow,
    get_morning_briefing,
    get_workflow,
    list_workflow_runs,
    list_workflows,
    reject_workflow_run,
    seed_demo_workflows_if_empty,
    update_workflow,
)

router = APIRouter(prefix="/autoflow", tags=["autoflow"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.get("/workflows", response_model=list[WorkflowRead])
def get_workflows(current_user: CurrentUser, db: DbSession) -> list[WorkflowRead]:
    seed_demo_workflows_if_empty(db, current_user.id)
    workflows = list_workflows(db, current_user.id)
    return [WorkflowRead.model_validate(w) for w in workflows]


@router.post("/workflows", response_model=WorkflowRead, status_code=status.HTTP_201_CREATED)
def add_workflow(payload: WorkflowCreate, current_user: CurrentUser, db: DbSession) -> WorkflowRead:
    wf = create_workflow(db, current_user.id, payload)
    return WorkflowRead.model_validate(wf)


@router.get("/workflows/{workflow_id}", response_model=WorkflowRead)
def get_single_workflow(workflow_id: int, current_user: CurrentUser, db: DbSession) -> WorkflowRead:
    wf = get_workflow(db, current_user.id, workflow_id)
    if not wf:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return WorkflowRead.model_validate(wf)


@router.patch("/workflows/{workflow_id}", response_model=WorkflowRead)
def edit_workflow(
    workflow_id: int,
    payload: WorkflowUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> WorkflowRead:
    wf = update_workflow(db, current_user.id, workflow_id, payload)
    if not wf:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return WorkflowRead.model_validate(wf)


@router.delete("/workflows/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_workflow(workflow_id: int, current_user: CurrentUser, db: DbSession) -> None:
    deleted = delete_workflow(db, current_user.id, workflow_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")


@router.post("/workflows/{workflow_id}/run", response_model=WorkflowRunRead)
def trigger_workflow(
    workflow_id: int,
    current_user: CurrentUser,
    db: DbSession,
) -> WorkflowRunRead:
    seed_demo_workflows_if_empty(db, current_user.id)
    try:
        return execute_workflow(db, current_user.id, workflow_id, triggered_by="manual")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/runs", response_model=list[WorkflowRunRead])
def get_runs(
    current_user: CurrentUser,
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=100),
) -> list[WorkflowRunRead]:
    seed_demo_workflows_if_empty(db, current_user.id)
    return list_workflow_runs(db, current_user.id, limit=limit)


@router.post("/runs/{run_id}/approve", response_model=WorkflowRunRead)
def approve_run(run_id: int, current_user: CurrentUser, db: DbSession) -> WorkflowRunRead:
    res = approve_workflow_run(db, current_user.id, run_id)
    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return res


@router.post("/runs/{run_id}/reject", response_model=WorkflowRunRead)
def reject_run(run_id: int, current_user: CurrentUser, db: DbSession) -> WorkflowRunRead:
    res = reject_workflow_run(db, current_user.id, run_id)
    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return res


@router.get("/briefing", response_model=MorningBriefingResponse)
def get_briefing(current_user: CurrentUser, db: DbSession) -> MorningBriefingResponse:
    seed_demo_workflows_if_empty(db, current_user.id)
    return get_morning_briefing(db, current_user.id)
