from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.pricepilot.schemas import (
    BasketComparison,
    ProductPriceComparison,
    ProductPriceCreate,
    ProductPriceRead,
)
from app.modules.pricepilot.service import (
    analyze_basket,
    compare_item_prices,
    create_product_price,
    list_product_prices,
    seed_demo_prices_if_empty,
)

router = APIRouter(prefix="/pricepilot", tags=["pricepilot"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


class BasketAnalysisRequest(BaseModel):
    items: list[str]


@router.get("/prices", response_model=list[ProductPriceRead])
def get_prices(
    current_user: CurrentUser,
    db: DbSession,
    category: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[ProductPriceRead]:
    seed_demo_prices_if_empty(db, current_user.id)
    items = list_product_prices(db, user_id=current_user.id, category=category, search=search, limit=limit)
    return [ProductPriceRead.model_validate(i) for i in items]


@router.post("/prices", response_model=ProductPriceRead, status_code=status.HTTP_201_CREATED)
def record_price(
    payload: ProductPriceCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> ProductPriceRead:
    item = create_product_price(db, current_user.id, payload)
    return ProductPriceRead.model_validate(item)


@router.get("/compare", response_model=ProductPriceComparison)
def compare_prices(
    current_user: CurrentUser,
    db: DbSession,
    q: str = Query(min_length=1, max_length=100),
) -> ProductPriceComparison:
    seed_demo_prices_if_empty(db, current_user.id)
    result = compare_item_prices(db, user_id=current_user.id, query=q)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No price comparison found for '{q}'")
    return result


@router.post("/basket-analysis", response_model=BasketComparison)
def compare_basket(
    payload: BasketAnalysisRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> BasketComparison:
    seed_demo_prices_if_empty(db, current_user.id)
    return analyze_basket(db, user_id=current_user.id, item_names=payload.items)
