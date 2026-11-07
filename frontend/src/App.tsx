import { FormEvent, useEffect, useState } from "react";
import { AutoFlowView } from "./AutoFlowView";
import { DocuVaultView } from "./DocuVaultView";
import { InboxZeroView } from "./InboxZeroView";
import { LearnLoopView } from "./LearnLoopView";
import { LifeOSView } from "./LifeOSView";
import { MealMindView } from "./MealMindView";
import { PricePilotView } from "./PricePilotView";
import { SpendWiseView } from "./SpendWiseView";

const modules = [
  { name: "LifeOS", detail: "Tasks and planning", icon: "◷", available: true },
  { name: "InboxZero", detail: "Email summaries & triage", icon: "✉", available: true },
  { name: "SpendWise", detail: "Expenses and budgets", icon: "₹", available: true },
  { name: "LearnLoop", detail: "Study and revision", icon: "▤", available: true },
  { name: "DocuVault", detail: "Your documents", icon: "▱", available: true },
  { name: "MealMind", detail: "Meals and groceries", icon: "⌂", available: true },
  { name: "PricePilot", detail: "Shopping research", icon: "◇", available: true },
  { name: "AutoFlow", detail: "Connected workflows", icon: "⤳", available: true },
];

type User = { id: number; email: string };
type ChatMessage = { role: "user" | "assistant"; content: string };

function App() {
  const [user, setUser] = useState<User>({ id: 1, email: "devansh@local" });
  const [apiStatus, setApiStatus] = useState("Checking API…");

  useEffect(() => {
    fetch("/api/health")
      .then((response) => response.json())
      .then((data: { status: string; assistant: string }) => {
        setApiStatus(data.status === "ok" ? "API online" : "API offline");
      })
      .catch(() => setApiStatus("API offline"));

    fetch("/api/auth/me")
      .then((res) => (res.ok ? res.json() : null))
      .then((data: User | null) => {
        if (data) setUser(data);
      })
      .catch(() => {});
  }, []);

  return <Dashboard user={user} token="" apiStatus={apiStatus} />;
}

function Dashboard({ user, token, apiStatus }: { user: User; token: string; apiStatus: string }) {
  const [activeView, setActiveView] = useState<string>("overview");
  const [selectedDeckId, setSelectedDeckId] = useState<number | null>(null);
  const [selectedPriceQuery, setSelectedPriceQuery] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [prompt, setPrompt] = useState("");
  const [chatError, setChatError] = useState("");
  const [sending, setSending] = useState(false);
  const [notice, setNotice] = useState("");

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = prompt.trim();
    if (!message || sending) return;
    const next = [...messages, { role: "user" as const, content: message }];
    setMessages(next);
    setPrompt("");
    setChatError("");
    setSending(true);
    try {
      const response = await fetch("/api/assistant/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, history: messages.slice(-20) }),
      });
      if (!response.ok) throw new Error(await readError(response));
      const result = (await response.json()) as { reply: string };
      setMessages([...next, { role: "assistant", content: result.reply }]);
    } catch (caught) {
      setChatError(caught instanceof Error ? caught.message : "Assistant request failed.");
    } finally {
      setSending(false);
    }
  }

  function handleModuleClick(moduleName: string, available: boolean) {
    if (available) {
      setActiveView(moduleName.toLowerCase());
      setNotice("");
    } else {
      setNotice(`${moduleName} is scheduled for a future development phase.`);
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Sidebar navigation">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">p</span>
          <span>personal<span className="brand-light">assistant</span></span>
        </div>
        <p className="nav-label">MODULES</p>
        <nav className="nav-list">
          <button
            type="button"
            className={`module-link ${activeView === "overview" ? "active" : ""}`}
            onClick={() => setActiveView("overview")}
            style={{ width: "100%", border: 0, textAlign: "left", cursor: "pointer", background: "none" }}
          >
            <span className="module-icon" aria-hidden="true">✦</span>
            <span className="module-copy"><strong>Overview</strong><small>Home dashboard</small></span>
            {activeView === "overview" && <span className="active-dot" />}
          </button>
          {modules.map((module) => {
            const isActive = activeView === module.name.toLowerCase();
            return (
              <button
                type="button"
                className={`module-link ${isActive ? "active" : ""}`}
                onClick={() => handleModuleClick(module.name, module.available)}
                key={module.name}
                style={{ width: "100%", border: 0, textAlign: "left", cursor: "pointer", background: "none" }}
              >
                <span className="module-icon" aria-hidden="true">{module.icon}</span>
                <span className="module-copy">
                  <strong>{module.name}</strong>
                  <small>{module.detail}</small>
                </span>
                {isActive && <span className="active-dot" />}
              </button>
            );
          })}
        </nav>
        <div className="account-row" title="Local Workspace Active">
          <span className="user-avatar">{user.email[0]?.toUpperCase()}</span>
          <span><strong>{user.email}</strong><small>Local Assistant · Active</small></span>
        </div>
      </aside>

      <main className="main-content" id="home">
        <header className="topbar">
          <div className="breadcrumbs">
            <span
              style={{ cursor: "pointer", textDecoration: activeView !== "overview" ? "underline" : "none" }}
              onClick={() => setActiveView("overview")}
            >
              Workspace
            </span>
            <span>/</span>
            <strong>{activeView === "overview" ? "Overview" : activeView.toUpperCase()}</strong>
          </div>
          <div className="top-actions">
            <span className="connection"><span />{apiStatus}</span>
            <div className="user-avatar small">{user.email[0]?.toUpperCase()}</div>
          </div>
        </header>

        {notice && (
          <div style={{ margin: "16px 0", padding: "10px 14px", background: "#fdf8ee", border: "1px solid #ebd8a7", borderRadius: "8px", fontSize: "11px", color: "#87661b" }}>
            {notice}
          </div>
        )}

        {/* View Switching */}
        {activeView === "lifeos" ? (
          <LifeOSView token={token} />
        ) : activeView === "inboxzero" ? (
          <InboxZeroView token={token} />
        ) : activeView === "spendwise" ? (
          <SpendWiseView token={token} />
        ) : activeView === "docuvault" ? (
          <DocuVaultView
            token={token}
            onSwitchToDeck={(deckId) => {
              setSelectedDeckId(deckId);
              setActiveView("learnloop");
            }}
          />
        ) : activeView === "learnloop" ? (
          <LearnLoopView token={token} initialDeckId={selectedDeckId} />
        ) : activeView === "mealmind" ? (
          <MealMindView
            token={token}
            onCheckPrices={(itemName) => {
              setSelectedPriceQuery(itemName);
              setActiveView("pricepilot");
            }}
          />
        ) : activeView === "pricepilot" ? (
          <PricePilotView token={token} initialSearchQuery={selectedPriceQuery} />
        ) : activeView === "autoflow" ? (
          <AutoFlowView token={token} />
        ) : (
          <>
            <section className="welcome">
              <div>
                <p className="eyebrow">YOUR WORKSPACE</p>
                <h1>A little more room<br />for what matters.</h1>
                <p className="welcome-copy">Your personal workspace is ready. Pick any module or ask your AI assistant to manage tasks, emails, expenses, meals, and automations.</p>
              </div>
              <div className="welcome-art" aria-hidden="true">
                <div className="sun" />
                <div className="hill hill-back" />
                <div className="hill hill-front" />
                <span className="art-sparkle sparkle-one">✳</span>
                <span className="art-sparkle sparkle-two">✦</span>
              </div>
            </section>

            <section className="section-heading">
              <div><p className="eyebrow">YOUR SPACE</p><h2>All Modules Ready</h2></div>
              <span className="module-count">8 modules active</span>
            </section>
            <section className="module-grid" aria-label="Assistant modules">
              {modules.map((module, index) => (
                <div
                  className={`module-card card-${index + 1}`}
                  onClick={() => handleModuleClick(module.name, module.available)}
                  key={module.name}
                  style={{ cursor: "pointer" }}
                >
                  <span className="card-icon" aria-hidden="true">{module.icon}</span>
                  <span className="card-arrow" aria-hidden="true">↗</span>
                  <h3>{module.name}</h3>
                  <p>{module.detail}</p>
                  <span className="card-tag">READY</span>
                </div>
              ))}
            </section>
          </>
        )}

        {/* AI Assistant panel is available across views */}
        <section className="assistant-panel" aria-label="AI assistant">
          <div className="assistant-panel-heading">
            <div className="assistant-badge">✳</div>
            <div className="assistant-text">
              <strong>Your assistant</strong>
              <span>Ask questions or say &quot;Add a task: Finish slide deck by 5pm&quot;, &quot;Summarize inbox&quot;, &quot;What's for dinner?&quot; or &quot;Morning briefing&quot;</span>
            </div>
            <span className="assistant-status">CONNECTED</span>
          </div>
          {messages.length > 0 && (
            <div className="chat-messages" aria-live="polite">
              {messages.map((item, index) => (
                <p className={`chat-message ${item.role}`} key={`${index}-${item.role}`}>
                  <strong>{item.role === "user" ? "You" : "Assistant"}</strong>
                  {item.content}
                </p>
              ))}
              {sending && <p className="chat-waiting">Thinking…</p>}
            </div>
          )}
          <form className="chat-form" onSubmit={sendMessage}>
            <input
              type="text"
              placeholder="Ask anything or request an action across your modules…"
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
            />
            <button type="submit" disabled={sending || !prompt.trim()}>
              Send
            </button>
          </form>
          {chatError && <p className="chat-error">{chatError}</p>}
        </section>
      </main>
    </div>
  );
}

async function readError(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as { detail?: string };
    if (data && typeof data.detail === "string") return data.detail;
  } catch {
    // ignore
  }
  return `Request failed (${response.status})`;
}

export default App;
