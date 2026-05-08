import { TOKEN_KEY, TOKEN_URL } from "./config.js";

export async function ensureToken() {
  let t = sessionStorage.getItem(TOKEN_KEY);
  if (t) return t;
  const r = await fetch(TOKEN_URL, { method: "POST" });
  if (!r.ok) throw new Error("token");
  const j = await r.json();
  t = j.access_token;
  if (!t) throw new Error("token");
  sessionStorage.setItem(TOKEN_KEY, t);
  return t;
}

export function clearToken() {
  sessionStorage.removeItem(TOKEN_KEY);
}
