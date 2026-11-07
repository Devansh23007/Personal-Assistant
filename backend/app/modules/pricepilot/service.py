from datetime import datetime, timezone

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.modules.pricepilot.models import ProductPrice
from app.modules.pricepilot.schemas import (
    BasketComparison,
    BasketStoreEstimate,
    ProductPriceComparison,
    ProductPriceCreate,
    StoreOffer,
)


def seed_demo_prices_if_empty(db: Session, user_id: int | None = None) -> None:
    count = db.scalar(select(func.count(ProductPrice.id)))
    if count and count > 0:
        return

    sample_catalog = [
        # Avocados
        {"item": "Avocados", "cat": "produce", "store": "Walmart", "price": 3.48, "unit": "bag of 4", "stock": True, "deal": "Rollback Deal"},
        {"item": "Avocados", "cat": "produce", "store": "Trader Joe's", "price": 3.99, "unit": "bag of 4", "stock": True, "deal": None},
        {"item": "Avocados", "cat": "produce", "store": "Local Market", "price": 4.29, "unit": "bag of 4", "stock": True, "deal": None},
        {"item": "Avocados", "cat": "produce", "store": "Whole Foods", "price": 5.49, "unit": "bag of 4", "stock": True, "deal": "Prime 10% off"},
        # Wild Salmon
        {"item": "Wild Salmon Fillets", "cat": "meat", "store": "Walmart", "price": 10.49, "unit": "lb", "stock": True, "deal": None},
        {"item": "Wild Salmon Fillets", "cat": "meat", "store": "Trader Joe's", "price": 11.99, "unit": "lb", "stock": True, "deal": "Fresh catch"},
        {"item": "Wild Salmon Fillets", "cat": "meat", "store": "Whole Foods", "price": 15.99, "unit": "lb", "stock": True, "deal": "MSC Certified"},
        {"item": "Wild Salmon Fillets", "cat": "meat", "store": "Local Market", "price": 13.50, "unit": "lb", "stock": True, "deal": None},
        # Eggs
        {"item": "Eggs", "cat": "dairy", "store": "Walmart", "price": 3.28, "unit": "dozen", "stock": True, "deal": "Everyday Low Price"},
        {"item": "Eggs", "cat": "dairy", "store": "Trader Joe's", "price": 3.99, "unit": "dozen", "stock": True, "deal": "Pasture-raised"},
        {"item": "Eggs", "cat": "dairy", "store": "Whole Foods", "price": 4.99, "unit": "dozen", "stock": True, "deal": None},
        {"item": "Eggs", "cat": "dairy", "store": "Local Market", "price": 3.79, "unit": "dozen", "stock": True, "deal": "Local farm fresh"},
        # Quinoa
        {"item": "Organic Quinoa", "cat": "pantry", "store": "Walmart", "price": 3.98, "unit": "16 oz bag", "stock": True, "deal": None},
        {"item": "Organic Quinoa", "cat": "pantry", "store": "Trader Joe's", "price": 4.49, "unit": "16 oz bag", "stock": True, "deal": None},
        {"item": "Organic Quinoa", "cat": "pantry", "store": "Whole Foods", "price": 5.99, "unit": "16 oz bag", "stock": True, "deal": None},
        # Asparagus
        {"item": "Fresh Asparagus", "cat": "produce", "store": "Local Market", "price": 2.99, "unit": "bunch", "stock": True, "deal": "Weekly Special"},
        {"item": "Fresh Asparagus", "cat": "produce", "store": "Trader Joe's", "price": 3.49, "unit": "bunch", "stock": True, "deal": None},
        {"item": "Fresh Asparagus", "cat": "produce", "store": "Walmart", "price": 3.78, "unit": "bunch", "stock": True, "deal": None},
        {"item": "Fresh Asparagus", "cat": "produce", "store": "Whole Foods", "price": 4.99, "unit": "bunch", "stock": True, "deal": None},
        # Feta Cheese
        {"item": "Greek Feta Cheese", "cat": "dairy", "store": "Local Market", "price": 3.99, "unit": "7 oz pack", "stock": True, "deal": None},
        {"item": "Greek Feta Cheese", "cat": "dairy", "store": "Trader Joe's", "price": 4.29, "unit": "7 oz pack", "stock": True, "deal": "Imported Greek"},
        {"item": "Greek Feta Cheese", "cat": "dairy", "store": "Whole Foods", "price": 5.49, "unit": "7 oz pack", "stock": True, "deal": None},
        # Olive Oil
        {"item": "Extra Virgin Olive Oil", "cat": "pantry", "store": "Walmart", "price": 6.88, "unit": "500 ml bottle", "stock": True, "deal": None},
        {"item": "Extra Virgin Olive Oil", "cat": "pantry", "store": "Trader Joe's", "price": 7.99, "unit": "500 ml bottle", "stock": True, "deal": "Cold-pressed"},
        {"item": "Extra Virgin Olive Oil", "cat": "pantry", "store": "Whole Foods", "price": 10.99, "unit": "500 ml bottle", "stock": True, "deal": "Single-estate"},
        # Sourdough
        {"item": "Sourdough Bread", "cat": "bakery", "store": "Trader Joe's", "price": 3.49, "unit": "loaf", "stock": True, "deal": "Artisan baked"},
        {"item": "Sourdough Bread", "cat": "bakery", "store": "Local Market", "price": 4.25, "unit": "loaf", "stock": True, "deal": "Wood-fired bakery"},
        {"item": "Sourdough Bread", "cat": "bakery", "store": "Whole Foods", "price": 4.99, "unit": "loaf", "stock": True, "deal": None},
    ]

    for p in sample_catalog:
        db.add(
            ProductPrice(
                user_id=user_id,
                item_name=p["item"],
                category=p["cat"],
                store_name=p["store"],
                price=p["price"],
                unit=p["unit"],
                in_stock=p["stock"],
                deal_description=p["deal"],
            )
        )
    db.commit()


def list_product_prices(
    db: Session,
    user_id: int | None = None,
    category: str | None = None,
    search: str | None = None,
    limit: int = 50,
) -> list[ProductPrice]:
    query = select(ProductPrice)
    if user_id is not None:
        query = query.where(or_(ProductPrice.user_id == user_id, ProductPrice.user_id.is_(None)))
    if category:
        query = query.where(ProductPrice.category == category)
    if search:
        s = f"%{search.strip()}%"
        query = query.where(or_(ProductPrice.item_name.ilike(s), ProductPrice.store_name.ilike(s)))
    query = query.order_by(ProductPrice.item_name.asc(), ProductPrice.price.asc()).limit(limit)
    return list(db.scalars(query).all())


def compare_item_prices(
    db: Session,
    user_id: int | None = None,
    query: str = "",
) -> ProductPriceComparison | None:
    if not query.strip():
        return None

    s = f"%{query.strip()}%"
    db_query = select(ProductPrice).where(
        or_(ProductPrice.item_name.ilike(s), ProductPrice.category.ilike(s))
    )
    if user_id is not None:
        db_query = db_query.where(or_(ProductPrice.user_id == user_id, ProductPrice.user_id.is_(None)))

    matches = list(db.scalars(db_query).all())
    if not matches:
        return None

    # Group by item name to find best match
    best_item_name = matches[0].item_name
    item_matches = [m for m in matches if m.item_name.lower() == best_item_name.lower()]
    item_matches.sort(key=lambda x: x.price)

    lowest = item_matches[0]
    highest = item_matches[-1]

    offers = [
        StoreOffer(
            store_name=m.store_name,
            price=m.price,
            unit=m.unit,
            in_stock=m.in_stock,
            deal_description=m.deal_description,
            is_best_price=(m.price == lowest.price),
        )
        for m in item_matches
    ]

    return ProductPriceComparison(
        query=query,
        matched_item=best_item_name,
        category=lowest.category,
        cheapest_store=lowest.store_name,
        lowest_price=lowest.price,
        highest_price=highest.price,
        potential_savings=round(highest.price - lowest.price, 2),
        offers=offers,
    )


def analyze_basket(
    db: Session,
    user_id: int | None = None,
    item_names: list[str] | None = None,
) -> BasketComparison:
    if not item_names:
        item_names = []

    # Get distinct stores
    all_prices = list_product_prices(db, user_id=user_id, limit=200)
    stores = sorted(list({p.store_name for p in all_prices}))

    breakdowns: list[BasketStoreEstimate] = []
    for store in stores:
        store_total = 0.0
        found_count = 0
        missing: list[str] = []

        for req_item in item_names:
            req_clean = req_item.strip().lower()
            matching = [
                p for p in all_prices
                if p.store_name == store and (req_clean in p.item_name.lower() or p.item_name.lower() in req_clean)
            ]
            if matching:
                store_total += matching[0].price
                found_count += 1
            else:
                missing.append(req_item)

        breakdowns.append(
            BasketStoreEstimate(
                store_name=store,
                total_cost=round(store_total, 2),
                items_found=found_count,
                total_requested=len(item_names),
                missing_items=missing,
            )
        )

    # Sort stores by items found desc, then total cost asc
    breakdowns.sort(key=lambda b: (-b.items_found, b.total_cost))

    best_store = breakdowns[0].store_name if breakdowns else "None"
    lowest_cost = breakdowns[0].total_cost if breakdowns else 0.0
    highest_cost = max((b.total_cost for b in breakdowns), default=0.0)

    return BasketComparison(
        items_requested=item_names,
        best_overall_store=best_store,
        lowest_total_cost=lowest_cost,
        highest_total_cost=highest_cost,
        store_breakdowns=breakdowns,
    )


def create_product_price(db: Session, user_id: int, payload: ProductPriceCreate) -> ProductPrice:
    item = ProductPrice(
        user_id=user_id,
        item_name=payload.item_name,
        category=payload.category,
        store_name=payload.store_name,
        price=payload.price,
        unit=payload.unit,
        in_stock=payload.in_stock,
        deal_description=payload.deal_description,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item
