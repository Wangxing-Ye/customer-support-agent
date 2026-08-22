import { API_BASE } from "../config.js";

export const OWNER_TOKEN_KEY = "pst_owner_jwt";

export function getOwnerToken() {
  return sessionStorage.getItem(OWNER_TOKEN_KEY) || "";
}

export function setOwnerToken(token) {
  if (token) sessionStorage.setItem(OWNER_TOKEN_KEY, token);
  else sessionStorage.removeItem(OWNER_TOKEN_KEY);
}

export function storeOwnerSession(j) {
  if (j?.access_token) setOwnerToken(j.access_token);
  return j;
}

async function parseError(r) {
  try {
    const j = await r.json();
    if (typeof j.detail === "string") return j.detail;
    if (Array.isArray(j.detail)) {
      return j.detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
    }
    return r.statusText || "Request failed";
  } catch {
    return r.statusText || "Request failed";
  }
}

export async function adminFetch(path, { method = "GET", body, auth = true } = {}) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth) {
    const t = getOwnerToken();
    if (t) headers.Authorization = `Bearer ${t}`;
  }
  const r = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    const detail = await parseError(r);
    const err = new Error(detail);
    err.status = r.status;
    throw err;
  }
  if (r.status === 204) return null;
  return r.json();
}
