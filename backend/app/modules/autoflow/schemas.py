import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    trigger_type: str = Field(default="manual", pattern="^(manual|scheduled|event)$")
    schedule_cron: str | None = None
    is_active: bool = True
    config: dict[str, object] = Field(default_factory=dict)


class WorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    trigger_type: str | None = None
    schedule_cron: str | None = None
    is_active: bool | None = None
    config: dict[str, object] | None = None


class WorkflowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    description: str | None
    trigger_type: str
    schedule_cron: str | None
    is_active: bool
    config_json: str
    created_at: dt.datetime


class WorkflowRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workflow_id: int
    workflow_name: str | None = None
    user_id: int
    status: str
    triggered_by: str
    results_summary: str
    details_json: str
    requires_approval: bool
    approved_at: dt.datetime | None
    created_at: dt.datetime


class MorningBriefingResponse(BaseModel):
    generated_at: dt.datetime
    headline: str
    urgent_tasks: list[dict[str, object]]
    urgent_emails: list[dict[str, object]]
    planned_dinner: dict[str, object] | None
    budget_alerts: list[dict[str, object]]
    study_due_count: int
    summary_markdown: str
