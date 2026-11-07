import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class ProductPriceCreate(BaseModel):
    item_name: str = Field(min_length=1, max_length=255)
    category: str = Field(default="produce", max_length=64)
    store_name: str = Field(min_length=1, max_length=100)
    price: float = Field(gt=0)
    unit: str = Field(default="each", max_length=64)
    in_stock: bool = True
    deal_description: str | None = None


class ProductPriceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    item_name: str
    category: str
    store_name: str
    price: float
    unit: str
    in_stock: bool
    deal_description: str | None
    last_updated_at: dt.datetime


class StoreOffer(BaseModel):
    store_name: str
    price: float
    unit: str
    in_stock: bool
    deal_description: str | None
    is_best_price: bool = False


class ProductPriceComparison(BaseModel):
    query: str
    matched_item: str
    category: str
    cheapest_store: str
    lowest_price: float
    highest_price: float
    potential_savings: float
    offers: list[StoreOffer]


class BasketStoreEstimate(BaseModel):
    store_name: str
    total_cost: float
    items_found: int
    total_requested: int
    missing_items: list[str]


class BasketComparison(BaseModel):
    items_requested: list[str]
    best_overall_store: str
    lowest_total_cost: float
    highest_total_cost: float
    store_breakdowns: list[BasketStoreEstimate]
