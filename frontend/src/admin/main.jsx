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

/** Display status labels with a capital first letter (API values stay lowercase). */
function formatStatusLabel(value) {
  if (value == null || value === "") return "All";
  const s = String(value);
  if (s === "expired") return "Expired (no payment)";
  if (s === "no_show") return "No-show";
  if (s === "completed") return "Completed";
  if (s === "pending_payment") return "Pending_payment";
  if (s === "in_progress") return "In_progress";
  return s.charAt(0).toUpperCase() + s.slice(1);
}

const ADMIN_PAGE_SIZE = 10;

function includesQuery(haystack, query) {
  if (!query) return true;
  return String(haystack ?? "")
    .toLowerCase()
    .includes(query.toLowerCase());
}

function filterAppointments(rows, query) {
  const q = (query || "").trim();
  if (!q) return rows;
  return rows.filter(
    (a) =>
      includesQuery(a.appointment_id, q) ||
      includesQuery(a.service_name, q) ||
      includesQuery(a.customer_name, q) ||
      includesQuery(a.customer_email, q),
  );
}

function filterTickets(rows, query) {
  const q = (query || "").trim();
  if (!q) return rows;
  return rows.filter(
    (t) =>
      includesQuery(t.ticket_id, q) ||
      includesQuery(t.summary, q) ||
      includesQuery(t.name, q) ||
      includesQuery(t.email, q) ||
      includesQuery(t.phone, q),
  );
}

function AdminPager({ page, pageCount, total, pageSize, onPrev, onNext }) {
  if (total === 0) return null;
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);
  return (
    <div className="admin-pager">
      <span>
        {from}–{to} of {total} · {pageSize} per page
      </span>
      <button
        type="button"
        className="admin-btn secondary"
        onClick={onPrev}
        disabled={page <= 1}
      >
        Prev
      </button>
      <span>
        Page {page} / {pageCount}
      </span>
      <button
        type="button"
        className="admin-btn secondary"
        onClick={onNext}
        disabled={page >= pageCount}
      >
        Next
      </button>
    </div>
  );
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

function isUpcoming(startsAt, nowMs) {
  if (!startsAt) return false;
  const t = new Date(startsAt).getTime();
  return Number.isFinite(t) && t > nowMs;
}

function isPastStart(startsAt, nowMs) {
  if (!startsAt) return false;
  const t = new Date(startsAt).getTime();
  return Number.isFinite(t) && t <= nowMs;
}

function RescheduleModal({ appointment, onClose, onDone }) {
  const [slots, setSlots] = useState([]);
  const [startIso, setStartIso] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError("");
      try {
        const j = await adminFetch(
          `/admin/appointments/${encodeURIComponent(appointment.appointment_id)}/slots`,
        );
        if (!cancelled) {
          setSlots(j.slots || []);
          setStartIso(j.slots?.[0]?.start_iso || "");
        }
      } catch (err) {
        if (!cancelled) setError(err.message || "Failed to load slots");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [appointment.appointment_id]);

  async function submit(e) {
    e.preventDefault();
    if (!startIso) return;
    setBusy(true);
    setError("");
    try {
      await adminFetch(
        `/admin/appointments/${encodeURIComponent(appointment.appointment_id)}/reschedule`,
        { method: "POST", body: { start_iso: startIso } },
      );
      onDone();
    } catch (err) {
      setError(err.message || "Reschedule failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="admin-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="admin-modal"
        role="dialog"
        aria-labelledby="reschedule-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="reschedule-title">Reschedule</h2>
        <p className="muted">
          {appointment.customer_name} · {appointment.service_name}
          <br />
          Current:{" "}
          {appointment.starts_at
            ? new Date(appointment.starts_at).toLocaleString()
            : "—"}
        </p>
        {loading ? <p className="muted">Loading open slots…</p> : null}
        {!loading && !slots.length ? (
          <p className="admin-error">No open slots in the next two weeks.</p>
        ) : null}
        {slots.length ? (
          <form onSubmit={submit}>
            <label htmlFor="slot">New date &amp; time</label>
            <select
              id="slot"
              value={startIso}
              onChange={(e) => setStartIso(e.target.value)}
              required
            >
              {slots.map((s) => (
                <option key={s.start_iso} value={s.start_iso}>
                  {s.label}
                </option>
              ))}
            </select>
            {error ? <div className="admin-error">{error}</div> : null}
            <div className="admin-modal-actions">
              <button type="button" className="admin-btn secondary" onClick={onClose}>
                Cancel
              </button>
              <button type="submit" className="admin-btn" disabled={busy || !startIso}>
                {busy ? "Saving…" : "Save new time"}
              </button>
            </div>
          </form>
        ) : (
          <div className="admin-modal-actions">
            <button type="button" className="admin-btn secondary" onClick={onClose}>
              Close
            </button>
          </div>
        )}
        {error && !slots.length ? <div className="admin-error">{error}</div> : null}
      </div>
    </div>
  );
}

function AppointmentsPanel() {
  const [status, setStatus] = useState("booked");
  const [searchInput, setSearchInput] = useState("");
  const [appliedSearch, setAppliedSearch] = useState("");
  const [page, setPage] = useState(1);
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [rescheduleAppt, setRescheduleAppt] = useState(null);

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
    setPage(1);
    load();
  }, [load]);

  useEffect(() => {
    const id = setInterval(() => setNowMs(Date.now()), 30000);
    return () => clearInterval(id);
  }, []);

  const filtered = useMemo(
    () => filterAppointments(rows, appliedSearch),
    [rows, appliedSearch],
  );
  const pageCount = Math.max(1, Math.ceil(filtered.length / ADMIN_PAGE_SIZE) || 1);
  const safePage = Math.min(page, pageCount);
  const pageRows = filtered.slice(
    (safePage - 1) * ADMIN_PAGE_SIZE,
    safePage * ADMIN_PAGE_SIZE,
  );

  async function refresh() {
    setAppliedSearch(searchInput.trim());
    setPage(1);
    await load();
  }

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

  async function markOutcome(id, status) {
    const label = status === "no_show" ? "No-show" : "Completed";
    if (!window.confirm(`Mark appointment ${id} as ${label}?`)) return;
    try {
      await adminFetch(`/admin/appointments/${encodeURIComponent(id)}/outcome`, {
        method: "POST",
        body: { status },
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
          <label htmlFor="st">Status</label>
          <select id="st" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="booked">{formatStatusLabel("booked")}</option>
            <option value="pending_payment">{formatStatusLabel("pending_payment")}</option>
            <option value="cancelled">{formatStatusLabel("cancelled")}</option>
            <option value="expired">{formatStatusLabel("expired")}</option>
            <option value="no_show">{formatStatusLabel("no_show")}</option>
            <option value="completed">{formatStatusLabel("completed")}</option>
            <option value="">{formatStatusLabel("all")}</option>
          </select>
        </div>
        <div className="admin-search-wrap">
          <label htmlFor="appt-q">Search</label>
          <input
            id="appt-q"
            type="search"
            className="admin-search"
            placeholder="ID, service, name, or email"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                refresh();
              }
            }}
          />
        </div>
        <button type="button" className="admin-btn secondary" onClick={refresh} disabled={busy}>
          Refresh
        </button>
      </div>
      {error ? <div className="admin-error">{error}</div> : null}
      <div className="admin-table-wrap">
        <table className="admin-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>When</th>
              <th>Countdown</th>
              <th>Service</th>
              <th>Customer</th>
              <th>Location</th>
              <th>Status</th>
              <th>Created</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {pageRows.map((a) => (
              <tr key={a.appointment_id}>
                <td>
                  <code>{a.appointment_id}</code>
                </td>
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
                <td>{formatStatusLabel(a.status)}</td>
                <td>{a.created_at ? new Date(a.created_at).toLocaleString() : "—"}</td>
                <td>
                  <div className="admin-actions">
                    {a.status === "booked" ? (
                      <>
                        <button
                          type="button"
                          className="admin-btn secondary"
                          onClick={() => cancel(a.appointment_id)}
                        >
                          Cancel
                        </button>
                        {isUpcoming(a.starts_at, nowMs) ? (
                          <button
                            type="button"
                            className="admin-btn secondary"
                            onClick={() => setRescheduleAppt(a)}
                          >
                            Reschedule
                          </button>
                        ) : null}
                        {isPastStart(a.starts_at, nowMs) ? (
                          <>
                            <button
                              type="button"
                              className="admin-btn secondary"
                              onClick={() => markOutcome(a.appointment_id, "no_show")}
                            >
                              Mark No-show
                            </button>
                            <button
                              type="button"
                              className="admin-btn secondary"
                              onClick={() => markOutcome(a.appointment_id, "completed")}
                            >
                              Mark Completed
                            </button>
                          </>
                        ) : null}
                      </>
                    ) : null}
                  </div>
                </td>
              </tr>
            ))}
            {!pageRows.length ? (
              <tr>
                <td colSpan={9}>{busy ? "Loading…" : "No appointments"}</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
      <AdminPager
        page={safePage}
        pageCount={pageCount}
        total={filtered.length}
        pageSize={ADMIN_PAGE_SIZE}
        onPrev={() => setPage((p) => Math.max(1, p - 1))}
        onNext={() => setPage((p) => Math.min(pageCount, p + 1))}
      />
      {rescheduleAppt ? (
        <RescheduleModal
          appointment={rescheduleAppt}
          onClose={() => setRescheduleAppt(null)}
          onDone={async () => {
            setRescheduleAppt(null);
            await load();
          }}
        />
      ) : null}
    </div>
  );
}

function TicketsPanel({ onReply }) {
  const [status, setStatus] = useState("open");
  const [searchInput, setSearchInput] = useState("");
  const [appliedSearch, setAppliedSearch] = useState("");
  const [page, setPage] = useState(1);
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [notesTicket, setNotesTicket] = useState(null);

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
    setPage(1);
    load();
  }, [load]);

  useEffect(() => {
    const id = setInterval(() => setNowMs(Date.now()), 30000);
    return () => clearInterval(id);
  }, []);

  const filtered = useMemo(
    () => filterTickets(rows, appliedSearch),
    [rows, appliedSearch],
  );
  const pageCount = Math.max(1, Math.ceil(filtered.length / ADMIN_PAGE_SIZE) || 1);
  const safePage = Math.min(page, pageCount);
  const pageRows = filtered.slice(
    (safePage - 1) * ADMIN_PAGE_SIZE,
    safePage * ADMIN_PAGE_SIZE,
  );

  async function refresh() {
    setAppliedSearch(searchInput.trim());
    setPage(1);
    await load();
  }

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
            <option value="open">{formatStatusLabel("open")}</option>
            <option value="in_progress">{formatStatusLabel("in_progress")}</option>
            <option value="closed">{formatStatusLabel("closed")}</option>
            <option value="">{formatStatusLabel("all")}</option>
          </select>
        </div>
        <div className="admin-search-wrap">
          <label htmlFor="ticket-q">Search</label>
          <input
            id="ticket-q"
            type="search"
            className="admin-search"
            placeholder="ID, summary, name, email, or phone"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                refresh();
              }
            }}
          />
        </div>
        <button type="button" className="admin-btn secondary" onClick={refresh} disabled={busy}>
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
              <th>Note</th>
              <th>Created</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {pageRows.map((t) => (
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
                <td>{formatStatusLabel(t.status)}</td>
                <td
                  className="admin-note-cell"
                  title={t.latest_note || ""}
                >
                  {t.latest_note
                    ? t.latest_note.length > 80
                      ? `${t.latest_note.slice(0, 80)}…`
                      : t.latest_note
                    : "—"}
                </td>
                <td>{t.created_at ? new Date(t.created_at).toLocaleString() : "—"}</td>
                <td>
                  <div className="admin-actions">
                    {t.status !== "closed" ? (
                      <>
                        <button
                          type="button"
                          className="admin-btn secondary"
                          onClick={() => onReply?.(t.ticket_id)}
                        >
                          Reply
                        </button>
                        <button
                          type="button"
                          className="admin-btn secondary"
                          onClick={() => setNotesTicket(t)}
                        >
                          Notes
                        </button>
                      </>
                    ) : null}
                    {t.status === "open" ? (
                      <button
                        type="button"
                        className="admin-btn secondary"
                        onClick={() => setTicketStatus(t.ticket_id, "in_progress")}
                      >
                        In progress
                      </button>
                    ) : null}
                    {t.status === "closed" ? (
                      <button
                        type="button"
                        className="admin-btn secondary"
                        onClick={() => {
                          if (
                            !window.confirm(
                              `Reopen ticket ${t.ticket_id}? It will move back to in progress.`,
                            )
                          ) {
                            return;
                          }
                          setTicketStatus(t.ticket_id, "in_progress");
                        }}
                      >
                        Reopen
                      </button>
                    ) : null}
                    {t.status !== "closed" ? (
                      <button
                        type="button"
                        className="admin-btn"
                        onClick={() => {
                          if (
                            !window.confirm(
                              `Close ticket ${t.ticket_id}? Mark it as resolved.`,
                            )
                          ) {
                            return;
                          }
                          setTicketStatus(t.ticket_id, "closed");
                        }}
                      >
                        Close
                      </button>
                    ) : null}
                  </div>
                </td>
              </tr>
            ))}
            {!pageRows.length ? (
              <tr>
                <td colSpan={12}>{busy ? "Loading…" : "No tickets"}</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
      <AdminPager
        page={safePage}
        pageCount={pageCount}
        total={filtered.length}
        pageSize={ADMIN_PAGE_SIZE}
        onPrev={() => setPage((p) => Math.max(1, p - 1))}
        onNext={() => setPage((p) => Math.min(pageCount, p + 1))}
      />
      {notesTicket ? (
        <TicketNotesModal
          ticket={notesTicket}
          onClose={() => setNotesTicket(null)}
          onSaved={async () => {
            setNotesTicket(null);
            await load();
          }}
        />
      ) : null}
    </div>
  );
}

const PHONE_OUTCOME_LABELS = {
  reached: "Reached",
  no_answer: "No answer",
  left_voicemail: "Left voicemail",
  wrong_number: "Wrong number",
  other: "Other",
};

function activityKindLabel(kind) {
  if (kind === "note") return "Note";
  if (kind === "phone") return "Phone";
  if (kind === "email_out") return "Email reply";
  return kind;
}

function TicketNotesModal({ ticket, onClose, onSaved }) {
  const [body, setBody] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await adminFetch(`/admin/tickets/${encodeURIComponent(ticket.ticket_id)}/notes`, {
        method: "POST",
        body: { body },
      });
      onSaved?.();
    } catch (err) {
      setError(err.message || "Failed to save note");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="admin-modal-backdrop" onClick={onClose} role="presentation">
      <div
        className="admin-modal"
        role="dialog"
        aria-labelledby="notes-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="notes-title">Internal note</h2>
        <p className="muted">
          Ticket <code>{ticket.ticket_id}</code> — not emailed to the customer.
        </p>
        <form onSubmit={submit}>
          <label htmlFor="note-body">Note</label>
          <textarea
            id="note-body"
            rows={5}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            required
            minLength={2}
            placeholder="Internal follow-up notes…"
          />
          {error ? <div className="admin-error">{error}</div> : null}
          <div className="admin-modal-actions">
            <button type="button" className="admin-btn secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="admin-btn" disabled={busy}>
              Save note
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function TicketReplyPage({ ticketId, onBack }) {
  const [ticket, setTicket] = useState(null);
  const [activities, setActivities] = useState([]);
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");
  const [busy, setBusy] = useState(false);
  const [phoneOutcome, setPhoneOutcome] = useState("reached");
  const [phoneBody, setPhoneBody] = useState("");
  const [replyBody, setReplyBody] = useState("");

  const load = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      const j = await adminFetch(`/admin/tickets/${encodeURIComponent(ticketId)}`);
      setTicket(j);
      setActivities(j.activities || []);
    } catch (err) {
      setError(err.message || "Failed to load ticket");
    } finally {
      setBusy(false);
    }
  }, [ticketId]);

  useEffect(() => {
    load();
  }, [load]);

  async function savePhone(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setOk("");
    try {
      await adminFetch(`/admin/tickets/${encodeURIComponent(ticketId)}/phone-log`, {
        method: "POST",
        body: { phone_outcome: phoneOutcome, body: phoneBody },
      });
      setPhoneBody("");
      setOk("Phone call logged.");
      await load();
    } catch (err) {
      setError(err.message || "Failed to save phone log");
    } finally {
      setBusy(false);
    }
  }

  async function sendReply(e) {
    e.preventDefault();
    if (!window.confirm(`Send email reply to ${ticket?.email || "customer"}?`)) return;
    setBusy(true);
    setError("");
    setOk("");
    try {
      await adminFetch(`/admin/tickets/${encodeURIComponent(ticketId)}/reply`, {
        method: "POST",
        body: { body: replyBody },
      });
      setReplyBody("");
      setOk("Email reply sent.");
      await load();
    } catch (err) {
      setError(err.message || "Failed to send reply");
    } finally {
      setBusy(false);
    }
  }

  const closed = ticket?.status === "closed";

  return (
    <div className="admin-reply-page">
      <div className="admin-reply-toolbar">
        <button type="button" className="admin-btn secondary" onClick={onBack}>
          ← Back to tickets
        </button>
        <h2 style={{ margin: 0 }}>Reply — {ticketId}</h2>
      </div>
      {error ? <div className="admin-error">{error}</div> : null}
      {ok ? <div className="admin-ok">{ok}</div> : null}
      {!ticket && busy ? <p className="muted">Loading…</p> : null}
      {ticket ? (
        <>
          <div className="admin-reply-card">
            <h3>Ticket</h3>
            <dl className="admin-ticket-meta">
              <div>
                <dt>Customer name</dt>
                <dd>{ticket.name || "—"}</dd>
              </div>
              <div>
                <dt>Telephone</dt>
                <dd>{ticket.phone || "—"}</dd>
              </div>
              <div>
                <dt>Email</dt>
                <dd>{ticket.email || "—"}</dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd>{formatStatusLabel(ticket.status)}</dd>
              </div>
              <div>
                <dt>Priority</dt>
                <dd>{ticket.priority || "—"}</dd>
              </div>
              <div>
                <dt>Preferred call</dt>
                <dd>{ticket.preferred_call_window || "—"}</dd>
              </div>
              <div>
                <dt>Respond by</dt>
                <dd>{ticket.respond_by_display || "—"}</dd>
              </div>
            </dl>
            <p className="admin-ticket-summary">
              <strong>Summary</strong>
              <br />
              {ticket.summary}
            </p>
          </div>

          {closed ? (
            <p className="muted">This ticket is closed. Reopen it to reply or log calls.</p>
          ) : (
            <>
              <form className="admin-reply-card" onSubmit={savePhone}>
                <h3>1) Phone call log</h3>
                <label htmlFor="phone-outcome">Outcome</label>
                <select
                  id="phone-outcome"
                  value={phoneOutcome}
                  onChange={(e) => setPhoneOutcome(e.target.value)}
                >
                  {(ticket.phone_outcomes || Object.keys(PHONE_OUTCOME_LABELS)).map((k) => (
                    <option key={k} value={k}>
                      {PHONE_OUTCOME_LABELS[k] || k}
                    </option>
                  ))}
                </select>
                <label htmlFor="phone-notes">Call notes</label>
                <textarea
                  id="phone-notes"
                  rows={4}
                  value={phoneBody}
                  onChange={(e) => setPhoneBody(e.target.value)}
                  required
                  minLength={2}
                  placeholder="What was discussed on the call…"
                />
                <button type="submit" className="admin-btn secondary" disabled={busy}>
                  Save phone log
                </button>
              </form>

              <form className="admin-reply-card" onSubmit={sendReply}>
                <h3>2) Email reply</h3>
                <p className="muted">Sends to {ticket.email}</p>
                <label htmlFor="reply-body">Reply</label>
                <textarea
                  id="reply-body"
                  rows={8}
                  value={replyBody}
                  onChange={(e) => setReplyBody(e.target.value)}
                  required
                  minLength={2}
                  placeholder="Write the email reply to the customer…"
                />
                <button type="submit" className="admin-btn" disabled={busy}>
                  Send email
                </button>
              </form>
            </>
          )}

          <div className="admin-reply-card">
            <h3>History</h3>
            {!activities.length ? (
              <p className="muted">No notes, calls, or replies yet.</p>
            ) : (
              <ul className="admin-activity-list">
                {activities.map((a) => (
                  <li key={a.id}>
                    <div className="admin-activity-meta">
                      <strong>{activityKindLabel(a.kind)}</strong>
                      {a.phone_outcome
                        ? ` · ${PHONE_OUTCOME_LABELS[a.phone_outcome] || a.phone_outcome}`
                        : ""}
                      {" · "}
                      {a.created_at ? new Date(a.created_at).toLocaleString() : ""}
                      {a.created_by ? ` · ${a.created_by}` : ""}
                    </div>
                    <div className="admin-activity-body">{a.body}</div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      ) : null}
    </div>
  );
}

function Dashboard({ session, onLogout }) {
  const [tab, setTab] = useState("appointments");
  const [replyTicketId, setReplyTicketId] = useState(null);

  if (replyTicketId) {
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
        <TicketReplyPage
          ticketId={replyTicketId}
          onBack={() => {
            setReplyTicketId(null);
            setTab("tickets");
          }}
        />
      </div>
    );
  }

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
      {tab === "appointments" ? (
        <AppointmentsPanel />
      ) : (
        <TicketsPanel onReply={(id) => setReplyTicketId(id)} />
      )}
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
