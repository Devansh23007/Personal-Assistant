import { FormEvent, useEffect, useState } from "react";

type Ingredient = {
  name: string;
  quantity: string;
  category: string;
};

type Recipe = {
  id: number;
  user_id: number;
  title: string;
  description: string | null;
  prep_time_minutes: number;
  ingredients: Ingredient[];
  instructions: string;
  dietary_tags: string[];
  created_at: string;
};

type MealPlan = {
  id: number;
  user_id: number;
  date: string;
  meal_type: string;
  recipe_id: number | null;
  custom_meal_name: string | null;
  recipe_title: string | null;
  notes: string | null;
  created_at: string;
};

type GroceryItem = {
  id: number;
  user_id: number;
  item_name: string;
  quantity: string;
  category: string;
  is_purchased: boolean;
  estimated_cost: number;
  source_meal_plan_id: number | null;
  created_at: string;
};

type GrocerySummary = {
  total_items: number;
  purchased_items: number;
  pending_items: number;
  estimated_total_cost: number;
  items_by_category: Record<string, GroceryItem[]>;
};

export function MealMindView({
  token,
  onCheckPrices,
}: {
  token: string;
  onCheckPrices?: (itemName: string) => void;
}) {
  const [activeTab, setActiveTab] = useState<"planner" | "recipes" | "grocery">("planner");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [successMsg, setSuccessMsg] = useState("");

  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [mealPlans, setMealPlans] = useState<MealPlan[]>([]);
  const [grocerySummary, setGrocerySummary] = useState<GrocerySummary | null>(null);

  // Forms
  const [showAddPlan, setShowAddPlan] = useState(false);
  const [planDate, setPlanDate] = useState(() => new Date().toISOString().split("T")[0]);
  const [planMealType, setPlanMealType] = useState("dinner");
  const [planRecipeId, setPlanRecipeId] = useState<string>("");
  const [planCustomName, setPlanCustomName] = useState("");
  const [planNotes, setPlanNotes] = useState("");

  const [showAddRecipe, setShowAddRecipe] = useState(false);
  const [newRecTitle, setNewRecTitle] = useState("");
  const [newRecDesc, setNewRecDesc] = useState("");
  const [newRecTime, setNewRecTime] = useState(20);
  const [newRecInstructions, setNewRecInstructions] = useState("");
  const [newRecTags, setNewRecTags] = useState("");
  const [newRecIngredients, setNewRecIngredients] = useState("Avocado (2 count, produce)\nEggs (4 count, dairy)");

  const [showAddGrocery, setShowAddGrocery] = useState(false);
  const [newGrocName, setNewGrocName] = useState("");
  const [newGrocQty, setNewGrocQty] = useState("1");
  const [newGrocCat, setNewGrocCat] = useState("produce");
  const [newGrocCost, setNewGrocCost] = useState(3.5);

  const [viewingRecipe, setViewingRecipe] = useState<Recipe | null>(null);

  useEffect(() => {
    fetchData();
  }, [token]);

  async function fetchData() {
    setLoading(true);
    setError("");
    try {
      const [recRes, planRes, grocRes] = await Promise.all([
        fetch("/api/mealmind/recipes", { headers: { Authorization: `Bearer ${token}` } }),
        fetch("/api/mealmind/plans", { headers: { Authorization: `Bearer ${token}` } }),
        fetch("/api/mealmind/grocery/summary", { headers: { Authorization: `Bearer ${token}` } }),
      ]);

      if (recRes.ok) setRecipes(await recRes.json());
      if (planRes.ok) setMealPlans(await planRes.json());
      if (grocRes.ok) setGrocerySummary(await grocRes.json());
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error loading MealMind data");
    } finally {
      setLoading(false);
    }
  }

  async function handleCreatePlan(e: FormEvent) {
    e.preventDefault();
    setError("");
    setSuccessMsg("");
    try {
      const res = await fetch("/api/mealmind/plans", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          date: planDate,
          meal_type: planMealType,
          recipe_id: planRecipeId ? parseInt(planRecipeId) : null,
          custom_meal_name: planCustomName || undefined,
          notes: planNotes || undefined,
        }),
      });
      if (!res.ok) throw new Error("Failed to add meal plan");
      const created = await res.json();
      setMealPlans((prev) => [...prev, created]);
      setSuccessMsg("Meal added to your schedule!");
      setShowAddPlan(false);
      setPlanCustomName("");
      setPlanNotes("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Create plan error");
    }
  }

  async function handleDeletePlan(id: number) {
    try {
      const res = await fetch(`/api/mealmind/plans/${id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Failed to delete meal plan");
      setMealPlans((prev) => prev.filter((p) => p.id !== id));
      setSuccessMsg("Meal plan removed.");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Delete plan error");
    }
  }

  async function handleGenerateGroceriesFromPlans() {
    setError("");
    setSuccessMsg("");
    try {
      const res = await fetch("/api/mealmind/grocery/generate-from-plans", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Failed to generate groceries");
      const newItems = await res.json();
      setSuccessMsg(`Added ${newItems.length} ingredients to your grocery list!`);
      const updatedGroc = await fetch("/api/mealmind/grocery/summary", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (updatedGroc.ok) setGrocerySummary(await updatedGroc.json());
      setActiveTab("grocery");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Generation error");
    }
  }

  async function handleTogglePurchased(item: GroceryItem) {
    try {
      const res = await fetch(`/api/mealmind/grocery/${item.id}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ is_purchased: !item.is_purchased }),
      });
      if (!res.ok) throw new Error("Failed to update status");
      const updatedGroc = await fetch("/api/mealmind/grocery/summary", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (updatedGroc.ok) setGrocerySummary(await updatedGroc.json());
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Update grocery error");
    }
  }

  async function handleDeleteGrocery(id: number) {
    try {
      const res = await fetch(`/api/mealmind/grocery/${id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Failed to delete item");
      const updatedGroc = await fetch("/api/mealmind/grocery/summary", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (updatedGroc.ok) setGrocerySummary(await updatedGroc.json());
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Delete grocery error");
    }
  }

  async function handleCreateGrocery(e: FormEvent) {
    e.preventDefault();
    setError("");
    setSuccessMsg("");
    try {
      const res = await fetch("/api/mealmind/grocery", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          item_name: newGrocName,
          quantity: newGrocQty,
          category: newGrocCat,
          estimated_cost: newGrocCost,
        }),
      });
      if (!res.ok) throw new Error("Failed to add grocery item");
      setSuccessMsg("Item added to grocery list!");
      setShowAddGrocery(false);
      setNewGrocName("");
      const updatedGroc = await fetch("/api/mealmind/grocery/summary", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (updatedGroc.ok) setGrocerySummary(await updatedGroc.json());
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Add grocery error");
    }
  }

  async function handleCreateRecipe(e: FormEvent) {
    e.preventDefault();
    setError("");
    setSuccessMsg("");
    try {
      const parsedIngredients = newRecIngredients
        .split("\n")
        .map((l) => l.trim())
        .filter(Boolean)
        .map((line) => {
          const match = line.match(/^([^(]+)(?:\(([^,]+)(?:,\s*([^)]+))?\))?/);
          return {
            name: match ? match[1].trim() : line,
            quantity: match && match[2] ? match[2].trim() : "1",
            category: match && match[3] ? match[3].trim() : "produce",
          };
        });

      const res = await fetch("/api/mealmind/recipes", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          title: newRecTitle,
          description: newRecDesc || undefined,
          prep_time_minutes: newRecTime,
          instructions: newRecInstructions,
          dietary_tags: newRecTags.split(",").map((t) => t.trim()).filter(Boolean),
          ingredients: parsedIngredients,
        }),
      });
      if (!res.ok) throw new Error("Failed to save recipe");
      const created = await res.json();
      setRecipes((prev) => [created, ...prev]);
      setSuccessMsg("Recipe created!");
      setShowAddRecipe(false);
      setNewRecTitle("");
      setNewRecDesc("");
      setNewRecInstructions("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Create recipe error");
    }
  }

  return (
    <div className="mealmind-view">
      <div className="view-header">
        <div>
          <h2>MealMind</h2>
          <p className="subtitle">Weekly meal planning, nutritious recipe catalog & smart grocery lists</p>
        </div>
        <div className="header-actions">
          {activeTab === "planner" && (
            <>
              <button className="btn-accent" onClick={handleGenerateGroceriesFromPlans}>
                ⚡ Auto-Sync to Grocery List
              </button>
              <button className="btn-primary" onClick={() => setShowAddPlan(!showAddPlan)}>
                {showAddPlan ? "Cancel" : "+ Plan Meal"}
              </button>
            </>
          )}
          {activeTab === "recipes" && (
            <button className="btn-primary" onClick={() => setShowAddRecipe(!showAddRecipe)}>
              {showAddRecipe ? "Cancel" : "+ New Recipe"}
            </button>
          )}
          {activeTab === "grocery" && (
            <button className="btn-primary" onClick={() => setShowAddGrocery(!showAddGrocery)}>
              {showAddGrocery ? "Cancel" : "+ Add Item"}
            </button>
          )}
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}
      {successMsg && <div className="success-banner">{successMsg}</div>}

      {/* Tabs */}
      <div className="tab-bar">
        <button
          className={`tab-btn ${activeTab === "planner" ? "active" : ""}`}
          onClick={() => setActiveTab("planner")}
        >
          📅 Meal Schedule ({mealPlans.length})
        </button>
        <button
          className={`tab-btn ${activeTab === "recipes" ? "active" : ""}`}
          onClick={() => setActiveTab("recipes")}
        >
          📖 Recipes ({recipes.length})
        </button>
        <button
          className={`tab-btn ${activeTab === "grocery" ? "active" : ""}`}
          onClick={() => setActiveTab("grocery")}
        >
          🛒 Grocery List ({grocerySummary?.total_items || 0})
        </button>
      </div>

      {/* PLANNER TAB */}
      {activeTab === "planner" && (
        <div className="planner-tab">
          {showAddPlan && (
            <form className="add-plan-form" onSubmit={handleCreatePlan}>
              <h3>Schedule a Meal</h3>
              <div className="form-row">
                <div className="form-group">
                  <label>Date</label>
                  <input
                    type="date"
                    required
                    value={planDate}
                    onChange={(e) => setPlanDate(e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label>Meal Time</label>
                  <select
                    value={planMealType}
                    onChange={(e) => setPlanMealType(e.target.value)}
                  >
                    <option value="breakfast">Breakfast</option>
                    <option value="lunch">Lunch</option>
                    <option value="dinner">Dinner</option>
                    <option value="snack">Snack</option>
                  </select>
                </div>
                <div className="form-group">
                  <label>Select Recipe</label>
                  <select
                    value={planRecipeId}
                    onChange={(e) => setPlanRecipeId(e.target.value)}
                  >
                    <option value="">-- Or enter custom meal name --</option>
                    {recipes.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.title} ({r.prep_time_minutes}m)
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {!planRecipeId && (
                <div className="form-group">
                  <label>Custom Meal Name</label>
                  <input
                    type="text"
                    placeholder="e.g., Grilled Chicken & Brown Rice"
                    value={planCustomName}
                    onChange={(e) => setPlanCustomName(e.target.value)}
                  />
                </div>
              )}

              <div className="form-group">
                <label>Notes (optional)</label>
                <input
                  type="text"
                  placeholder="e.g., Double portion for lunch tomorrow"
                  value={planNotes}
                  onChange={(e) => setPlanNotes(e.target.value)}
                />
              </div>

              <button type="submit" className="btn-primary">Add to Schedule</button>
            </form>
          )}

          {loading ? (
            <p className="loading-notice">Loading meal plan…</p>
          ) : mealPlans.length === 0 ? (
            <p className="empty-notice">No meals planned yet. Click &quot;+ Plan Meal&quot; above!</p>
          ) : (
            <div className="meal-plans-timeline">
              {mealPlans.map((plan) => (
                <div key={plan.id} className="meal-plan-card">
                  <div className="plan-badge-col">
                    <span className="meal-type-badge">{plan.meal_type.toUpperCase()}</span>
                    <span className="meal-date-str">{plan.date}</span>
                  </div>
                  <div className="plan-details-col">
                    <h4>{plan.recipe_title || plan.custom_meal_name}</h4>
                    {plan.notes && <p className="plan-notes">{plan.notes}</p>}
                  </div>
                  <div className="plan-actions-col">
                    {plan.recipe_id && (
                      <button
                        className="btn-secondary btn-sm"
                        onClick={() => {
                          const r = recipes.find((x) => x.id === plan.recipe_id);
                          if (r) setViewingRecipe(r);
                        }}
                      >
                        View Recipe
                      </button>
                    )}
                    <button
                      className="btn-danger btn-sm"
                      onClick={() => handleDeletePlan(plan.id)}
                    >
                      Remove
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* RECIPES TAB */}
      {activeTab === "recipes" && (
        <div className="recipes-tab">
          {showAddRecipe && (
            <form className="add-recipe-form" onSubmit={handleCreateRecipe}>
              <h3>Create Custom Recipe</h3>
              <div className="form-row">
                <div className="form-group" style={{ flex: 3 }}>
                  <label>Recipe Title</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g., Slow Cooker Chicken Fajitas"
                    value={newRecTitle}
                    onChange={(e) => setNewRecTitle(e.target.value)}
                  />
                </div>
                <div className="form-group" style={{ flex: 1 }}>
                  <label>Prep Time (mins)</label>
                  <input
                    type="number"
                    value={newRecTime}
                    onChange={(e) => setNewRecTime(parseInt(e.target.value) || 15)}
                  />
                </div>
              </div>
              <div className="form-group">
                <label>Description</label>
                <input
                  type="text"
                  placeholder="Short description of dish"
                  value={newRecDesc}
                  onChange={(e) => setNewRecDesc(e.target.value)}
                />
              </div>
              <div className="form-group">
                <label>Dietary Tags (comma-separated)</label>
                <input
                  type="text"
                  placeholder="e.g., high-protein, gluten-free, quick"
                  value={newRecTags}
                  onChange={(e) => setNewRecTags(e.target.value)}
                />
              </div>
              <div className="form-group">
                <label>Ingredients (one per line, format: Name (quantity, category))</label>
                <textarea
                  rows={4}
                  value={newRecIngredients}
                  onChange={(e) => setNewRecIngredients(e.target.value)}
                />
              </div>
              <div className="form-group">
                <label>Cooking Instructions</label>
                <textarea
                  rows={4}
                  required
                  placeholder="Step by step preparation guide..."
                  value={newRecInstructions}
                  onChange={(e) => setNewRecInstructions(e.target.value)}
                />
              </div>
              <button type="submit" className="btn-primary">Save Recipe</button>
            </form>
          )}

          <div className="recipes-grid">
            {recipes.map((recipe) => (
              <div key={recipe.id} className="recipe-card">
                <div className="recipe-top">
                  <h4>{recipe.title}</h4>
                  <span className="prep-time-badge">⏱ {recipe.prep_time_minutes} min</span>
                </div>
                {recipe.description && <p className="recipe-desc">{recipe.description}</p>}

                <div className="recipe-tags">
                  {recipe.dietary_tags.map((t, i) => (
                    <span key={i} className="diet-tag">#{t}</span>
                  ))}
                </div>

                <div className="recipe-footer">
                  <span className="ingredient-count">{recipe.ingredients.length} ingredients</span>
                  <button
                    className="btn-secondary btn-sm"
                    onClick={() => setViewingRecipe(recipe)}
                  >
                    View Details
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* GROCERY LIST TAB */}
      {activeTab === "grocery" && (
        <div className="grocery-tab">
          {grocerySummary && (
            <div className="grocery-metrics-row">
              <div className="groc-metric">
                <span className="label">Total Items</span>
                <strong>{grocerySummary.total_items}</strong>
              </div>
              <div className="groc-metric">
                <span className="label">Need to Buy</span>
                <strong className="text-warning">{grocerySummary.pending_items}</strong>
              </div>
              <div className="groc-metric">
                <span className="label">In Cart / Pantry</span>
                <strong className="text-success">{grocerySummary.purchased_items}</strong>
              </div>
              <div className="groc-metric">
                <span className="label">Estimated Total</span>
                <strong>${grocerySummary.estimated_total_cost.toFixed(2)}</strong>
              </div>
            </div>
          )}

          {showAddGrocery && (
            <form className="add-grocery-form" onSubmit={handleCreateGrocery}>
              <h3>Add Grocery Item</h3>
              <div className="form-row">
                <div className="form-group" style={{ flex: 2 }}>
                  <label>Item Name</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g., Organic Honey"
                    value={newGrocName}
                    onChange={(e) => setNewGrocName(e.target.value)}
                  />
                </div>
                <div className="form-group" style={{ flex: 1 }}>
                  <label>Quantity</label>
                  <input
                    type="text"
                    value={newGrocQty}
                    onChange={(e) => setNewGrocQty(e.target.value)}
                  />
                </div>
                <div className="form-group" style={{ flex: 1 }}>
                  <label>Category</label>
                  <select
                    value={newGrocCat}
                    onChange={(e) => setNewGrocCat(e.target.value)}
                  >
                    <option value="produce">Produce</option>
                    <option value="dairy">Dairy</option>
                    <option value="meat">Meat & Seafood</option>
                    <option value="pantry">Pantry</option>
                    <option value="bakery">Bakery</option>
                    <option value="other">Other</option>
                  </select>
                </div>
                <div className="form-group" style={{ flex: 1 }}>
                  <label>Est. Cost ($)</label>
                  <input
                    type="number"
                    step="0.01"
                    value={newGrocCost}
                    onChange={(e) => setNewGrocCost(parseFloat(e.target.value) || 0)}
                  />
                </div>
              </div>
              <button type="submit" className="btn-primary">Add Item</button>
            </form>
          )}

          {grocerySummary && Object.keys(grocerySummary.items_by_category).length === 0 ? (
            <p className="empty-notice">Your grocery list is empty. Add items or generate from meal plans!</p>
          ) : (
            <div className="grocery-category-groups">
              {grocerySummary &&
                Object.entries(grocerySummary.items_by_category).map(([category, items]) => (
                  <div key={category} className="grocery-category-block">
                    <h4 className="category-heading">{category.toUpperCase()} ({items.length})</h4>
                    <div className="grocery-items-table">
                      {items.map((item) => (
                        <div key={item.id} className={`grocery-row ${item.is_purchased ? "purchased" : ""}`}>
                          <input
                            type="checkbox"
                            checked={item.is_purchased}
                            onChange={() => handleTogglePurchased(item)}
                          />
                          <div className="groc-name-col">
                            <strong>{item.item_name}</strong>
                            <span className="groc-qty">{item.quantity}</span>
                          </div>
                          <span className="groc-cost">${item.estimated_cost.toFixed(2)}</span>
                          <div className="groc-actions">
                            {onCheckPrices && (
                              <button
                                className="btn-link"
                                title="Check store prices with PricePilot"
                                onClick={() => onCheckPrices(item.item_name)}
                              >
                                🔍 Price Check
                              </button>
                            )}
                            <button
                              className="btn-remove"
                              onClick={() => handleDeleteGrocery(item.id)}
                            >
                              ✕
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
            </div>
          )}
        </div>
      )}

      {/* View Recipe Modal */}
      {viewingRecipe && (
        <div className="modal-overlay" onClick={() => setViewingRecipe(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>{viewingRecipe.title}</h3>
              <button className="modal-close" onClick={() => setViewingRecipe(null)}>✕</button>
            </div>
            <div className="modal-meta">
              <span>⏱ {viewingRecipe.prep_time_minutes} min prep</span>
              <span>🏷 {viewingRecipe.dietary_tags.join(", ")}</span>
            </div>
            <div className="recipe-modal-body">
              <h4>Ingredients</h4>
              <ul className="ingredients-list">
                {viewingRecipe.ingredients.map((ing, i) => (
                  <li key={i}>
                    <strong>{ing.name}</strong> — {ing.quantity} ({ing.category})
                    {onCheckPrices && (
                      <button
                        className="btn-link-sm"
                        onClick={() => {
                          setViewingRecipe(null);
                          onCheckPrices(ing.name);
                        }}
                      >
                        Check Price
                      </button>
                    )}
                  </li>
                ))}
              </ul>
              <h4>Preparation Instructions</h4>
              <pre className="instructions-body">{viewingRecipe.instructions}</pre>
            </div>
            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setViewingRecipe(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
