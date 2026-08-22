import { createRoot } from "react-dom/client";
import { useCallback, useEffect, useMemo, useState } from "react";
import "./admin.css";
import {
  adminFetch,
  getOwnerToken,
  setOwnerToken,
  storeOwnerSession,
} from "./api.js";

function useQuery() {
  return useMemo(() => new URLSearchParams(window.location.search), []);
}

function LoginView({ onLoggedIn, onForgot }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const j = await adminFetch("/admin/login", {
        method: "POST",
        auth: false,
        body: { username, password },
      });
      storeOwnerSession(j);
      onLoggedIn(j);
    } catch (err) {
      setError(err.message || "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="admin-card" onSubmit={submit}>
      <h1>Owner login</h1>
      <p className="muted">Sign in to manage appointments and tickets.</p>
      <label htmlFor="user">Username</label>
      <input
        id="user"
        value={username}
        onChange={(e) => setUsername(e.target.value)}
        autoComplete="username"
        required
      />
      <label htmlFor="pass">Password</label>
      <input
        id="pass"
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        autoComplete="current-password"
        required
      />
      {error ? <div className="admin-error">{error}</div> : null}
      <button type="submit" disabled={busy}>
        {busy ? "Signing in…" : "Sign in"}
      </button>
      <button type="button" className="admin-link" onClick={onForgot}>
        Forgot password?
      </button>
    </form>
  );
}

function SetupView({ onDone }) {
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [codeSent, setCodeSent] = useState(false);

  async function sendCode(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setMsg("");
    try {
      await adminFetch("/admin/setup/request-email-code", {
        method: "POST",
        body: { email },
      });
      setCodeSent(true);
      setMsg("Verification code sent (check console email if EMAIL_PROVIDER=console).");
    } catch (err) {
      setError(err.message || "Failed to send code");
    } finally {
      setBusy(false);
    }
  }

  async function finish(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const j = await adminFetch("/admin/setup/verify-and-set-password", {
        method: "POST",
        body: { code, new_password: password },
      });
      storeOwnerSession(j);
      onDone(j);
    } catch (err) {
      setError(err.message || "Setup failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="admin-card">
      <h1>Complete setup</h1>
      <p className="muted">
        Bind an admin email and set a new password (min 10 characters). The default
        password will stop working after this.
      </p>
      <form onSubmit={sendCode}>
        <label htmlFor="email">Admin email</label>
        <input
          id="email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <button type="submit" disabled={busy}>
          Send verification code
        </button>
      </form>
      {codeSent ? (
        <form onSubmit={finish}>
          <label htmlFor="code">Verification code</label>
          <input
            id="code"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            required
          />
          <label htmlFor="npw">New password</label>
          <input
            id="npw"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={10}
            required
          />
          <button type="submit" disabled={busy}>
            Verify and save
          </button>
        </form>
      ) : null}
      {msg ? <div className="admin-ok">{msg}</div> : null}
      {error ? <div className="admin-error">{error}</div> : null}
    </div>
  );
}

function ForgotView({ onBack, initialToken }) {
  const [email, setEmail] = useState("");
  const [token, setToken] = useState(initialToken || "");
  const [password, setPassword] = useState("");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState(initialToken ? "reset" : "request");

  async function requestReset(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setMsg("");
    try {
      const j = await adminFetch("/admin/forgot-password", {
        method: "POST",
        auth: false,
        body: { email },
      });
      setMsg(j.detail || "If that email is registered, a reset link was sent.");
      setStep("reset");
    } catch (err) {
      setError(err.message || "Request failed");
    } finally {
      setBusy(false);
    }
  }

  async function doReset(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const j = await adminFetch("/admin/reset-password", {
        method: "POST",
        auth: false,
        body: { token, new_password: password },
      });
      setMsg(j.detail || "Password updated.");
      setTimeout(onBack, 1200);
    } catch (err) {
      setError(err.message || "Reset failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="admin-card">
      <h1>Reset password</h1>
      {step === "request" ? (
        <form onSubmit={requestReset}>
          <p className="muted">Enter the email bound during owner setup.</p>
          <label htmlFor="fe">Email</label>
          <input
            id="fe"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <button type="submit" disabled={busy}>
            Send reset link
          </button>
        </form>
      ) : (
        <form onSubmit={doReset}>
          <p className="muted">Paste the token from email (or use the link).</p>
          <label htmlFor="tok">Reset token</label>
          <input
            id="tok"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            required
          />
          <label htmlFor="rpw">New password</label>
          <input
            id="rpw"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={10}
            required
          />
          <button type="submit" disabled={busy}>
            Update password
          </button>
        </form>
      )}
      {msg ? <div className="admin-ok">{msg}</div> : null}
      {error ? <div className="admin-error">{error}</div> : null}
      <button type="button" className="admin-link" onClick={onBack}>
        Back to login
      </button>
    </div>
  );
}

function formatCountdown(startsAt, nowMs) {
  if (!startsAt) return "—";
  const start = new Date(startsAt).getTime();
  if (!Number.isFinite(start)) return "—";
  let diffMin = Math.floor((start - nowMs) / 60000);
  if (diffMin < 0) {
    return "Ended";
  }
  const h = Math.floor(diffMin / 60);
  const m = diffMin % 60;
  return h > 0 ? `${h} h ${m} m` : `${m} m`;
}

function AppointmentLocation({ value }) {
  const text = (value || "").trim();
  if (!text) return "—";
  if (/^https:\/\//i.test(text)) {
    return (
      <a href={text} target="_blank" rel="noopener noreferrer">
        {text}
      </a>
    );
  }
  return text;
}

function AppointmentsPanel() {
  const [status, setStatus] = useState("booked");
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [nowMs, setNowMs] = useState(() => Date.now());

  const load = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      const q = status ? `?status=${encodeURIComponent(status)}` : "";
      const j = await adminFetch(`/admin/appointments${q}`);
      setRows(j.appointments || []);
    } catch (err) {
      setError(err.message || "Failed to load");
    } finally {
      setBusy(false);
    }
  }, [status]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const id = setInterval(() => setNowMs(Date.now()), 30000);
    return () => clearInterval(id);
  }, []);

  async function cancel(id) {
    if (!window.confirm(`Cancel appointment ${id}?`)) return;
    try {
      await adminFetch(`/admin/appointments/${encodeURIComponent(id)}/cancel`, {
        method: "POST",
      });
      await load();
    } catch (err) {
      setError(err.message || "Cancel failed");
    }
  }

  return (
    <div>
      <div className="admin-filters">
        <div>
          <label htmlFor="st">Status</label>
          <select id="st" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="booked">booked</option>
            <option value="pending_payment">pending_payment</option>
            <option value="cancelled">cancelled</option>
            <option value="expired">expired</option>
            <option value="">all</option>
          </select>
        </div>
        <button type="button" className="admin-btn secondary" onClick={load} disabled={busy}>
          Refresh
        </button>
      </div>
      {error ? <div className="admin-error">{error}</div> : null}
      <div className="admin-table-wrap">
        <table className="admin-table">
          <thead>
            <tr>
              <th>When</th>
              <th>Countdown</th>
              <th>Service</th>
              <th>Customer</th>
              <th>Location</th>
              <th>Status</th>
              <th>Created</th>
              <th>ID</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((a) => (
              <tr key={a.appointment_id}>
                <td>{a.starts_at ? new Date(a.starts_at).toLocaleString() : "—"}</td>
                <td>
                  {a.status === "booked" || a.status === "pending_payment"
                    ? formatCountdown(a.starts_at, nowMs)
                    : "—"}
                </td>
                <td>{a.service_name || "—"}</td>
                <td>
                  {a.customer_name}
                  <br />
                  <span style={{ color: "#64748b" }}>{a.customer_email}</span>
                </td>
                <td style={{ maxWidth: 220, wordBreak: "break-all" }}>
                  <AppointmentLocation value={a.location_for_service} />
                </td>
                <td>{a.status}</td>
                <td>{a.created_at ? new Date(a.created_at).toLocaleString() : "—"}</td>
                <td>
                  <code>{a.appointment_id}</code>
                </td>
                <td className="admin-actions">
                  {a.status === "booked" ? (
                    <button type="button" className="admin-btn secondary" onClick={() => cancel(a.appointment_id)}>
                      Cancel
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
            {!rows.length ? (
              <tr>
                <td colSpan={9}>{busy ? "Loading…" : "No appointments"}</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TicketsPanel() {
  const [status, setStatus] = useState("open");
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [nowMs, setNowMs] = useState(() => Date.now());

  const load = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      const q = status ? `?status=${encodeURIComponent(status)}` : "";
      const j = await adminFetch(`/admin/tickets${q}`);
      setRows(j.tickets || []);
    } catch (err) {
      setError(err.message || "Failed to load");
    } finally {
      setBusy(false);
    }
  }, [status]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const id = setInterval(() => setNowMs(Date.now()), 30000);
    return () => clearInterval(id);
  }, []);

  async function setTicketStatus(id, next) {
    try {
      await adminFetch(`/admin/tickets/${encodeURIComponent(id)}`, {
        method: "PATCH",
        body: { status: next },
      });
      await load();
    } catch (err) {
      setError(err.message || "Update failed");
    }
  }

  return (
    <div>
      <div className="admin-filters">
        <div>
          <label htmlFor="tst">Status</label>
          <select id="tst" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="open">open</option>
            <option value="in_progress">in_progress</option>
            <option value="closed">closed</option>
            <option value="">all</option>
          </select>
        </div>
        <button type="button" className="admin-btn secondary" onClick={load} disabled={busy}>
          Refresh
        </button>
      </div>
      {error ? <div className="admin-error">{error}</div> : null}
      <div className="admin-table-wrap">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Ticket ID</th>
              <th>Respond by</th>
              <th>Countdown</th>
              <th>Priority</th>
              <th>Name</th>
              <th>Email</th>
              <th>Phone</th>
              <th>Summary</th>
              <th>Status</th>
              <th>Created</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((t) => (
              <tr key={t.ticket_id}>
                <td>
                  <code>{t.ticket_id}</code>
                </td>
                <td>{t.respond_by_display || t.respond_by || "—"}</td>
                <td>
                  {t.status === "open" || t.status === "in_progress"
                    ? formatCountdown(t.respond_by, nowMs)
                    : "—"}
                </td>
                <td>{t.priority}</td>
                <td>{t.name || "—"}</td>
                <td>{t.email || "—"}</td>
                <td>{t.phone || "—"}</td>
                <td>{t.summary}</td>
                <td>{t.status}</td>
                <td>{t.created_at ? new Date(t.created_at).toLocaleString() : "—"}</td>
                <td className="admin-actions">
                  {t.status !== "in_progress" ? (
                    <button
                      type="button"
                      className="admin-btn secondary"
                      onClick={() => setTicketStatus(t.ticket_id, "in_progress")}
                    >
                      In progress
                    </button>
                  ) : null}
                  {t.status !== "closed" ? (
                    <button
                      type="button"
                      className="admin-btn"
                      onClick={() => setTicketStatus(t.ticket_id, "closed")}
                    >
                      Close
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
            {!rows.length ? (
              <tr>
                <td colSpan={11}>{busy ? "Loading…" : "No tickets"}</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Dashboard({ session, onLogout }) {
  const [tab, setTab] = useState("appointments");

  return (
    <div className="admin-shell">
      <div className="admin-header">
        <div>
          <h1>Owner dashboard</h1>
          <p className="muted" style={{ margin: "4px 0 0" }}>
            {session?.username}
            {session?.email ? ` · ${session.email}` : ""}
          </p>
        </div>
        <button type="button" className="admin-btn secondary" onClick={onLogout}>
          Log out
        </button>
      </div>
      <div className="admin-tabs">
        <button
          type="button"
          className={tab === "appointments" ? "active" : ""}
          onClick={() => setTab("appointments")}
        >
          Appointments
        </button>
        <button
          type="button"
          className={tab === "tickets" ? "active" : ""}
          onClick={() => setTab("tickets")}
        >
          Tickets
        </button>
      </div>
      {tab === "appointments" ? <AppointmentsPanel /> : <TicketsPanel />}
    </div>
  );
}

function AdminApp() {
  const query = useQuery();
  const resetToken = query.get("reset") || "";
  const [view, setView] = useState(resetToken ? "forgot" : "boot");
  const [session, setSession] = useState(null);

  useEffect(() => {
    if (resetToken) return;
    const t = getOwnerToken();
    if (!t) {
      setView("login");
      return;
    }
    adminFetch("/admin/me")
      .then((me) => {
        setSession(me);
        setView(me.setup_required ? "setup" : "dashboard");
      })
      .catch(() => {
        setOwnerToken("");
        setView("login");
      });
  }, [resetToken]);

  function onLoggedIn(j) {
    setSession(j);
    setView(j.setup_required ? "setup" : "dashboard");
  }

  function logout() {
    setOwnerToken("");
    setSession(null);
    setView("login");
  }

  if (view === "boot") {
    return (
      <div className="admin-card">
        <p className="muted">Loading…</p>
      </div>
    );
  }
  if (view === "login") {
    return <LoginView onLoggedIn={onLoggedIn} onForgot={() => setView("forgot")} />;
  }
  if (view === "setup") {
    return (
      <SetupView
        onDone={(j) => {
          setSession(j);
          setView("dashboard");
        }}
      />
    );
  }
  if (view === "forgot") {
    return (
      <ForgotView
        initialToken={resetToken}
        onBack={() => {
          window.history.replaceState({}, "", "/admin.html");
          setView("login");
        }}
      />
    );
  }
  return <Dashboard session={session} onLogout={logout} />;
}

const root = document.getElementById("admin-root");
if (root) {
  createRoot(root).render(<AdminApp />);
}
