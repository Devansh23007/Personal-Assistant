import { FormEvent, useEffect, useState } from "react";

export type Task = {
  id: number;
  user_id: number;
  title: string;
  description: string | null;
  status: "pending" | "in_progress" | "completed" | "cancelled";
  priority: "low" | "medium" | "high" | "urgent";
  due_date: string | null;
  reminder_at: string | null;
  timezone: string;
  tags: string[];
  created_at: string;
  updated_at: string | null;
  completed_at: string | null;
};

type TaskSummary = {
  total: number;
  pending: number;
  in_progress: number;
  completed: number;
  overdue: number;
  due_today: number;
};

export function LifeOSView({ token }: { token: string }) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [summary, setSummary] = useState<TaskSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [priorityFilter, setPriorityFilter] = useState<string>("all");
  const [search, setSearch] = useState("");

  // New task form state
  const [newTitle, setNewTitle] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newPriority, setNewPriority] = useState<"low" | "medium" | "high" | "urgent">("medium");
  const [newDueDate, setNewDueDate] = useState("");
  const [newTags, setNewTags] = useState("");
  const [creating, setCreating] = useState(false);

  const localTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";

  async function loadData() {
    setLoading(true);
    setError("");
    try {
      // 1. Fetch summary
      const sumRes = await fetch(`/api/lifeos/tasks/summary?timezone=${encodeURIComponent(localTimezone)}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (sumRes.ok) {
        setSummary(await sumRes.json());
      }

      // 2. Fetch tasks
      const params = new URLSearchParams();
      if (statusFilter !== "all") params.append("status", statusFilter);
      if (priorityFilter !== "all") params.append("priority", priorityFilter);
      if (search.trim()) params.append("search", search.trim());

      const tasksRes = await fetch(`/api/lifeos/tasks?${params.toString()}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!tasksRes.ok) throw new Error("Could not load tasks");
      setTasks(await tasksRes.json());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to load LifeOS data");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, [statusFilter, priorityFilter, search]);

  async function handleCreateTask(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!newTitle.trim() || creating) return;
    setCreating(true);
    setError("");

    try {
      const payload: Record<string, unknown> = {
        title: newTitle.trim(),
        description: newDescription.trim() || null,
        priority: newPriority,
        timezone: localTimezone,
        tags: newTags ? newTags.split(",").map((t) => t.trim()).filter(Boolean) : [],
      };
      if (newDueDate) {
        payload.due_date = new Date(newDueDate).toISOString();
      }

      const res = await fetch("/api/lifeos/tasks", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "Failed to create task");
      }

      // Reset form
      setNewTitle("");
      setNewDescription("");
      setNewPriority("medium");
      setNewDueDate("");
      setNewTags("");

      await loadData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Error creating task");
    } finally {
      setCreating(false);
    }
  }

  async function handleToggleStatus(task: Task) {
    const nextStatus = task.status === "completed" ? "pending" : "completed";
    try {
      const res = await fetch(`/api/lifeos/tasks/${task.id}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ status: nextStatus }),
      });
      if (!res.ok) throw new Error("Failed to update task");
      await loadData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Error updating task status");
    }
  }

  async function handleDeleteTask(taskId: number) {
    if (!confirm("Are you sure you want to delete this task?")) return;
    try {
      const res = await fetch(`/api/lifeos/tasks/${taskId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Failed to delete task");
      await loadData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Error deleting task");
    }
  }

  function formatDateTime(iso: string | null) {
    if (!iso) return null;
    const date = new Date(iso);
    return date.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  const isOverdue = (task: Task) => {
    if (task.status === "completed" || !task.due_date) return false;
    return new Date(task.due_date).getTime() < Date.now();
  };

  return (
    <div className="lifeos-container">
      <header className="lifeos-header">
        <div>
          <p className="eyebrow">MODULE · LIFEOS</p>
          <h1>Tasks & Schedule</h1>
          <p className="lifeos-subtitle">
            Plan your day, organize tasks with priorities, and schedule reminders. Timezone:{" "}
            <strong>{localTimezone}</strong>
          </p>
        </div>
        <button className="primary-button" onClick={() => loadData()} style={{ height: "36px", padding: "0 14px" }}>
          Refresh
        </button>
      </header>

      {/* Summary Cards */}
      {summary && (
        <section className="lifeos-summary-grid">
          <div className="summary-card">
            <span className="summary-label">Total</span>
            <span className="summary-value">{summary.total}</span>
          </div>
          <div className="summary-card">
            <span className="summary-label">Pending</span>
            <span className="summary-value">{summary.pending + summary.in_progress}</span>
          </div>
          <div className="summary-card accent-today">
            <span className="summary-label">Due Today</span>
            <span className="summary-value">{summary.due_today}</span>
          </div>
          <div className="summary-card accent-overdue">
            <span className="summary-label">Overdue</span>
            <span className="summary-value">{summary.overdue}</span>
          </div>
          <div className="summary-card accent-done">
            <span className="summary-label">Completed</span>
            <span className="summary-value">{summary.completed}</span>
          </div>
        </section>
      )}

      {error && <div className="form-error" style={{ margin: "16px 0" }}>{error}</div>}

      {/* New Task Creation Form */}
      <section className="task-create-card">
        <h3>Create New Task</h3>
        <form onSubmit={handleCreateTask} className="task-create-form">
          <div className="form-row">
            <input
              type="text"
              placeholder="What needs to be done? (Title)"
              required
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              className="task-input-title"
            />
            <select
              value={newPriority}
              onChange={(e) => setNewPriority(e.target.value as "low" | "medium" | "high" | "urgent")}
              className="task-select-priority"
            >
              <option value="low">Low Priority</option>
              <option value="medium">Medium Priority</option>
              <option value="high">High Priority</option>
              <option value="urgent">Urgent</option>
            </select>
          </div>

          <div className="form-row">
            <input
              type="datetime-local"
              value={newDueDate}
              onChange={(e) => setNewDueDate(e.target.value)}
              className="task-input-date"
              title="Due date and time"
            />
            <input
              type="text"
              placeholder="Tags (comma-separated, e.g. work, planning)"
              value={newTags}
              onChange={(e) => setNewTags(e.target.value)}
              className="task-input-tags"
            />
          </div>

          <div className="form-row">
            <input
              type="text"
              placeholder="Optional notes or details"
              value={newDescription}
              onChange={(e) => setNewDescription(e.target.value)}
              className="task-input-desc"
            />
            <button type="submit" className="primary-button" disabled={creating || !newTitle.trim()}>
              {creating ? "Adding…" : "+ Add Task"}
            </button>
          </div>
        </form>
      </section>

      {/* Filters & Search */}
      <section className="lifeos-filter-bar">
        <div className="status-tabs">
          {["all", "pending", "in_progress", "completed"].map((st) => (
            <button
              key={st}
              className={`filter-tab ${statusFilter === st ? "active" : ""}`}
              onClick={() => setStatusFilter(st)}
            >
              {st === "in_progress" ? "In Progress" : st.charAt(0).toUpperCase() + st.slice(1)}
            </button>
          ))}
        </div>

        <div className="filter-controls">
          <select
            value={priorityFilter}
            onChange={(e) => setPriorityFilter(e.target.value)}
            className="filter-priority-select"
          >
            <option value="all">All Priorities</option>
            <option value="urgent">Urgent</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>

          <input
            type="search"
            placeholder="Search tasks…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="filter-search-input"
          />
        </div>
      </section>

      {/* Tasks List */}
      <section className="lifeos-task-list">
        {loading && <p className="loading-tasks">Loading tasks…</p>}
        {!loading && tasks.length === 0 && (
          <div className="empty-tasks-state">
            <span className="empty-icon">✓</span>
            <p>No tasks found. Everything is clear or no tasks match your filters!</p>
          </div>
        )}
        {!loading &&
          tasks.map((task) => {
            const overdue = isOverdue(task);
            return (
              <div key={task.id} className={`task-item ${task.status === "completed" ? "is-completed" : ""}`}>
                <button
                  type="button"
                  className={`task-checkbox ${task.status === "completed" ? "checked" : ""}`}
                  onClick={() => handleToggleStatus(task)}
                  aria-label={task.status === "completed" ? "Mark incomplete" : "Mark complete"}
                >
                  {task.status === "completed" ? "✓" : ""}
                </button>

                <div className="task-main">
                  <div className="task-title-row">
                    <span className="task-title">{task.title}</span>
                    <span className={`priority-pill priority-${task.priority}`}>{task.priority}</span>
                    {overdue && <span className="overdue-badge">Overdue</span>}
                  </div>
                  {task.description && <p className="task-desc">{task.description}</p>}

                  <div className="task-meta-row">
                    {task.due_date && (
                      <span className={`task-date ${overdue ? "text-overdue" : ""}`}>
                        🕒 Due: {formatDateTime(task.due_date)}
                      </span>
                    )}
                    {task.tags && task.tags.length > 0 && (
                      <div className="task-tags">
                        {task.tags.map((tg) => (
                          <span key={tg} className="task-tag-pill">
                            #{tg}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                <button
                  type="button"
                  className="task-delete-btn"
                  onClick={() => handleDeleteTask(task.id)}
                  title="Delete task"
                >
                  ✕
                </button>
              </div>
            );
          })}
      </section>
    </div>
  );
}
