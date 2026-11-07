import csv
from datetime import date, datetime, timedelta, timezone
import io

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modules.spendwise.models import Budget, Transaction
from app.modules.spendwise.schemas import (
    BudgetCreate,
    BudgetRead,
    CSVImportResult,
    SpendSummaryRead,
    TransactionCreate,
    TransactionUpdate,
)


def seed_demo_transactions_if_empty(db: Session, user_id: int) -> None:
    today = date.today()
    current_month_str = today.strftime("%Y-%m")

    tx_count = db.scalar(select(func.count(Transaction.id)).where(Transaction.user_id == user_id))
    if not tx_count or tx_count == 0:
        # Sample transactions
        sample_data = [
            {
                "amount": 4200.00,
                "type": "income",
                "category": "Salary & Investments",
                "description": "Monthly Salary Deposit",
                "date": today.replace(day=1),
                "payment_method": "Bank Transfer",
                "tags": "income,salary",
            },
            {
                "amount": 145.50,
                "type": "expense",
                "category": "Food & Dining",
                "description": "Weekly Grocery Run at Trader Joe's",
                "date": today - timedelta(days=2),
                "payment_method": "Credit Card",
                "tags": "groceries,food",
            },
            {
                "amount": 18.25,
                "type": "expense",
                "category": "Food & Dining",
                "description": "Coffee and Croissant",
                "date": today - timedelta(days=1),
                "payment_method": "UPI",
                "tags": "coffee",
            },
            {
                "amount": 75.00,
                "type": "expense",
                "category": "Transportation",
                "description": "Gas Station Refill",
                "date": today - timedelta(days=4),
                "payment_method": "Debit Card",
                "tags": "commute,gas",
            },
            {
                "amount": 89.99,
                "type": "expense",
                "category": "Housing & Utilities",
                "description": "High-speed Fiber Internet",
                "date": today.replace(day=5) if today.day >= 5 else today,
                "payment_method": "Bank Transfer",
                "is_recurring": True,
                "tags": "bills,internet",
            },
            {
                "amount": 15.99,
                "type": "expense",
                "category": "Entertainment",
                "description": "Netflix Subscription",
                "date": today.replace(day=3) if today.day >= 3 else today,
                "payment_method": "Credit Card",
                "is_recurring": True,
                "tags": "streaming",
            },
            {
                "amount": 120.00,
                "type": "expense",
                "category": "Shopping",
                "description": "Running Shoes Discount",
                "date": today - timedelta(days=6),
                "payment_method": "Credit Card",
                "tags": "shoes,gear",
            },
        ]

        for item in sample_data:
            t = Transaction(user_id=user_id, **item)
            db.add(t)
        db.commit()

    budget_count = db.scalar(
        select(func.count(Budget.id)).where(Budget.user_id == user_id, Budget.month == current_month_str)
    )
    if not budget_count or budget_count == 0:
        sample_budgets = [
            {"category": "Food & Dining", "monthly_limit": 500.0, "month": current_month_str},
            {"category": "Transportation", "monthly_limit": 200.0, "month": current_month_str},
            {"category": "Entertainment", "monthly_limit": 100.0, "month": current_month_str},
            {"category": "Shopping", "monthly_limit": 250.0, "month": current_month_str},
        ]
        for b in sample_budgets:
            db.add(Budget(user_id=user_id, **b))
        db.commit()


def create_transaction(db: Session, user_id: int, payload: TransactionCreate) -> Transaction:
    tags_str = ",".join(payload.tags) if payload.tags else None
    t = Transaction(
        user_id=user_id,
        amount=payload.amount,
        type=payload.type,
        category=payload.category,
        description=payload.description,
        date=payload.date,
        payment_method=payload.payment_method,
        is_recurring=payload.is_recurring,
        tags=tags_str,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def list_transactions(
    db: Session,
    user_id: int,
    type: str | None = None,
    category: str | None = None,
    month: str | None = None,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Transaction]:
    query = select(Transaction).where(Transaction.user_id == user_id)

    if type and type != "all":
        query = query.where(Transaction.type == type)
    if category and category != "all":
        query = query.where(Transaction.category == category)
    if month:
        # e.g. "2026-11"
        try:
            year, m = map(int, month.split("-"))
            start_date = date(year, m, 1)
            next_month = (start_date.replace(day=28) + timedelta(days=4)).replace(day=1)
            query = query.where(Transaction.date >= start_date, Transaction.date < next_month)
        except ValueError:
            pass
    if search:
        term = f"%{search}%"
        query = query.where(
            or_(
                Transaction.description.ilike(term),
                Transaction.category.ilike(term),
                Transaction.payment_method.ilike(term),
            )
        )

    query = query.order_by(Transaction.date.desc(), Transaction.id.desc()).offset(offset).limit(limit)
    return list(db.scalars(query).all())


def get_transaction(db: Session, user_id: int, transaction_id: int) -> Transaction | None:
    return db.scalar(select(Transaction).where(Transaction.user_id == user_id, Transaction.id == transaction_id))


def update_transaction(
    db: Session,
    user_id: int,
    transaction_id: int,
    payload: TransactionUpdate,
) -> Transaction | None:
    t = get_transaction(db, user_id, transaction_id)
    if not t:
        return None

    if payload.amount is not None:
        t.amount = payload.amount
    if payload.type is not None:
        t.type = payload.type
    if payload.category is not None:
        t.category = payload.category
    if payload.description is not None:
        t.description = payload.description
    if payload.date is not None:
        t.date = payload.date
    if payload.payment_method is not None:
        t.payment_method = payload.payment_method
    if payload.is_recurring is not None:
        t.is_recurring = payload.is_recurring
    if payload.tags is not None:
        t.tags = ",".join(payload.tags) if payload.tags else None

    db.commit()
    db.refresh(t)
    return t


def delete_transaction(db: Session, user_id: int, transaction_id: int) -> bool:
    t = get_transaction(db, user_id, transaction_id)
    if not t:
        return False
    db.delete(t)
    db.commit()
    return True


def import_transactions_from_csv(db: Session, user_id: int, csv_text: str) -> CSVImportResult:
    f = io.StringIO(csv_text.strip())
    reader = csv.DictReader(f)

    imported = 0
    errors = 0
    messages: list[str] = []

    for row_idx, row in enumerate(reader, start=1):
        try:
            # Map common header variations
            keys = {k.lower().strip(): v for k, v in row.items() if k}
            desc = keys.get("description") or keys.get("memo") or keys.get("payee") or keys.get("title") or "Transaction"
            amt_str = keys.get("amount") or keys.get("price") or keys.get("total") or "0"
            amt = abs(float(amt_str.replace("$", "").replace(",", "").strip()))

            tx_type = keys.get("type", "expense").lower()
            if "debit" in tx_type or "expense" in tx_type:
                tx_type = "expense"
            elif "credit" in tx_type or "income" in tx_type:
                tx_type = "income"

            cat = keys.get("category") or "Other"
            payment_method = keys.get("payment_method") or keys.get("account") or "Card"

            date_str = keys.get("date") or str(date.today())
            try:
                tx_date = datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
            except ValueError:
                try:
                    tx_date = datetime.strptime(date_str.strip(), "%m/%d/%Y").date()
                except ValueError:
                    tx_date = date.today()

            t = Transaction(
                user_id=user_id,
                amount=amt,
                type=tx_type,
                category=cat,
                description=desc,
                date=tx_date,
                payment_method=payment_method,
            )
            db.add(t)
            imported += 1
        except Exception as exc:
            errors += 1
            messages.append(f"Row {row_idx}: {str(exc)}")

    db.commit()
    return CSVImportResult(imported_count=imported, error_count=errors, messages=messages[:10])


# --- Budgets ---
def set_budget(db: Session, user_id: int, payload: BudgetCreate) -> Budget:
    existing = db.scalar(
        select(Budget).where(
            Budget.user_id == user_id,
            Budget.category == payload.category,
            Budget.month == payload.month,
        )
    )
    if existing:
        existing.monthly_limit = payload.monthly_limit
        db.commit()
        db.refresh(existing)
        return existing

    budget = Budget(
        user_id=user_id,
        category=payload.category,
        monthly_limit=payload.monthly_limit,
        month=payload.month,
    )
    db.add(budget)
    db.commit()
    db.refresh(budget)
    return budget


def list_budgets_with_progress(db: Session, user_id: int, month: str) -> list[BudgetRead]:
    budgets = list(
        db.scalars(select(Budget).where(Budget.user_id == user_id, Budget.month == month)).all()
    )

    year, m = map(int, month.split("-"))
    start_date = date(year, m, 1)
    next_month = (start_date.replace(day=28) + timedelta(days=4)).replace(day=1)

    # Get actual spending per category for that month
    expenses = list(
        db.scalars(
            select(Transaction).where(
                Transaction.user_id == user_id,
                Transaction.type == "expense",
                Transaction.date >= start_date,
                Transaction.date < next_month,
            )
        ).all()
    )

    spent_by_category: dict[str, float] = {}
    for tx in expenses:
        spent_by_category[tx.category] = spent_by_category.get(tx.category, 0.0) + tx.amount

    result: list[BudgetRead] = []
    for b in budgets:
        spent = round(spent_by_category.get(b.category, 0.0), 2)
        remaining = round(b.monthly_limit - spent, 2)
        pct = round((spent / b.monthly_limit * 100), 1) if b.monthly_limit > 0 else 0.0
        result.append(
            BudgetRead(
                id=b.id,
                user_id=b.user_id,
                category=b.category,
                monthly_limit=b.monthly_limit,
                month=b.month,
                spent=spent,
                remaining=remaining,
                percentage_used=pct,
                created_at=b.created_at,
                updated_at=b.updated_at,
            )
        )
    return result


def delete_budget(db: Session, user_id: int, budget_id: int) -> bool:
    b = db.scalar(select(Budget).where(Budget.user_id == user_id, Budget.id == budget_id))
    if not b:
        return False
    db.delete(b)
    db.commit()
    return True


def get_spend_summary(db: Session, user_id: int, month: str | None = None) -> SpendSummaryRead:
    if not month:
        month = date.today().strftime("%Y-%m")

    year, m = map(int, month.split("-"))
    start_date = date(year, m, 1)
    next_month = (start_date.replace(day=28) + timedelta(days=4)).replace(day=1)

    txs = list(
        db.scalars(
            select(Transaction).where(
                Transaction.user_id == user_id,
                Transaction.date >= start_date,
                Transaction.date < next_month,
            )
        ).all()
    )

    total_income = sum(t.amount for t in txs if t.type == "income")
    total_expenses = sum(t.amount for t in txs if t.type == "expense")
    net_savings = total_income - total_expenses
    savings_rate = round((net_savings / total_income * 100), 1) if total_income > 0 else 0.0

    category_breakdown: dict[str, float] = {}
    for t in txs:
        if t.type == "expense":
            category_breakdown[t.category] = round(category_breakdown.get(t.category, 0.0) + t.amount, 2)

    sorted_categories = sorted(category_breakdown.items(), key=lambda x: x[1], reverse=True)
    top_categories = [{"category": c, "amount": amt} for c, amt in sorted_categories[:5]]

    # Check budgets
    budgets = list_budgets_with_progress(db, user_id, month)
    over_budget_count = sum(1 for b in budgets if b.spent > b.monthly_limit)

    return SpendSummaryRead(
        month=month,
        total_income=round(total_income, 2),
        total_expenses=round(total_expenses, 2),
        net_savings=round(net_savings, 2),
        savings_rate=savings_rate,
        category_breakdown=category_breakdown,
        top_categories=top_categories,
        over_budget_count=over_budget_count,
    )
