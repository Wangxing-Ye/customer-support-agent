import { TOKEN_KEY, TOKEN_URL, MAX_WORDS_KEY, DEFAULT_MAX_WORDS } from "./config.js";

export async function ensureToken() {
  let t = sessionStorage.getItem(TOKEN_KEY);
  let words = sessionStorage.getItem(MAX_WORDS_KEY);
  if (t && words) return t;

  const r = await fetch(TOKEN_URL, { method: "POST" });
  if (!r.ok) throw new Error("token");
  const j = await r.json();
  t = j.access_token;
  if (!t) throw new Error("token");
  sessionStorage.setItem(TOKEN_KEY, t);

  const maxWords = parseInt(j.max_message_words, 10);
  sessionStorage.setItem(
    MAX_WORDS_KEY,
    String(Number.isFinite(maxWords) && maxWords > 0 ? maxWords : DEFAULT_MAX_WORDS),
  );
  return t;
}

export function clearToken() {
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(MAX_WORDS_KEY);
}
