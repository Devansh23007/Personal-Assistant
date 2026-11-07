from datetime import date, datetime, timedelta, timezone
import json

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.modules.mealmind.models import GroceryItem, MealPlan, Recipe
from app.modules.mealmind.schemas import (
    GroceryItemCreate,
    GroceryItemRead,
    GroceryItemUpdate,
    GroceryListSummary,
    IngredientItem,
    MealPlanCreate,
    MealPlanRead,
    RecipeCreate,
    RecipeRead,
)


def seed_demo_mealmind_if_empty(db: Session, user_id: int) -> None:
    recipe_count = db.scalar(select(func.count(Recipe.id)).where(Recipe.user_id == user_id))
    if recipe_count and recipe_count > 0:
        return

    # 1. Seed demo recipes
    r1 = Recipe(
        user_id=user_id,
        title="Avocado & Poached Egg Toast",
        description="Crispy sourdough bread topped with creamy smashed avocado, soft poached eggs, and chili flakes.",
        prep_time_minutes=12,
        dietary_tags="vegetarian,quick,breakfast",
        ingredients_json=json.dumps([
            {"name": "Avocados", "quantity": "2", "category": "produce"},
            {"name": "Eggs", "quantity": "4", "category": "dairy"},
            {"name": "Sourdough Bread", "quantity": "1 loaf", "category": "bakery"},
            {"name": "Extra Virgin Olive Oil", "quantity": "1 bottle", "category": "pantry"},
            {"name": "Chili Flakes", "quantity": "1 jar", "category": "pantry"},
        ]),
        instructions="1. Toast the sourdough slices until golden.\n2. Mash avocados with lemon juice and salt.\n3. Poach eggs in simmering water for 3 minutes.\n4. Assemble toast, top with egg, and sprinkle chili flakes.",
    )

    r2 = Recipe(
        user_id=user_id,
        title="Mediterranean Quinoa Salad Bowl",
        description="Nutrient-dense warm quinoa bowl tossed with kalamata olives, crisp cucumbers, feta, and lemon oregano vinaigrette.",
        prep_time_minutes=20,
        dietary_tags="vegetarian,high-protein,gluten-free",
        ingredients_json=json.dumps([
            {"name": "Organic Quinoa", "quantity": "1 cup", "category": "pantry"},
            {"name": "Cherry Tomatoes", "quantity": "1 pint", "category": "produce"},
            {"name": "English Cucumbers", "quantity": "2", "category": "produce"},
            {"name": "Feta Cheese", "quantity": "1 block", "category": "dairy"},
            {"name": "Kalamata Olives", "quantity": "1 jar", "category": "pantry"},
            {"name": "Chickpeas", "quantity": "1 can", "category": "pantry"},
        ]),
        instructions="1. Cook quinoa according to package directions.\n2. Chop tomatoes and cucumbers.\n3. Mix ingredients in a large bowl, crumble feta over top, and drizzle with olive oil and lemon.",
    )

    r3 = Recipe(
        user_id=user_id,
        title="Herb-Crusted Wild Salmon with Asparagus",
        description="Fresh Atlantic salmon fillet seared with garlic, dill, and served with tender roasted asparagus.",
        prep_time_minutes=25,
        dietary_tags="high-protein,keto,seafood",
        ingredients_json=json.dumps([
            {"name": "Wild Salmon Fillets", "quantity": "2 fillets", "category": "meat"},
            {"name": "Fresh Asparagus", "quantity": "1 bunch", "category": "produce"},
            {"name": "Fresh Dill", "quantity": "1 bunch", "category": "produce"},
            {"name": "Garlic", "quantity": "1 bulb", "category": "produce"},
            {"name": "Lemons", "quantity": "2", "category": "produce"},
        ]),
        instructions="1. Preheat oven to 400°F (200°C).\n2. Season salmon fillets with salt, pepper, garlic, and fresh dill.\n3. Toss asparagus in olive oil and arrange on sheet pan.\n4. Bake salmon and asparagus together for 14-16 minutes.",
    )

    db.add_all([r1, r2, r3])
    db.commit()
    db.refresh(r1)
    db.refresh(r2)
    db.refresh(r3)

    # 2. Seed meal plans for today and tomorrow
    today = date.today()
    tomorrow = today + timedelta(days=1)
    day_after = today + timedelta(days=2)

    mp1 = MealPlan(user_id=user_id, date=today, meal_type="breakfast", recipe_id=r1.id, custom_meal_name=None, notes="Fuel for morning workout")
    mp2 = MealPlan(user_id=user_id, date=today, meal_type="lunch", recipe_id=r2.id, custom_meal_name=None, notes="Prep night before")
    mp3 = MealPlan(user_id=user_id, date=today, meal_type="dinner", recipe_id=r3.id, custom_meal_name=None, notes="Quick family dinner")
    mp4 = MealPlan(user_id=user_id, date=tomorrow, meal_type="breakfast", recipe_id=r1.id, custom_meal_name=None, notes=None)
    mp5 = MealPlan(user_id=user_id, date=tomorrow, meal_type="dinner", recipe_id=None, custom_meal_name="Grilled Chicken & Veggies", notes="Eat out or BBQ")

    db.add_all([mp1, mp2, mp3, mp4, mp5])
    db.commit()

    # 3. Seed grocery list
    groceries = [
        GroceryItem(user_id=user_id, item_name="Avocados", quantity="4 count", category="produce", estimated_cost=4.99, is_purchased=False),
        GroceryItem(user_id=user_id, item_name="Wild Salmon Fillets", quantity="2 count", category="meat", estimated_cost=14.50, is_purchased=False),
        GroceryItem(user_id=user_id, item_name="Organic Quinoa", quantity="1 bag", category="pantry", estimated_cost=5.49, is_purchased=True),
        GroceryItem(user_id=user_id, item_name="Eggs", quantity="1 dozen", category="dairy", estimated_cost=4.29, is_purchased=False),
        GroceryItem(user_id=user_id, item_name="Fresh Asparagus", quantity="1 bunch", category="produce", estimated_cost=3.99, is_purchased=False),
        GroceryItem(user_id=user_id, item_name="Greek Feta Cheese", quantity="1 pack", category="dairy", estimated_cost=4.79, is_purchased=False),
    ]
    db.add_all(groceries)
    db.commit()


def list_recipes(db: Session, user_id: int, tag: str | None = None) -> list[RecipeRead]:
    query = select(Recipe).where(Recipe.user_id == user_id).order_by(Recipe.title.asc())
    recipes = list(db.scalars(query).all())
    results = [RecipeRead.from_orm_model(r) for r in recipes]
    if tag:
        tag_lower = tag.lower().strip()
        results = [r for r in results if any(tag_lower in t.lower() for t in r.dietary_tags)]
    return results


def get_recipe(db: Session, user_id: int, recipe_id: int) -> RecipeRead | None:
    recipe = db.scalar(select(Recipe).where(Recipe.user_id == user_id, Recipe.id == recipe_id))
    if not recipe:
        return None
    return RecipeRead.from_orm_model(recipe)


def create_recipe(db: Session, user_id: int, payload: RecipeCreate) -> RecipeRead:
    ingredients_data = [item.model_dump() for item in payload.ingredients]
    recipe = Recipe(
        user_id=user_id,
        title=payload.title,
        description=payload.description,
        prep_time_minutes=payload.prep_time_minutes,
        ingredients_json=json.dumps(ingredients_data),
        instructions=payload.instructions,
        dietary_tags=",".join(payload.dietary_tags),
    )
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return RecipeRead.from_orm_model(recipe)


def delete_recipe(db: Session, user_id: int, recipe_id: int) -> bool:
    recipe = db.scalar(select(Recipe).where(Recipe.user_id == user_id, Recipe.id == recipe_id))
    if not recipe:
        return False
    db.delete(recipe)
    db.commit()
    return True


def list_meal_plans(
    db: Session,
    user_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[MealPlanRead]:
    query = select(MealPlan).where(MealPlan.user_id == user_id)
    if start_date:
        query = query.where(MealPlan.date >= start_date)
    if end_date:
        query = query.where(MealPlan.date <= end_date)
    query = query.order_by(MealPlan.date.asc(), MealPlan.id.asc())

    plans = list(db.scalars(query).all())
    result: list[MealPlanRead] = []
    for p in plans:
        recipe_title = p.recipe.title if p.recipe else p.custom_meal_name
        result.append(
            MealPlanRead(
                id=p.id,
                user_id=p.user_id,
                date=p.date,
                meal_type=p.meal_type,
                recipe_id=p.recipe_id,
                custom_meal_name=p.custom_meal_name,
                recipe_title=recipe_title,
                notes=p.notes,
                created_at=p.created_at,
            )
        )
    return result


def create_meal_plan(db: Session, user_id: int, payload: MealPlanCreate) -> MealPlanRead:
    recipe = None
    if payload.recipe_id:
        recipe = db.scalar(select(Recipe).where(Recipe.user_id == user_id, Recipe.id == payload.recipe_id))

    plan = MealPlan(
        user_id=user_id,
        date=payload.plan_date,
        meal_type=payload.meal_type,
        recipe_id=payload.recipe_id,
        custom_meal_name=payload.custom_meal_name or (recipe.title if recipe else None),
        notes=payload.notes,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)

    return MealPlanRead(
        id=plan.id,
        user_id=plan.user_id,
        date=plan.date,
        meal_type=plan.meal_type,
        recipe_id=plan.recipe_id,
        custom_meal_name=plan.custom_meal_name,
        recipe_title=recipe.title if recipe else plan.custom_meal_name,
        notes=plan.notes,
        created_at=plan.created_at,
    )


def delete_meal_plan(db: Session, user_id: int, plan_id: int) -> bool:
    plan = db.scalar(select(MealPlan).where(MealPlan.user_id == user_id, MealPlan.id == plan_id))
    if not plan:
        return False
    db.delete(plan)
    db.commit()
    return True


def list_grocery_items(
    db: Session,
    user_id: int,
    purchased: bool | None = None,
) -> list[GroceryItem]:
    query = select(GroceryItem).where(GroceryItem.user_id == user_id)
    if purchased is not None:
        query = query.where(GroceryItem.is_purchased == purchased)
    query = query.order_by(GroceryItem.is_purchased.asc(), GroceryItem.category.asc(), GroceryItem.item_name.asc())
    return list(db.scalars(query).all())


def get_grocery_summary(db: Session, user_id: int) -> GroceryListSummary:
    items = list_grocery_items(db, user_id)
    total = len(items)
    purchased = sum(1 for i in items if i.is_purchased)
    pending = total - purchased
    total_cost = sum(i.estimated_cost for i in items)

    categorized: dict[str, list[GroceryItemRead]] = {}
    for i in items:
        cat = i.category or "other"
        if cat not in categorized:
            categorized[cat] = []
        categorized[cat].append(GroceryItemRead.model_validate(i))

    return GroceryListSummary(
        total_items=total,
        purchased_items=purchased,
        pending_items=pending,
        estimated_total_cost=round(total_cost, 2),
        items_by_category=categorized,
    )


def add_grocery_item(db: Session, user_id: int, payload: GroceryItemCreate) -> GroceryItem:
    item = GroceryItem(
        user_id=user_id,
        item_name=payload.item_name,
        quantity=payload.quantity,
        category=payload.category,
        estimated_cost=payload.estimated_cost,
        source_meal_plan_id=payload.source_meal_plan_id,
        is_purchased=False,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def update_grocery_item(
    db: Session,
    user_id: int,
    item_id: int,
    payload: GroceryItemUpdate,
) -> GroceryItem | None:
    item = db.scalar(select(GroceryItem).where(GroceryItem.user_id == user_id, GroceryItem.id == item_id))
    if not item:
        return None
    if payload.item_name is not None:
        item.item_name = payload.item_name
    if payload.quantity is not None:
        item.quantity = payload.quantity
    if payload.category is not None:
        item.category = payload.category
    if payload.is_purchased is not None:
        item.is_purchased = payload.is_purchased
    if payload.estimated_cost is not None:
        item.estimated_cost = payload.estimated_cost

    db.commit()
    db.refresh(item)
    return item


def delete_grocery_item(db: Session, user_id: int, item_id: int) -> bool:
    item = db.scalar(select(GroceryItem).where(GroceryItem.user_id == user_id, GroceryItem.id == item_id))
    if not item:
        return False
    db.delete(item)
    db.commit()
    return True


def generate_grocery_from_plans(
    db: Session,
    user_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[GroceryItem]:
    plans = list_meal_plans(db, user_id, start_date=start_date, end_date=end_date)
    existing_items = {i.item_name.lower(): i for i in list_grocery_items(db, user_id)}

    new_items: list[GroceryItem] = []
    for plan in plans:
        if not plan.recipe_id:
            continue
        recipe = get_recipe(db, user_id, plan.recipe_id)
        if not recipe or not recipe.ingredients:
            continue

        for ing in recipe.ingredients:
            if ing.name.lower() not in existing_items:
                created = GroceryItem(
                    user_id=user_id,
                    item_name=ing.name,
                    quantity=ing.quantity,
                    category=ing.category,
                    estimated_cost=3.50,
                    source_meal_plan_id=plan.id,
                    is_purchased=False,
                )
                db.add(created)
                existing_items[ing.name.lower()] = created
                new_items.append(created)

    if new_items:
        db.commit()
        for it in new_items:
            db.refresh(it)
    return new_items
