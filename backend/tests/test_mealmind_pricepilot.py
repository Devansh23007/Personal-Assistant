from datetime import date, timedelta

from app.core.database import get_db
from app.modules.assistant.tools import ToolContext, run_tool
from app.modules.auth.models import User


def _get_auth_headers(client, email="meal_user@example.com", password="a-strong-password-123"):
    client.post("/api/auth/register", json={"email": email, "password": password})
    res = client.post("/api/auth/token", data={"username": email, "password": password})
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_mealmind_seeding_and_recipes(client):
    headers = _get_auth_headers(client, "meal_seed@example.com")

    # Seed recipes & list
    res = client.get("/api/mealmind/recipes", headers=headers)
    assert res.status_code == 200
    recipes = res.json()
    assert len(recipes) >= 3
    titles = [r["title"] for r in recipes]
    assert any("Salmon" in t for t in titles)
    assert any("Avocado" in t for t in titles)

    # Filter by tag
    tag_res = client.get("/api/mealmind/recipes?tag=keto", headers=headers)
    assert tag_res.status_code == 200
    keto_recipes = tag_res.json()
    assert len(keto_recipes) >= 1
    assert "Salmon" in keto_recipes[0]["title"]


def test_mealmind_create_recipe_and_meal_plan(client):
    headers = _get_auth_headers(client, "meal_create@example.com")

    # Create new recipe
    create_rec_res = client.post(
        "/api/mealmind/recipes",
        headers=headers,
        json={
            "title": "Protein Power Smoothie",
            "description": "Banana, spinach, whey protein, and almond milk smoothie.",
            "prep_time_minutes": 5,
            "ingredients": [
                {"name": "Bananas", "quantity": "2", "category": "produce"},
                {"name": "Baby Spinach", "quantity": "1 cup", "category": "produce"},
                {"name": "Almond Milk", "quantity": "1 carton", "category": "dairy"},
            ],
            "instructions": "Blend all ingredients until smooth.",
            "dietary_tags": ["high-protein", "quick", "vegan"],
        },
    )
    assert create_rec_res.status_code == 201
    new_rec = create_rec_res.json()
    assert new_rec["title"] == "Protein Power Smoothie"
    rec_id = new_rec["id"]

    # Plan meal with recipe
    today_str = date.today().isoformat()
    plan_res = client.post(
        "/api/mealmind/plans",
        headers=headers,
        json={
            "date": today_str,
            "meal_type": "breakfast",
            "recipe_id": rec_id,
            "notes": "Quick morning breakfast",
        },
    )
    assert plan_res.status_code == 201
    plan = plan_res.json()
    assert plan["recipe_id"] == rec_id
    assert "Protein Power Smoothie" in plan["recipe_title"]


def test_mealmind_grocery_list_and_generation(client):
    headers = _get_auth_headers(client, "meal_grocery@example.com")

    # Check grocery list
    res = client.get("/api/mealmind/grocery", headers=headers)
    assert res.status_code == 200
    groceries = res.json()
    assert len(groceries) >= 4

    # Summary
    summary_res = client.get("/api/mealmind/grocery/summary", headers=headers)
    assert summary_res.status_code == 200
    summary = summary_res.json()
    assert summary["total_items"] >= 4
    assert summary["estimated_total_cost"] > 0
    assert "produce" in summary["items_by_category"]

    # Add item
    add_res = client.post(
        "/api/mealmind/grocery",
        headers=headers,
        json={
            "item_name": "Greek Yogurt",
            "quantity": "32 oz tub",
            "category": "dairy",
            "estimated_cost": 5.25,
        },
    )
    assert add_res.status_code == 201
    item_id = add_res.json()["id"]

    # Mark as purchased
    patch_res = client.patch(
        f"/api/mealmind/grocery/{item_id}",
        headers=headers,
        json={"is_purchased": True},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["is_purchased"] is True

    # Generate grocery from plans
    gen_res = client.post("/api/mealmind/grocery/generate-from-plans", headers=headers)
    assert gen_res.status_code == 200


def test_pricepilot_comparison_and_basket(client):
    headers = _get_auth_headers(client, "price_user@example.com")

    # List prices
    prices_res = client.get("/api/pricepilot/prices", headers=headers)
    assert prices_res.status_code == 200
    prices = prices_res.json()
    assert len(prices) >= 15

    # Compare prices for avocados
    compare_res = client.get("/api/pricepilot/compare?q=Avocados", headers=headers)
    assert compare_res.status_code == 200
    comparison = compare_res.json()
    assert comparison["matched_item"] == "Avocados"
    assert comparison["lowest_price"] < comparison["highest_price"]
    assert comparison["potential_savings"] > 0
    assert len(comparison["offers"]) >= 3
    assert any(o["is_best_price"] for o in comparison["offers"])

    # Basket analysis
    basket_res = client.post(
        "/api/pricepilot/basket-analysis",
        headers=headers,
        json={"items": ["Avocados", "Eggs", "Wild Salmon Fillets"]},
    )
    assert basket_res.status_code == 200
    basket = basket_res.json()
    assert len(basket["store_breakdowns"]) >= 3
    assert basket["lowest_total_cost"] > 0
    assert basket["best_overall_store"] in [b["store_name"] for b in basket["store_breakdowns"]]


def test_mealmind_pricepilot_tools_direct(client):
    headers = _get_auth_headers(client, "meal_tools@example.com")
    db = next(client.app.dependency_overrides[get_db]())
    user = db.query(User).filter(User.email == "meal_tools@example.com").first()
    context = ToolContext(user=user, db=db)

    # 1. plan_meals tool
    meals_out = run_tool("plan_meals", {}, context=context)
    assert "Upcoming Meal Plan" in meals_out

    # 2. get_grocery_list tool
    groc_out = run_tool("get_grocery_list", {}, context=context)
    assert "Grocery List" in groc_out

    # 3. add_grocery_item tool
    add_out = run_tool("add_grocery_item", {"item_name": "Dark Chocolate", "quantity": "2 bars", "category": "pantry"}, context=context)
    assert "Dark Chocolate" in add_out

    # 4. search_product_prices tool
    price_out = run_tool("search_product_prices", {"item_name": "Salmon"}, context=context)
    assert "Price Comparison" in price_out
    assert "Best deal" in price_out
