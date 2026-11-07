import { FormEvent, useEffect, useState } from "react";

type Workflow = {
  id: number;
  user_id: number;
  name: string;
  description: string | null;
  trigger_type: string;
  schedule_cron: string | null;
  is_active: boolean;
  config_json: string;
  created_at: string;
};

type WorkflowRun = {
  id: number;
  workflow_id: number;
  workflow_name: string | null;
  user_id: number;
  status: string;
  triggered_by: string;
  results_summary: string;
  details_json: string;
  requires_approval: boolean;
  approved_at: string | null;
  created_at: string;
};

type MorningBriefing = {
  generated_at: string;
  headline: string;
  urgent_tasks: Array<{ id: number; title: string; priority: string; due_date: string | null }>;
  urgent_emails: Array<{ id: number; from: string; subject: string; category: string }>;
  planned_dinner: { meal: string; notes: string | null } | null;
  budget_alerts: Array<{ category: string; spent: number; limit: number; percentage: number }>;
  study_due_count: number;
  summary_markdown: string;
};

export function AutoFlowView({ token }: { token: string }) {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [briefing, setBriefing] = useState<MorningBriefing | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [successMsg, setSuccessMsg] = useState("");

  // Create workflow
  const [showAddForm, setShowAddForm] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [newTrigger, setNewTrigger] = useState("manual");
  const [newCron, setNewCron] = useState("0 9 * * *");
  const [actionChoice, setActionChoice] = useState("morning_briefing");

  useEffect(() => {
    fetchData();
  }, [token]);

  async function fetchData() {
    setLoading(true);
    setError("");
    try {
      const [wfRes, runsRes, briefRes] = await Promise.all([
        fetch("/api/autoflow/workflows", { headers: { Authorization: `Bearer ${token}` } }),
        fetch("/api/autoflow/runs", { headers: { Authorization: `Bearer ${token}` } }),
        fetch("/api/autoflow/briefing", { headers: { Authorization: `Bearer ${token}` } }),
      ]);

      if (wfRes.ok) setWorkflows(await wfRes.json());
      if (runsRes.ok) setRuns(await runsRes.json());
      if (briefRes.ok) setBriefing(await briefRes.json());
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error loading AutoFlow data");
    } finally {
      setLoading(false);
    }
  }

  async function handleTriggerRun(workflowId: number) {
    setError("");
    setSuccessMsg("");
    try {
      const res = await fetch(`/api/autoflow/workflows/${workflowId}/run`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Failed to execute workflow");
      const run: WorkflowRun = await res.json();
      setRuns((prev) => [run, ...prev]);
      if (run.requires_approval) {
        setSuccessMsg(`Workflow initiated: "${run.workflow_name || 'Workflow'}" requires your human approval below!`);
      } else {
        setSuccessMsg(`Workflow executed: ${run.results_summary}`);
      }
      // Refresh briefing in case items changed
      const freshBrief = await fetch("/api/autoflow/briefing", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (freshBrief.ok) setBriefing(await freshBrief.json());
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Execution error");
    }
  }

  async function handleApprove(runId: number) {
    try {
      const res = await fetch(`/api/autoflow/runs/${runId}/approve`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Approval failed");
      const updated: WorkflowRun = await res.json();
      setRuns((prev) => prev.map((r) => (r.id === runId ? updated : r)));
      setSuccessMsg("Workflow run approved and executed!");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Approval error");
    }
  }

  async function handleReject(runId: number) {
    try {
      const res = await fetch(`/api/autoflow/runs/${runId}/reject`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Rejection failed");
      const updated: WorkflowRun = await res.json();
      setRuns((prev) => prev.map((r) => (r.id === runId ? updated : r)));
      setSuccessMsg("Workflow run rejected and aborted.");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Rejection error");
    }
  }

  async function handleToggleActive(wf: Workflow) {
    try {
      const res = await fetch(`/api/autoflow/workflows/${wf.id}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ is_active: !wf.is_active }),
      });
      if (!res.ok) throw new Error("Failed to update status");
      const updated = await res.json();
      setWorkflows((prev) => prev.map((w) => (w.id === wf.id ? updated : w)));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Toggle error");
    }
  }

  async function handleCreateWorkflow(e: FormEvent) {
    e.preventDefault();
    setError("");
    setSuccessMsg("");
    try {
      const res = await fetch("/api/autoflow/workflows", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          name: newName,
          description: newDesc || undefined,
          trigger_type: newTrigger,
          schedule_cron: newTrigger === "scheduled" ? newCron : undefined,
          is_active: true,
          config: { action: actionChoice },
        }),
      });
      if (!res.ok) throw new Error("Failed to create workflow");
      const created = await res.json();
      setWorkflows((prev) => [...prev, created]);
      setSuccessMsg("Workflow created!");
      setShowAddForm(false);
      setNewName("");
      setNewDesc("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Create error");
    }
  }

  return (
    <div className="autoflow-view">
      <div className="view-header">
        <div>
          <h2>AutoFlow</h2>
          <p className="subtitle">Cross-module connected automations, consolidated daily briefings & approval gates</p>
        </div>
        <button className="btn-primary" onClick={() => setShowAddForm(!showAddForm)}>
          {showAddForm ? "Cancel" : "+ New Automation"}
        </button>
      </div>

      {error && <div className="error-banner">{error}</div>}
      {successMsg && <div className="success-banner">{successMsg}</div>}

      {/* Morning Briefing Highlight Card */}
      {briefing && (
        <div className="briefing-container">
          <div className="briefing-header">
            <div>
              <span className="briefing-tag">Consolidated Intelligence</span>
              <h3>Executive Morning Briefing</h3>
              <p className="briefing-headline">{briefing.headline}</p>
            </div>
            <button
              className="btn-secondary btn-sm"
              onClick={async () => {
                const res = await fetch("/api/autoflow/briefing", {
                  headers: { Authorization: `Bearer ${token}` },
                });
                if (res.ok) setBriefing(await res.json());
              }}
            >
              🔄 Refresh Briefing
            </button>
          </div>

          <div className="briefing-metrics-grid">
            <div className="brief-card">
              <span className="brief-icon">⚡</span>
              <div>
                <strong>{briefing.urgent_tasks.length} Urgent Tasks</strong>
                <small>LifeOS deadlines</small>
              </div>
            </div>
            <div className="brief-card">
              <span className="brief-icon">✉️</span>
              <div>
                <strong>{briefing.urgent_emails.length} Action Emails</strong>
                <small>InboxZero triage</small>
              </div>
            </div>
            <div className="brief-card">
              <span className="brief-icon">🍽️</span>
              <div>
                <strong>{briefing.planned_dinner ? briefing.planned_dinner.meal : "None planned"}</strong>
                <small>MealMind dinner</small>
              </div>
            </div>
            <div className="brief-card">
              <span className="brief-icon">🧠</span>
              <div>
                <strong>{briefing.study_due_count} Cards Due</strong>
                <small>LearnLoop recall</small>
              </div>
            </div>
          </div>

          <div className="briefing-markdown-box">
            <pre className="briefing-text">{briefing.summary_markdown}</pre>
          </div>
        </div>
      )}

      {/* New Workflow Form */}
      {showAddForm && (
        <form className="add-workflow-form" onSubmit={handleCreateWorkflow}>
          <h3>Configure Connected Automation</h3>
          <div className="form-row">
            <div className="form-group" style={{ flex: 2 }}>
              <label>Automation Name</label>
              <input
                type="text"
                required
                placeholder="e.g., Evening Task & Email Reconciliation"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
              />
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label>Trigger Type</label>
              <select value={newTrigger} onChange={(e) => setNewTrigger(e.target.value)}>
                <option value="manual">Manual Trigger</option>
                <option value="scheduled">Scheduled (Cron)</option>
                <option value="event">Event-driven</option>
              </select>
            </div>
          </div>

          {newTrigger === "scheduled" && (
            <div className="form-group">
              <label>Schedule Cron Expression</label>
              <input
                type="text"
                placeholder="0 9 * * * (Every morning at 9am)"
                value={newCron}
                onChange={(e) => setNewCron(e.target.value)}
              />
            </div>
          )}

          <div className="form-row">
            <div className="form-group" style={{ flex: 1 }}>
              <label>Cross-Module Action</label>
              <select value={actionChoice} onChange={(e) => setActionChoice(e.target.value)}>
                <option value="morning_briefing">Consolidated Daily Briefing</option>
                <option value="grocery_restock_optimizer">Smart Grocery Restock & Price Optimizer (Approval Gate)</option>
                <option value="budget_guard">Weekly Financial Budget Guard</option>
                <option value="study_loop">Daily Study Spaced Repetition Loop</option>
              </select>
            </div>
          </div>

          <div className="form-group">
            <label>Description</label>
            <input
              type="text"
              placeholder="Brief description of the automated workflow"
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
            />
          </div>

          <button type="submit" className="btn-primary">Save Automation</button>
        </form>
      )}

      {/* Active Workflows Grid */}
      <div className="workflows-section">
        <div className="section-title-row">
          <h3>Connected Workflows ({workflows.length})</h3>
        </div>

        {loading ? (
          <p className="loading-notice">Loading workflows…</p>
        ) : workflows.length === 0 ? (
          <p className="empty-notice">No workflows found.</p>
        ) : (
          <div className="workflows-grid">
            {workflows.map((wf) => (
              <div key={wf.id} className={`workflow-card ${wf.is_active ? "active" : "disabled"}`}>
                <div className="wf-top">
                  <span className="wf-icon">⚙️</span>
                  <div className="wf-info">
                    <h4>{wf.name}</h4>
                    <span className="wf-trigger-badge">
                      {wf.trigger_type.toUpperCase()} {wf.schedule_cron && `· ${wf.schedule_cron}`}
                    </span>
                  </div>
                  <button
                    className={`toggle-btn ${wf.is_active ? "on" : "off"}`}
                    title={wf.is_active ? "Pause automation" : "Enable automation"}
                    onClick={() => handleToggleActive(wf)}
                  >
                    {wf.is_active ? "Active" : "Paused"}
                  </button>
                </div>

                {wf.description && <p className="wf-desc">{wf.description}</p>}

                <div className="wf-actions">
                  <button
                    className="btn-primary btn-sm"
                    disabled={!wf.is_active}
                    onClick={() => handleTriggerRun(wf.id)}
                  >
                    ▶ Run Workflow Now
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Execution History & Approval Gates */}
      <div className="runs-history-section">
        <div className="section-title-row">
          <h3>Execution History & Human Approval Gates</h3>
        </div>

        {runs.length === 0 ? (
          <p className="empty-notice">No execution runs yet. Click &quot;▶ Run Workflow Now&quot; above!</p>
        ) : (
          <div className="runs-list">
            {runs.map((run) => (
              <div
                key={run.id}
                className={`run-card ${run.status === "pending_approval" ? "approval-required" : ""}`}
              >
                <div className="run-header">
                  <div className="run-title-col">
                    <strong>{run.workflow_name || `Workflow #${run.workflow_id}`}</strong>
                    <span className="run-timestamp">
                      Triggered via {run.triggered_by} · {new Date(run.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>

                  <span className={`run-status-badge status-${run.status}`}>
                    {run.status.replace("_", " ").toUpperCase()}
                  </span>
                </div>

                <p className="run-summary">{run.results_summary}</p>

                {run.status === "pending_approval" && (
                  <div className="approval-gate-banner">
                    <div className="approval-copy">
                      <strong>⚠️ Human Approval Gate Required</strong>
                      <span>This workflow generated an external/financial action. Do you authorize this operation?</span>
                    </div>
                    <div className="approval-buttons">
                      <button className="btn-approve" onClick={() => handleApprove(run.id)}>
                        ✓ Authorize & Complete
                      </button>
                      <button className="btn-reject" onClick={() => handleReject(run.id)}>
                        ✕ Reject
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
