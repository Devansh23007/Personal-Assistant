import { useEffect, useState } from "react";

export type EmailMessage = {
  id: number;
  account_id: number;
  external_id: string | null;
  sender: string;
  sender_name: string | null;
  recipient: string;
  subject: string;
  snippet: string;
  body_text: string | null;
  category: "primary" | "action_needed" | "updates" | "receipts" | "newsletters";
  summary: string | null;
  is_read: boolean;
  is_archived: boolean;
  received_at: string;
  created_at: string;
};

export type EmailDraft = {
  id: number;
  user_id: number;
  account_id: number;
  reply_to_message_id: number | null;
  recipient: string;
  subject: string;
  body: string;
  status: "draft" | "awaiting_approval" | "sent" | "discarded";
  sent_at: string | null;
  created_at: string;
  updated_at: string | null;
};

type InboxStats = {
  total: number;
  unread: number;
  action_needed: number;
  drafts_pending: number;
};

export function InboxZeroView({ token }: { token: string }) {
  const [messages, setMessages] = useState<EmailMessage[]>([]);
  const [drafts, setDrafts] = useState<EmailDraft[]>([]);
  const [stats, setStats] = useState<InboxStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  // Filters
  const [currentTab, setCurrentTab] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [selectedMessage, setSelectedMessage] = useState<EmailMessage | null>(null);
  const [draftingForId, setDraftingForId] = useState<number | null>(null);
  const [sendingDraftId, setSendingDraftId] = useState<number | null>(null);

  async function loadData() {
    setLoading(true);
    setError("");
    try {
      // 1. Fetch stats
      const statsRes = await fetch("/api/inboxzero/stats", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (statsRes.ok) {
        setStats(await statsRes.json());
      }

      // 2. Fetch drafts
      const draftsRes = await fetch("/api/inboxzero/drafts", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (draftsRes.ok) {
        setDrafts(await draftsRes.json());
      }

      // 3. Fetch messages if not exclusively on drafts tab
      if (currentTab !== "drafts") {
        const params = new URLSearchParams();
        if (currentTab !== "all") params.append("category", currentTab);
        if (search.trim()) params.append("search", search.trim());

        const msgRes = await fetch(`/api/inboxzero/messages?${params.toString()}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!msgRes.ok) throw new Error("Failed to load messages");
        const msgData: EmailMessage[] = await msgRes.json();
        setMessages(msgData);
        if (msgData.length > 0 && !selectedMessage) {
          setSelectedMessage(msgData[0]);
        }
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Error loading InboxZero");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, [currentTab, search]);

  async function handleToggleRead(msg: EmailMessage) {
    try {
      const nextRead = !msg.is_read;
      const res = await fetch(`/api/inboxzero/messages/${msg.id}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ is_read: nextRead }),
      });
      if (!res.ok) throw new Error("Failed to update message");
      const updated = await res.json();
      setMessages((prev) => prev.map((m) => (m.id === msg.id ? updated : m)));
      if (selectedMessage?.id === msg.id) setSelectedMessage(updated);
      loadStatsOnly();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Update error");
    }
  }

  async function handleArchive(msg: EmailMessage) {
    try {
      const res = await fetch(`/api/inboxzero/messages/${msg.id}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ is_archived: true }),
      });
      if (!res.ok) throw new Error("Failed to archive message");
      setMessages((prev) => prev.filter((m) => m.id !== msg.id));
      if (selectedMessage?.id === msg.id) setSelectedMessage(null);
      loadStatsOnly();
      setNotice(`Archived "${msg.subject.slice(0, 30)}…"`);
      setTimeout(() => setNotice(""), 3000);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Archive error");
    }
  }

  async function handleGenerateDraft(msg: EmailMessage) {
    setDraftingForId(msg.id);
    setError("");
    try {
      const res = await fetch(`/api/inboxzero/messages/${msg.id}/draft-reply`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ instructions: "Draft a polite and concise response." }),
      });
      if (!res.ok) throw new Error("Failed to generate draft reply");
      const newDraft = await res.json();
      setDrafts((prev) => [newDraft, ...prev]);
      setCurrentTab("drafts");
      setNotice("AI reply draft created! Review and approve below.");
      setTimeout(() => setNotice(""), 4000);
      loadStatsOnly();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Draft generation failed");
    } finally {
      setDraftingForId(null);
    }
  }

  async function handleApproveAndSend(draftId: number) {
    setSendingDraftId(draftId);
    setError("");
    try {
      // Explicit human-in-the-loop approval gate
      const res = await fetch(`/api/inboxzero/drafts/${draftId}/send`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Failed to send approved draft");
      const updated = await res.json();
      setDrafts((prev) => prev.map((d) => (d.id === draftId ? updated : d)));
      setNotice("Draft approved and sent successfully!");
      setTimeout(() => setNotice(""), 3500);
      loadStatsOnly();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Approval send failed");
    } finally {
      setSendingDraftId(null);
    }
  }

  async function handleDeleteDraft(draftId: number) {
    if (!confirm("Are you sure you want to discard this draft?")) return;
    try {
      const res = await fetch(`/api/inboxzero/drafts/${draftId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Failed to discard draft");
      setDrafts((prev) => prev.filter((d) => d.id !== draftId));
      loadStatsOnly();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Discard error");
    }
  }

  async function loadStatsOnly() {
    const res = await fetch("/api/inboxzero/stats", {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) setStats(await res.json());
  }

  function formatDate(iso: string) {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }

  return (
    <div className="inbox-container">
      <header className="lifeos-header">
        <div>
          <p className="eyebrow">MODULE · INBOXZERO</p>
          <h1>Smart Email & Triage</h1>
          <p className="lifeos-subtitle">
            AI-powered summaries, categorized triage, and approval-gated drafts. Safe by design.
          </p>
        </div>
        <button className="primary-button" onClick={() => loadData()} style={{ height: "36px", padding: "0 14px" }}>
          Refresh Inbox
        </button>
      </header>

      {/* Stats Cards */}
      {stats && (
        <section className="lifeos-summary-grid">
          <div className="summary-card">
            <span className="summary-label">Total Messages</span>
            <span className="summary-value">{stats.total}</span>
          </div>
          <div className="summary-card accent-today">
            <span className="summary-label">Unread</span>
            <span className="summary-value">{stats.unread}</span>
          </div>
          <div className="summary-card accent-overdue">
            <span className="summary-label">Action Needed</span>
            <span className="summary-value">{stats.action_needed}</span>
          </div>
          <div className="summary-card accent-done">
            <span className="summary-label">Drafts Pending</span>
            <span className="summary-value">{stats.drafts_pending}</span>
          </div>
        </section>
      )}

      {notice && (
        <div style={{ margin: "14px 0", padding: "10px 14px", background: "#f1f8f3", border: "1px solid #b7dec4", borderRadius: "8px", fontSize: "12px", color: "#2d613d" }}>
          ✓ {notice}
        </div>
      )}

      {error && <div className="form-error" style={{ margin: "14px 0" }}>{error}</div>}

      {/* Category Tabs & Search Bar */}
      <section className="lifeos-filter-bar">
        <div className="status-tabs">
          {[
            { id: "all", label: "All Inbox" },
            { id: "action_needed", label: "Action Needed" },
            { id: "primary", label: "Primary" },
            { id: "receipts", label: "Receipts" },
            { id: "newsletters", label: "Newsletters" },
            { id: "drafts", label: `Drafts (${drafts.filter((d) => d.status !== "sent").length})` },
          ].map((tab) => (
            <button
              key={tab.id}
              className={`filter-tab ${currentTab === tab.id ? "active" : ""}`}
              onClick={() => setCurrentTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {currentTab !== "drafts" && (
          <div className="filter-controls">
            <input
              type="search"
              placeholder="Search sender, subject…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="filter-search-input"
              style={{ width: "220px" }}
            />
          </div>
        )}
      </section>

      {/* Main Inbox View: Split pane or Drafts */}
      {currentTab === "drafts" ? (
        <section className="inbox-drafts-list">
          {drafts.length === 0 ? (
            <div className="empty-tasks-state">
              <span className="empty-icon">✉</span>
              <p>No drafts right now. You can generate an AI reply draft from any email!</p>
            </div>
          ) : (
            drafts.map((draft) => (
              <div key={draft.id} className="draft-card">
                <div className="draft-header">
                  <div>
                    <span className={`draft-status-pill status-${draft.status}`}>
                      {draft.status === "awaiting_approval" ? "Awaiting Approval" : draft.status.toUpperCase()}
                    </span>
                    <h3 className="draft-subject">{draft.subject}</h3>
                    <p className="draft-meta">To: <strong>{draft.recipient}</strong></p>
                  </div>
                  <div className="draft-actions">
                    {draft.status !== "sent" ? (
                      <>
                        <button
                          className="primary-button"
                          onClick={() => handleApproveAndSend(draft.id)}
                          disabled={sendingDraftId === draft.id}
                          style={{ height: "34px", padding: "0 16px", background: "#256c42" }}
                        >
                          {sendingDraftId === draft.id ? "Sending…" : "✓ Approve & Send"}
                        </button>
                        <button
                          className="task-delete-btn"
                          onClick={() => handleDeleteDraft(draft.id)}
                          title="Discard draft"
                          style={{ padding: "6px 10px" }}
                        >
                          Discard
                        </button>
                      </>
                    ) : (
                      <span className="sent-timestamp">Sent: {new Date(draft.sent_at || "").toLocaleTimeString()}</span>
                    )}
                  </div>
                </div>
                <div className="draft-body-preview">{draft.body}</div>
              </div>
            ))
          )}
        </section>
      ) : (
        <section className="inbox-split-layout">
          {/* Email List Column */}
          <div className="inbox-message-list">
            {loading && <p className="loading-tasks">Loading emails…</p>}
            {!loading && messages.length === 0 && (
              <div className="empty-tasks-state">
                <span className="empty-icon">✓</span>
                <p>Inbox Zero! All emails caught up in this view.</p>
              </div>
            )}
            {!loading &&
              messages.map((msg) => {
                const isSelected = selectedMessage?.id === msg.id;
                return (
                  <div
                    key={msg.id}
                    className={`inbox-item ${!msg.is_read ? "unread" : ""} ${isSelected ? "selected" : ""}`}
                    onClick={() => setSelectedMessage(msg)}
                  >
                    <div className="inbox-item-top">
                      <div className="sender-row">
                        {!msg.is_read && <span className="unread-dot" />}
                        <strong className="inbox-sender">{msg.sender_name || msg.sender}</strong>
                      </div>
                      <span className="inbox-date">{formatDate(msg.received_at)}</span>
                    </div>

                    <div className="inbox-subject">{msg.subject}</div>

                    <span className={`category-tag cat-${msg.category}`}>
                      {msg.category.replace("_", " ").toUpperCase()}
                    </span>

                    {msg.summary && (
                      <div className="ai-summary-snippet">
                        <span className="ai-sparkle">✳</span> {msg.summary}
                      </div>
                    )}
                  </div>
                );
              })}
          </div>

          {/* Reading Pane Column */}
          <div className="inbox-reading-pane">
            {selectedMessage ? (
              <div className="reading-card">
                <div className="reading-header">
                  <div>
                    <span className={`category-tag cat-${selectedMessage.category}`}>
                      {selectedMessage.category.replace("_", " ").toUpperCase()}
                    </span>
                    <h2>{selectedMessage.subject}</h2>
                    <p className="reading-meta">
                      From: <strong>{selectedMessage.sender_name}</strong> &lt;{selectedMessage.sender}&gt;
                    </p>
                  </div>
                  <div className="reading-actions">
                    <button
                      className="reading-action-btn"
                      onClick={() => handleToggleRead(selectedMessage)}
                      title="Toggle read"
                    >
                      {selectedMessage.is_read ? "Mark Unread" : "Mark Read"}
                    </button>
                    <button
                      className="reading-action-btn"
                      onClick={() => handleArchive(selectedMessage)}
                      title="Archive email"
                    >
                      Archive
                    </button>
                    <button
                      className="primary-button"
                      onClick={() => handleGenerateDraft(selectedMessage)}
                      disabled={draftingForId === selectedMessage.id}
                      style={{ height: "32px", padding: "0 12px", fontSize: "11px" }}
                    >
                      {draftingForId === selectedMessage.id ? "Drafting…" : "✳ AI Draft Reply"}
                    </button>
                  </div>
                </div>

                {selectedMessage.summary && (
                  <div className="reading-ai-summary-box">
                    <strong>✳ AI Summary</strong>
                    <p>{selectedMessage.summary}</p>
                  </div>
                )}

                <div className="reading-body">
                  <pre>{selectedMessage.body_text || selectedMessage.snippet}</pre>
                </div>
              </div>
            ) : (
              <div className="empty-reading-pane">
                <p>Select an email to view its full content and AI summary.</p>
              </div>
            )}
          </div>
        </section>
      )}
    </div>
  );
}
