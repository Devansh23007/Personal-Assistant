from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.mealmind.schemas import (
    GroceryItemCreate,
    GroceryItemRead,
    GroceryItemUpdate,
    GroceryListSummary,
    MealPlanCreate,
    MealPlanRead,
    RecipeCreate,
    RecipeRead,
)
from app.modules.mealmind.service import (
    add_grocery_item,
    create_meal_plan,
    create_recipe,
    delete_grocery_item,
    delete_meal_plan,
    delete_recipe,
    generate_grocery_from_plans,
    get_grocery_summary,
    get_recipe,
    list_grocery_items,
    list_meal_plans,
    list_recipes,
    seed_demo_mealmind_if_empty,
    update_grocery_item,
)

router = APIRouter(prefix="/mealmind", tags=["mealmind"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


# --- Recipes ---
@router.get("/recipes", response_model=list[RecipeRead])
def get_all_recipes(
    current_user: CurrentUser,
    db: DbSession,
    tag: str | None = Query(default=None),
) -> list[RecipeRead]:
    seed_demo_mealmind_if_empty(db, current_user.id)
    return list_recipes(db, current_user.id, tag=tag)


@router.post("/recipes", response_model=RecipeRead, status_code=status.HTTP_201_CREATED)
def add_new_recipe(
    payload: RecipeCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> RecipeRead:
    return create_recipe(db, current_user.id, payload)


@router.get("/recipes/{recipe_id}", response_model=RecipeRead)
def get_single_recipe(recipe_id: int, current_user: CurrentUser, db: DbSession) -> RecipeRead:
    recipe = get_recipe(db, current_user.id, recipe_id)
    if not recipe:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found")
    return recipe


@router.delete("/recipes/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_recipe(recipe_id: int, current_user: CurrentUser, db: DbSession) -> None:
    deleted = delete_recipe(db, current_user.id, recipe_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found")


# --- Meal Plans ---
@router.get("/plans", response_model=list[MealPlanRead])
def get_plans(
    current_user: CurrentUser,
    db: DbSession,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
) -> list[MealPlanRead]:
    seed_demo_mealmind_if_empty(db, current_user.id)
    return list_meal_plans(db, current_user.id, start_date=start_date, end_date=end_date)


@router.post("/plans", response_model=MealPlanRead, status_code=status.HTTP_201_CREATED)
def add_meal_plan(
    payload: MealPlanCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> MealPlanRead:
    return create_meal_plan(db, current_user.id, payload)


@router.delete("/plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_meal_plan(plan_id: int, current_user: CurrentUser, db: DbSession) -> None:
    deleted = delete_meal_plan(db, current_user.id, plan_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meal plan not found")


# --- Grocery List ---
@router.get("/grocery", response_model=list[GroceryItemRead])
def get_groceries(
    current_user: CurrentUser,
    db: DbSession,
    purchased: bool | None = Query(default=None),
) -> list[GroceryItemRead]:
    seed_demo_mealmind_if_empty(db, current_user.id)
    items = list_grocery_items(db, current_user.id, purchased=purchased)
    return [GroceryItemRead.model_validate(i) for i in items]


@router.get("/grocery/summary", response_model=GroceryListSummary)
def get_grocery_stats(current_user: CurrentUser, db: DbSession) -> GroceryListSummary:
    seed_demo_mealmind_if_empty(db, current_user.id)
    return get_grocery_summary(db, current_user.id)


@router.post("/grocery", response_model=GroceryItemRead, status_code=status.HTTP_201_CREATED)
def add_grocery(
    payload: GroceryItemCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> GroceryItemRead:
    item = add_grocery_item(db, current_user.id, payload)
    return GroceryItemRead.model_validate(item)


@router.patch("/grocery/{item_id}", response_model=GroceryItemRead)
def edit_grocery(
    item_id: int,
    payload: GroceryItemUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> GroceryItemRead:
    item = update_grocery_item(db, current_user.id, item_id, payload)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grocery item not found")
    return GroceryItemRead.model_validate(item)


@router.delete("/grocery/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_grocery(item_id: int, current_user: CurrentUser, db: DbSession) -> None:
    deleted = delete_grocery_item(db, current_user.id, item_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grocery item not found")


@router.post("/grocery/generate-from-plans", response_model=list[GroceryItemRead])
def generate_groceries(
    current_user: CurrentUser,
    db: DbSession,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
) -> list[GroceryItemRead]:
    new_items = generate_grocery_from_plans(db, current_user.id, start_date=start_date, end_date=end_date)
    return [GroceryItemRead.model_validate(i) for i in new_items]
