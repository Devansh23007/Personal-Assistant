from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.spendwise.schemas import (
    BudgetCreate,
    BudgetRead,
    CSVImportResult,
    SpendSummaryRead,
    TransactionCreate,
    TransactionRead,
    TransactionUpdate,
)
from app.modules.spendwise.service import (
    create_transaction,
    delete_budget,
    delete_transaction,
    get_spend_summary,
    get_transaction,
    import_transactions_from_csv,
    list_budgets_with_progress,
    list_transactions,
    seed_demo_transactions_if_empty,
    set_budget,
    update_transaction,
)

router = APIRouter(prefix="/spendwise", tags=["spendwise"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.get("/summary", response_model=SpendSummaryRead)
def get_summary(
    current_user: CurrentUser,
    db: DbSession,
    month: str | None = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
) -> SpendSummaryRead:
    seed_demo_transactions_if_empty(db, current_user.id)
    return get_spend_summary(db, current_user.id, month=month)


@router.get("/transactions", response_model=list[TransactionRead])
def get_transactions(
    current_user: CurrentUser,
    db: DbSession,
    type: str | None = Query(default=None, pattern="^(expense|income|all)$"),
    category: str | None = Query(default=None),
    month: str | None = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    search: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[TransactionRead]:
    seed_demo_transactions_if_empty(db, current_user.id)
    txs = list_transactions(
        db,
        current_user.id,
        type=type,
        category=category,
        month=month,
        search=search,
        limit=limit,
        offset=offset,
    )
    return [TransactionRead.model_validate(t) for t in txs]


@router.post("/transactions", response_model=TransactionRead, status_code=status.HTTP_201_CREATED)
def add_transaction(
    payload: TransactionCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> TransactionRead:
    t = create_transaction(db, current_user.id, payload)
    return TransactionRead.model_validate(t)


@router.get("/transactions/{transaction_id}", response_model=TransactionRead)
def get_single_transaction(transaction_id: int, current_user: CurrentUser, db: DbSession) -> TransactionRead:
    t = get_transaction(db, current_user.id, transaction_id)
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return TransactionRead.model_validate(t)


@router.patch("/transactions/{transaction_id}", response_model=TransactionRead)
def update_existing_transaction(
    transaction_id: int,
    payload: TransactionUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> TransactionRead:
    t = update_transaction(db, current_user.id, transaction_id, payload)
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return TransactionRead.model_validate(t)


@router.delete("/transactions/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_transaction(transaction_id: int, current_user: CurrentUser, db: DbSession) -> None:
    deleted = delete_transaction(db, current_user.id, transaction_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")


@router.post("/transactions/import-csv", response_model=CSVImportResult)
def import_csv(
    current_user: CurrentUser,
    db: DbSession,
    csv_text: str = Body(..., media_type="text/plain"),
) -> CSVImportResult:
    return import_transactions_from_csv(db, current_user.id, csv_text)


@router.get("/budgets", response_model=list[BudgetRead])
def get_budgets(
    current_user: CurrentUser,
    db: DbSession,
    month: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
) -> list[BudgetRead]:
    seed_demo_transactions_if_empty(db, current_user.id)
    return list_budgets_with_progress(db, current_user.id, month)


@router.post("/budgets", response_model=BudgetRead, status_code=status.HTTP_201_CREATED)
def configure_budget(
    payload: BudgetCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> BudgetRead:
    b = set_budget(db, current_user.id, payload)
    budgets = list_budgets_with_progress(db, current_user.id, b.month)
    matching = next((item for item in budgets if item.id == b.id), None)
    if not matching:
        return BudgetRead(
            id=b.id,
            user_id=b.user_id,
            category=b.category,
            monthly_limit=b.monthly_limit,
            month=b.month,
            created_at=b.created_at,
            updated_at=b.updated_at,
        )
    return matching


@router.delete("/budgets/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_budget(budget_id: int, current_user: CurrentUser, db: DbSession) -> None:
    deleted = delete_budget(db, current_user.id, budget_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")
