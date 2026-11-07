import { FormEvent, useEffect, useState } from "react";

export type Transaction = {
  id: number;
  user_id: number;
  amount: number;
  type: "expense" | "income";
  category: string;
  description: string;
  date: string;
  payment_method: string;
  is_recurring: boolean;
  tags: string[];
  created_at: string;
};

export type Budget = {
  id: number;
  user_id: number;
  category: string;
  monthly_limit: number;
  month: string;
  spent: number;
  remaining: number;
  percentage_used: number;
};

type SpendSummary = {
  month: string;
  total_income: number;
  total_expenses: number;
  net_savings: number;
  savings_rate: number;
  category_breakdown: Record<string, number>;
  top_categories: { category: string; amount: number }[];
  over_budget_count: number;
};

const CATEGORIES = [
  "Food & Dining",
  "Transportation",
  "Shopping",
  "Entertainment",
  "Housing & Utilities",
  "Healthcare",
  "Salary & Investments",
  "Other",
];

export function SpendWiseView({ token }: { token: string }) {
  const currentMonthStr = new Date().toISOString().slice(0, 7);
  const [selectedMonth, setSelectedMonth] = useState(currentMonthStr);
  const [summary, setSummary] = useState<SpendSummary | null>(null);
  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  // Filters
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [categoryFilter, setCategoryFilter] = useState<string>("all");
  const [search, setSearch] = useState("");

  // Transaction form
  const [newAmount, setNewAmount] = useState("");
  const [newType, setNewType] = useState<"expense" | "income">("expense");
  const [newCategory, setNewCategory] = useState("Food & Dining");
  const [newDescription, setNewDescription] = useState("");
  const [newPaymentMethod, setNewPaymentMethod] = useState("Credit Card");
  const [newDate, setNewDate] = useState(new Date().toISOString().slice(0, 10));
  const [addingTx, setAddingTx] = useState(false);

  // Budget form
  const [showBudgetForm, setShowBudgetForm] = useState(false);
  const [budgetCat, setBudgetCat] = useState("Food & Dining");
  const [budgetLimit, setBudgetLimit] = useState("");

  // CSV Import state
  const [showCsvBox, setShowCsvBox] = useState(false);
  const [csvText, setCsvText] = useState("");
  const [importingCsv, setImportingCsv] = useState(false);

  async function loadData() {
    setLoading(true);
    setError("");
    try {
      // 1. Fetch summary
      const sumRes = await fetch(`/api/spendwise/summary?month=${selectedMonth}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (sumRes.ok) setSummary(await sumRes.json());

      // 2. Fetch budgets
      const budRes = await fetch(`/api/spendwise/budgets?month=${selectedMonth}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (budRes.ok) setBudgets(await budRes.json());

      // 3. Fetch transactions
      const params = new URLSearchParams();
      params.append("month", selectedMonth);
      if (typeFilter !== "all") params.append("type", typeFilter);
      if (categoryFilter !== "all") params.append("category", categoryFilter);
      if (search.trim()) params.append("search", search.trim());

      const txRes = await fetch(`/api/spendwise/transactions?${params.toString()}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!txRes.ok) throw new Error("Could not load transactions");
      setTransactions(await txRes.json());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Error loading financial data");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, [selectedMonth, typeFilter, categoryFilter, search]);

  async function handleAddTransaction(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const amt = parseFloat(newAmount);
    if (isNaN(amt) || amt <= 0 || !newDescription.trim() || addingTx) return;

    setAddingTx(true);
    setError("");
    try {
      const res = await fetch("/api/spendwise/transactions", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          amount: amt,
          type: newType,
          category: newCategory,
          description: newDescription.trim(),
          payment_method: newPaymentMethod,
          date: newDate,
        }),
      });

      if (!res.ok) throw new Error("Failed to create transaction");
      setNewAmount("");
      setNewDescription("");
      setNotice("Transaction logged successfully!");
      setTimeout(() => setNotice(""), 3000);
      await loadData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Error creating transaction");
    } finally {
      setAddingTx(false);
    }
  }

  async function handleDeleteTransaction(id: number) {
    if (!confirm("Delete this transaction?")) return;
    try {
      const res = await fetch(`/api/spendwise/transactions/${id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Failed to delete transaction");
      await loadData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Error deleting transaction");
    }
  }

  async function handleSetBudget(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const limit = parseFloat(budgetLimit);
    if (isNaN(limit) || limit <= 0) return;

    try {
      const res = await fetch("/api/spendwise/budgets", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          category: budgetCat,
          monthly_limit: limit,
          month: selectedMonth,
        }),
      });
      if (!res.ok) throw new Error("Failed to configure budget");
      setBudgetLimit("");
      setShowBudgetForm(false);
      setNotice(`Budget configured for ${budgetCat}!`);
      setTimeout(() => setNotice(""), 3000);
      await loadData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Error saving budget");
    }
  }

  async function handleDeleteBudget(id: number) {
    if (!confirm("Delete this category budget?")) return;
    try {
      const res = await fetch(`/api/spendwise/budgets/${id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Failed to delete budget");
      await loadData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Error deleting budget");
    }
  }

  async function handleImportCsv(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!csvText.trim() || importingCsv) return;

    setImportingCsv(true);
    setError("");
    try {
      const res = await fetch("/api/spendwise/transactions/import-csv", {
        method: "POST",
        headers: {
          "Content-Type": "text/plain",
          Authorization: `Bearer ${token}`,
        },
        body: csvText.trim(),
      });
      if (!res.ok) throw new Error("Failed to import CSV");
      const result = await res.json();
      setNotice(`Imported ${result.imported_count} transaction(s)!`);
      setTimeout(() => setNotice(""), 4000);
      setCsvText("");
      setShowCsvBox(false);
      await loadData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Error importing CSV");
    } finally {
      setImportingCsv(false);
    }
  }

  function fillSampleCsv() {
    setCsvText(
      `Date,Description,Amount,Category,Type,Payment Method\n${selectedMonth}-02,Freelance Design Invoice,850.00,Salary & Investments,credit,Bank Transfer\n${selectedMonth}-05,Weekly Groceries,89.20,Food & Dining,expense,Credit Card\n${selectedMonth}-07,Metro Card Transit,35.00,Transportation,expense,Debit Card`
    );
  }

  return (
    <div className="spendwise-container">
      <header className="lifeos-header">
        <div>
          <p className="eyebrow">MODULE · SPENDWISE</p>
          <h1>Expenses & Budgeting</h1>
          <p className="lifeos-subtitle">
            Track transactions, monitor budget caps, and analyze your personal cash flow.
          </p>
        </div>
        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
          <input
            type="month"
            value={selectedMonth}
            onChange={(e) => setSelectedMonth(e.target.value)}
            className="filter-priority-select"
            style={{ height: "36px", padding: "0 10px" }}
          />
          <button
            className="primary-button"
            onClick={() => loadData()}
            style={{ height: "36px", padding: "0 14px" }}
          >
            Refresh
          </button>
        </div>
      </header>

      {/* Financial Summary Cards */}
      {summary && (
        <section className="lifeos-summary-grid">
          <div className="summary-card">
            <span className="summary-label">Total Income</span>
            <span className="summary-value" style={{ color: "#287247" }}>
              ${summary.total_income.toFixed(2)}
            </span>
          </div>
          <div className="summary-card">
            <span className="summary-label">Total Expenses</span>
            <span className="summary-value" style={{ color: "#af382b" }}>
              ${summary.total_expenses.toFixed(2)}
            </span>
          </div>
          <div className="summary-card accent-today">
            <span className="summary-label">Net Savings</span>
            <span className="summary-value">
              ${summary.net_savings.toFixed(2)}
            </span>
          </div>
          <div className="summary-card accent-done">
            <span className="summary-label">Savings Rate</span>
            <span className="summary-value">
              {summary.savings_rate}%
            </span>
          </div>
          <div className="summary-card">
            <span className="summary-label">Budget Overruns</span>
            <span
              className="summary-value"
              style={{ color: summary.over_budget_count > 0 ? "#b4392c" : "#326249" }}
            >
              {summary.over_budget_count}
            </span>
          </div>
        </section>
      )}

      {notice && (
        <div style={{ margin: "14px 0", padding: "10px 14px", background: "#f1f8f3", border: "1px solid #b7dec4", borderRadius: "8px", fontSize: "12px", color: "#2d613d" }}>
          ✓ {notice}
        </div>
      )}

      {error && <div className="form-error" style={{ margin: "14px 0" }}>{error}</div>}

      {/* Budgets Section */}
      <section className="task-create-card" style={{ marginBottom: "20px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "14px" }}>
          <h3 style={{ margin: 0 }}>Category Budgets for {selectedMonth}</h3>
          <button
            className="reading-action-btn"
            onClick={() => setShowBudgetForm(!showBudgetForm)}
          >
            {showBudgetForm ? "Cancel" : "+ Set / Adjust Budget"}
          </button>
        </div>

        {showBudgetForm && (
          <form onSubmit={handleSetBudget} className="task-create-form" style={{ marginBottom: "16px", padding: "12px", background: "#f9faf7", borderRadius: "8px" }}>
            <div className="form-row">
              <select
                value={budgetCat}
                onChange={(e) => setBudgetCat(e.target.value)}
                className="task-select-priority"
                style={{ flex: 2 }}
              >
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
              <input
                type="number"
                step="0.01"
                placeholder="Monthly limit (e.g. 450)"
                required
                value={budgetLimit}
                onChange={(e) => setBudgetLimit(e.target.value)}
                className="task-input-title"
                style={{ flex: 2 }}
              />
              <button type="submit" className="primary-button" style={{ height: "38px" }}>
                Save Budget
              </button>
            </div>
          </form>
        )}

        <div className="budget-progress-grid">
          {budgets.map((b) => {
            const isOver = b.spent > b.monthly_limit;
            const isNear = b.percentage_used >= 80 && !isOver;
            return (
              <div key={b.id} className="budget-bar-card">
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", marginBottom: "6px" }}>
                  <strong>{b.category}</strong>
                  <span>
                    ${b.spent.toFixed(2)} / ${b.monthly_limit.toFixed(2)} ({b.percentage_used}%)
                  </span>
                </div>
                <div className="progress-track">
                  <div
                    className={`progress-fill ${isOver ? "fill-over" : isNear ? "fill-near" : "fill-normal"}`}
                    style={{ width: `${Math.min(b.percentage_used, 100)}%` }}
                  />
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "10px", marginTop: "4px", color: isOver ? "#b53a2d" : "#7c8779" }}>
                  <span>{isOver ? `Over by $${Math.abs(b.remaining).toFixed(2)}` : `$${b.remaining.toFixed(2)} remaining`}</span>
                  <button
                    onClick={() => handleDeleteBudget(b.id)}
                    style={{ border: 0, background: "none", color: "#a5b0a3", cursor: "pointer" }}
                    title="Delete budget"
                  >
                    ✕
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* Transaction Entry & CSV Import Action Row */}
      <section className="task-create-card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "14px" }}>
          <h3 style={{ margin: 0 }}>Log New Transaction</h3>
          <button
            className="reading-action-btn"
            onClick={() => setShowCsvBox(!showCsvBox)}
          >
            {showCsvBox ? "Close CSV Import" : "⇪ Import Transactions via CSV"}
          </button>
        </div>

        {showCsvBox && (
          <form onSubmit={handleImportCsv} style={{ marginBottom: "18px", padding: "14px", background: "#f8f9f6", borderRadius: "8px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px" }}>
              <span style={{ fontSize: "11px", color: "#616e60" }}>
                Paste CSV text with headers: <code>Date, Description, Amount, Category, Type, Payment Method</code>
              </span>
              <button
                type="button"
                onClick={fillSampleCsv}
                style={{ border: 0, background: "none", color: "#315f48", fontSize: "11px", fontWeight: "bold", cursor: "pointer" }}
              >
                Insert Sample Data
              </button>
            </div>
            <textarea
              rows={4}
              value={csvText}
              onChange={(e) => setCsvText(e.target.value)}
              placeholder="Date,Description,Amount,Category,Type,Payment Method..."
              className="task-input-desc"
              style={{ width: "100%", height: "80px", fontFamily: "monospace", fontSize: "11px" }}
            />
            <button
              type="submit"
              className="primary-button"
              disabled={importingCsv || !csvText.trim()}
              style={{ marginTop: "8px", height: "34px", padding: "0 16px" }}
            >
              {importingCsv ? "Importing…" : "Upload & Parse CSV"}
            </button>
          </form>
        )}

        <form onSubmit={handleAddTransaction} className="task-create-form">
          <div className="form-row">
            <input
              type="number"
              step="0.01"
              placeholder="Amount ($)"
              required
              value={newAmount}
              onChange={(e) => setNewAmount(e.target.value)}
              className="task-input-title"
              style={{ flex: 1.2 }}
            />
            <select
              value={newType}
              onChange={(e) => setNewType(e.target.value as "expense" | "income")}
              className="task-select-priority"
              style={{ flex: 1 }}
            >
              <option value="expense">Expense (-)</option>
              <option value="income">Income (+)</option>
            </select>
            <select
              value={newCategory}
              onChange={(e) => setNewCategory(e.target.value)}
              className="task-select-priority"
              style={{ flex: 1.8 }}
            >
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
            <input
              type="text"
              placeholder="Description (e.g. Grocery run, Dinner)"
              required
              value={newDescription}
              onChange={(e) => setNewDescription(e.target.value)}
              className="task-input-title"
              style={{ flex: 3 }}
            />
          </div>

          <div className="form-row">
            <select
              value={newPaymentMethod}
              onChange={(e) => setNewPaymentMethod(e.target.value)}
              className="task-select-priority"
              style={{ flex: 1.5 }}
            >
              <option value="Credit Card">Credit Card</option>
              <option value="Debit Card">Debit Card</option>
              <option value="UPI">UPI</option>
              <option value="Bank Transfer">Bank Transfer</option>
              <option value="Cash">Cash</option>
            </select>
            <input
              type="date"
              value={newDate}
              onChange={(e) => setNewDate(e.target.value)}
              className="task-input-date"
              style={{ flex: 1.5 }}
            />
            <button
              type="submit"
              className="primary-button"
              disabled={addingTx || !newAmount || !newDescription.trim()}
              style={{ flex: 1, height: "38px" }}
            >
              {addingTx ? "Logging…" : "+ Add Transaction"}
            </button>
          </div>
        </form>
      </section>

      {/* Filter Bar */}
      <section className="lifeos-filter-bar">
        <div className="status-tabs">
          {[
            { id: "all", label: "All Transactions" },
            { id: "expense", label: "Expenses" },
            { id: "income", label: "Income" },
          ].map((tab) => (
            <button
              key={tab.id}
              className={`filter-tab ${typeFilter === tab.id ? "active" : ""}`}
              onClick={() => setTypeFilter(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="filter-controls">
          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="filter-priority-select"
          >
            <option value="all">All Categories</option>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>

          <input
            type="search"
            placeholder="Search transactions…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="filter-search-input"
          />
        </div>
      </section>

      {/* Transactions Table / List */}
      <section className="spendwise-ledger">
        {loading && <p className="loading-tasks">Loading transactions…</p>}
        {!loading && transactions.length === 0 && (
          <div className="empty-tasks-state">
            <span className="empty-icon">₹</span>
            <p>No transactions found for {selectedMonth}. Log one above or import via CSV!</p>
          </div>
        )}
        {!loading && transactions.length > 0 && (
          <div className="ledger-table-wrap">
            <table className="ledger-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Description</th>
                  <th>Category</th>
                  <th>Method</th>
                  <th style={{ textAlign: "right" }}>Amount</th>
                  <th style={{ width: "40px" }}></th>
                </tr>
              </thead>
              <tbody>
                {transactions.map((t) => (
                  <tr key={t.id}>
                    <td className="ledger-date">{t.date}</td>
                    <td className="ledger-desc">
                      <strong>{t.description}</strong>
                      {t.is_recurring && <span className="recurring-badge">Recurring</span>}
                    </td>
                    <td>
                      <span className="task-tag-pill">{t.category}</span>
                    </td>
                    <td className="ledger-method">{t.payment_method}</td>
                    <td className="ledger-amount" style={{ textAlign: "right", color: t.type === "income" ? "#247143" : "#283429" }}>
                      {t.type === "income" ? `+$${t.amount.toFixed(2)}` : `-$${t.amount.toFixed(2)}`}
                    </td>
                    <td>
                      <button
                        className="task-delete-btn"
                        onClick={() => handleDeleteTransaction(t.id)}
                        title="Delete transaction"
                      >
                        ✕
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
