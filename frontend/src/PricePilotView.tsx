import { FormEvent, useEffect, useState } from "react";

type StoreOffer = {
  store_name: string;
  price: number;
  unit: string;
  in_stock: boolean;
  deal_description: string | null;
  is_best_price: boolean;
};

type ProductPriceComparison = {
  query: string;
  matched_item: string;
  category: string;
  cheapest_store: string;
  lowest_price: number;
  highest_price: number;
  potential_savings: number;
  offers: StoreOffer[];
};

type BasketStoreEstimate = {
  store_name: string;
  total_cost: number;
  items_found: number;
  total_requested: number;
  missing_items: string[];
};

type BasketComparison = {
  items_requested: string[];
  best_overall_store: string;
  lowest_total_cost: number;
  highest_total_cost: number;
  store_breakdowns: BasketStoreEstimate[];
};

type ProductPrice = {
  id: number;
  item_name: string;
  category: string;
  store_name: string;
  price: number;
  unit: string;
  in_stock: boolean;
  deal_description: string | null;
  last_updated_at: string;
};

export function PricePilotView({
  token,
  initialSearchQuery,
}: {
  token: string;
  initialSearchQuery?: string | null;
}) {
  const [searchQuery, setSearchQuery] = useState(initialSearchQuery || "Avocados");
  const [comparison, setComparison] = useState<ProductPriceComparison | null>(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");

  // Basket Analysis
  const [basketInput, setBasketInput] = useState("Avocados, Eggs, Wild Salmon Fillets, Fresh Asparagus, Greek Feta Cheese");
  const [basketResult, setBasketResult] = useState<BasketComparison | null>(null);
  const [analyzingBasket, setAnalyzingBasket] = useState(false);

  // Catalog
  const [catalog, setCatalog] = useState<ProductPrice[]>([]);
  const [catalogCategory, setCatalogCategory] = useState<string>("");

  useEffect(() => {
    if (initialSearchQuery) {
      setSearchQuery(initialSearchQuery);
      fetchComparison(initialSearchQuery);
    } else {
      fetchComparison("Avocados");
    }
    fetchCatalog();
  }, [token, initialSearchQuery]);

  async function fetchComparison(query: string) {
    if (!query.trim()) return;
    setSearching(true);
    setError("");
    try {
      const res = await fetch(`/api/pricepilot/compare?q=${encodeURIComponent(query)}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        if (res.status === 404) {
          setComparison(null);
          setError(`No store price records found for "${query}". Try "Salmon", "Eggs", "Avocados", or "Quinoa".`);
          return;
        }
        throw new Error("Price comparison lookup failed");
      }
      const data = await res.json();
      setComparison(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Lookup error");
    } finally {
      setSearching(false);
    }
  }

  async function handleSearch(e: FormEvent) {
    e.preventDefault();
    fetchComparison(searchQuery);
  }

  async function handleAnalyzeBasket(e: FormEvent) {
    e.preventDefault();
    const items = basketInput.split(",").map((i) => i.trim()).filter(Boolean);
    if (items.length === 0) return;
    setAnalyzingBasket(true);
    setError("");
    try {
      const res = await fetch("/api/pricepilot/basket-analysis", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ items }),
      });
      if (!res.ok) throw new Error("Basket analysis failed");
      const data = await res.json();
      setBasketResult(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Basket analysis error");
    } finally {
      setAnalyzingBasket(false);
    }
  }

  async function fetchCatalog(category?: string) {
    try {
      const url = category
        ? `/api/pricepilot/prices?category=${encodeURIComponent(category)}`
        : "/api/pricepilot/prices";
      const res = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setCatalog(await res.json());
    } catch {
      // ignore
    }
  }

  return (
    <div className="pricepilot-view">
      <div className="view-header">
        <div>
          <h2>PricePilot</h2>
          <p className="subtitle">Cross-store grocery price comparison, deals finder & basket optimization</p>
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {/* Live Price Search */}
      <div className="search-section">
        <form onSubmit={handleSearch} className="rag-search-bar">
          <input
            type="text"
            placeholder="Search price across stores (e.g., 'Salmon', 'Avocados', 'Eggs', 'Olive Oil')..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          <button type="submit" className="btn-primary" disabled={searching}>
            {searching ? "Searching Stores…" : "Compare Prices"}
          </button>
        </form>

        {comparison && (
          <div className="comparison-card">
            <div className="comparison-header">
              <div>
                <span className="comp-category-tag">{comparison.category.toUpperCase()}</span>
                <h3>{comparison.matched_item}</h3>
              </div>
              <div className="savings-badge">
                <span className="best-label">Best Deal at</span>
                <strong>{comparison.cheapest_store}</strong>
                <span className="savings-val">Save up to ${comparison.potential_savings.toFixed(2)}</span>
              </div>
            </div>

            <div className="store-offers-grid">
              {comparison.offers.map((offer, idx) => (
                <div key={idx} className={`store-offer-card ${offer.is_best_price ? "best-deal" : ""}`}>
                  {offer.is_best_price && <span className="best-deal-ribbon">⭐ LOWEST PRICE</span>}
                  <h4 className="store-name">{offer.store_name}</h4>
                  <div className="store-price-row">
                    <span className="currency">$</span>
                    <span className="price-val">{offer.price.toFixed(2)}</span>
                    <span className="price-unit">/{offer.unit}</span>
                  </div>
                  {offer.deal_description && (
                    <span className="deal-pill">{offer.deal_description}</span>
                  )}
                  <span className={`stock-status ${offer.in_stock ? "in-stock" : "out-of-stock"}`}>
                    {offer.in_stock ? "✓ In Stock" : "Out of Stock"}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Basket Optimizer Section */}
      <div className="basket-optimizer-section">
        <div className="section-title-row">
          <h3>🛒 Smart Grocery Basket Optimizer</h3>
          <span className="subtitle">Find which single store gives you the lowest total bill for your entire shopping list</span>
        </div>

        <form onSubmit={handleAnalyzeBasket} className="basket-form">
          <label>Enter items to compare across stores (comma-separated):</label>
          <div className="basket-input-row">
            <input
              type="text"
              value={basketInput}
              onChange={(e) => setBasketInput(e.target.value)}
              placeholder="e.g., Avocados, Eggs, Quinoa, Salmon"
            />
            <button type="submit" className="btn-accent" disabled={analyzingBasket}>
              {analyzingBasket ? "Calculating…" : "⚡ Optimize Basket"}
            </button>
          </div>
        </form>

        {basketResult && (
          <div className="basket-results-grid">
            {basketResult.store_breakdowns.map((store, i) => {
              const isBest = store.store_name === basketResult.best_overall_store;
              return (
                <div key={i} className={`basket-store-card ${isBest ? "best-store" : ""}`}>
                  {isBest && <span className="best-store-tag">🏆 CHEAPEST OVERALL</span>}
                  <h4>{store.store_name}</h4>
                  <div className="basket-cost">
                    ${store.total_cost.toFixed(2)}
                  </div>
                  <span className="items-matched">
                    {store.items_found} of {store.total_requested} items available
                  </span>
                  {store.missing_items.length > 0 && (
                    <small className="missing-list">
                      Missing: {store.missing_items.join(", ")}
                    </small>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Full Catalog Table */}
      <div className="catalog-section">
        <div className="catalog-header-row">
          <h3>Store Price Database ({catalog.length} items)</h3>
          <div className="cat-filters">
            <button
              className={`cat-pill ${!catalogCategory ? "active" : ""}`}
              onClick={() => {
                setCatalogCategory("");
                fetchCatalog();
              }}
            >
              All
            </button>
            {["produce", "dairy", "meat", "pantry", "bakery"].map((cat) => (
              <button
                key={cat}
                className={`cat-pill ${catalogCategory === cat ? "active" : ""}`}
                onClick={() => {
                  setCatalogCategory(cat);
                  fetchCatalog(cat);
                }}
              >
                {cat}
              </button>
            ))}
          </div>
        </div>

        <div className="catalog-table-wrap">
          <table className="catalog-table">
            <thead>
              <tr>
                <th>Item</th>
                <th>Category</th>
                <th>Store</th>
                <th>Price</th>
                <th>Special Offer</th>
                <th>Availability</th>
              </tr>
            </thead>
            <tbody>
              {catalog.map((item) => (
                <tr key={item.id}>
                  <td><strong>{item.item_name}</strong></td>
                  <td><span className="tag-simple">{item.category}</span></td>
                  <td>{item.store_name}</td>
                  <td><strong>${item.price.toFixed(2)}</strong> <small>/{item.unit}</small></td>
                  <td>{item.deal_description ? <span className="deal-pill">{item.deal_description}</span> : "—"}</td>
                  <td>
                    <span className={item.in_stock ? "text-success" : "text-muted"}>
                      {item.in_stock ? "✓ In Stock" : "Out of stock"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
