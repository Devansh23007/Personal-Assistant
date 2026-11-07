import { FormEvent, useEffect, useState } from "react";
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
  { name: "AutoFlow", detail: "Connected workflows", icon: "⤳", available: false },
];

type User = { id: number; email: string };
type ChatMessage = { role: "user" | "assistant"; content: string };

function App() {
  const [token, setToken] = useState(() => sessionStorage.getItem("access_token") ?? "");
  const [user, setUser] = useState<User | null>(null);
  const [authLoading, setAuthLoading] = useState(Boolean(token));
  const [apiStatus, setApiStatus] = useState("Checking API…");

  useEffect(() => {
    fetch("/api/health")
      .then((response) => response.json())
      .then((data: { status: string; assistant: string }) => {
        setApiStatus(data.status === "ok" ? "API online" : "API offline");
      })
      .catch(() => setApiStatus("API offline"));
  }, []);

  useEffect(() => {
    if (!token) {
      setAuthLoading(false);
      return;
    }
    fetch("/api/auth/me", { headers: { Authorization: `Bearer ${token}` } })
      .then((response) => {
        if (!response.ok) throw new Error("Session expired");
        return response.json() as Promise<User>;
      })
      .then(setUser)
      .catch(() => {
        sessionStorage.removeItem("access_token");
        setToken("");
      })
      .finally(() => setAuthLoading(false));
  }, [token]);

  function onAuthenticated(accessToken: string, account: User) {
    sessionStorage.setItem("access_token", accessToken);
    setToken(accessToken);
    setUser(account);
  }

  function signOut() {
    sessionStorage.removeItem("access_token");
    setToken("");
    setUser(null);
  }

  if (authLoading) return <div className="loading-screen">Opening your workspace…</div>;
  if (!token || !user) return <AuthScreen onAuthenticated={onAuthenticated} />;

  return <Dashboard user={user} token={token} apiStatus={apiStatus} onSignOut={signOut} />;
}

function AuthScreen({ onAuthenticated }: { onAuthenticated: (token: string, user: User) => void }) {
  const [registering, setRegistering] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (registering) {
        const response = await fetch("/api/auth/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password }),
        });
        if (!response.ok) throw new Error(await readError(response));
      }

      const response = await fetch("/api/auth/token", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ username: email, password }),
      });
      if (!response.ok) throw new Error(await readError(response));
      const auth = (await response.json()) as { access_token: string };
      const accountResponse = await fetch("/api/auth/me", {
        headers: { Authorization: `Bearer ${auth.access_token}` },
      });
      if (!accountResponse.ok) throw new Error("Could not load your account. Please sign in again.");
      onAuthenticated(auth.access_token, (await accountResponse.json()) as User);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not sign in. Check the backend and try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-page">
      <div className="auth-card">
        <a className="brand auth-brand" href="#home">
          <span className="brand-mark">p</span>
          <span>personal<span className="brand-light">assistant</span></span>
        </a>
        <p className="eyebrow">YOUR PERSONAL WORKSPACE</p>
        <h1>{registering ? "Make space for what matters." : "Welcome back."}</h1>
        <p className="auth-copy">{registering ? "Create your private workspace to get started." : "Sign in to open your personal workspace."}</p>
        <form className="auth-form" onSubmit={submit}>
          <label htmlFor="email">Email address</label>
          <input id="email" type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} />
          <label htmlFor="password">Password</label>
          <input id="password" type="password" autoComplete={registering ? "new-password" : "current-password"} minLength={registering ? 10 : 1} maxLength={128} required value={password} onChange={(event) => setPassword(event.target.value)} />
          {registering && <small className="field-hint">Use at least 10 characters.</small>}
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="primary-button" disabled={busy}>{busy ? "Please wait…" : registering ? "Create account" : "Sign in"}</button>
        </form>
        <p className="auth-switch">
          {registering ? "Already have an account?" : "New to the workspace?"}{" "}
          <button onClick={() => { setRegistering(!registering); setError(""); }}>
            {registering ? "Sign in" : "Create an account"}
          </button>
        </p>
        <p className="auth-note">Your account is stored in the local project database.</p>
      </div>
    </main>
  );
}

function Dashboard({ user, token, apiStatus, onSignOut }: { user: User; token: string; apiStatus: string; onSignOut: () => void }) {
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
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
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
      setTimeout(() => setNotice(""), 3500);
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#home" onClick={(e) => { e.preventDefault(); setActiveView("overview"); }} aria-label="Personal Assistant home">
          <span className="brand-mark">p</span>
          <span>personal<span className="brand-light">assistant</span></span>
        </a>
        <div className="nav-label">WORKSPACE</div>
        <nav aria-label="Modules">
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
        <button className="account-row" onClick={onSignOut} title="Sign out">
          <span className="user-avatar">{user.email[0]?.toUpperCase()}</span>
          <span><strong>{user.email}</strong><small>Personal account · Sign out</small></span>
          <span className="more-button">↗</span>
        </button>
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
        ) : (
          <>
            <section className="welcome">
              <div>
                <p className="eyebrow">YOUR WORKSPACE</p>
                <h1>A little more room<br />for what matters.</h1>
                <p className="welcome-copy">Your personal workspace is ready. Start with one thing you want to get done today.</p>
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
              <div><p className="eyebrow">YOUR SPACE</p><h2>Pick up where you are</h2></div>
              <span className="module-count">8 modules</span>
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
                  {module.available && <span className="card-tag">READY (PHASE 2)</span>}
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
              <span>Ask questions or say &quot;Add a task: Finish slide deck by 5pm&quot; or &quot;Show my tasks&quot;</span>
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
          {chatError && <p className="chat-error" role="alert">{chatError}</p>}
          <form className="chat-form" onSubmit={sendMessage}>
            <input
              aria-label="Message your assistant"
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder="What would you like help with? (e.g. 'Log expense $45 for groceries', 'Spending summary', 'Tasks', 'Emails')..."
              maxLength={8000}
            />
            <button disabled={sending || !prompt.trim()} aria-label="Send message">{sending ? "…" : "Send ↗"}</button>
          </form>
          <p className="chat-footnote">
            When configured with an LLM key, your assistant can manage LifeOS tasks, triage InboxZero emails, and log/track SpendWise expenses.
          </p>
        </section>

        <footer>
          <span>PERSONAL ASSISTANT <i>·</i> YOUR SPACE, AT YOUR PACE</span>
          <span>PHASE 4: SPENDWISE ACTIVE</span>
        </footer>
      </main>
    </div>
  );
}

async function readError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: string };
    return body.detail ?? `Request failed (${response.status})`;
  } catch {
    return `Request failed (${response.status})`;
  }
}

export default App;
