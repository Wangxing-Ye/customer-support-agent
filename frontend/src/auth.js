import {
  TOKEN_KEY,
  TOKEN_URL,
  REFRESH_URL,
  TOKEN_EXPIRES_AT_KEY,
  MAX_WORDS_KEY,
  DEFAULT_MAX_WORDS,
} from "./config.js";

const DEFAULT_REFRESH_SKEW_SECONDS = 300;

function storeTokenResponse(j) {
  const t = j.access_token;
  if (!t) throw new Error("token");
  sessionStorage.setItem(TOKEN_KEY, t);

  const expiresAt =
    typeof j.expires_at === "number"
      ? j.expires_at
      : Math.floor(Date.now() / 1000) + (parseInt(j.expires_in, 10) || 1800);
  sessionStorage.setItem(TOKEN_EXPIRES_AT_KEY, String(expiresAt));

  if (typeof j.refresh_skew_seconds === "number") {
    sessionStorage.setItem("pst_refresh_skew", String(j.refresh_skew_seconds));
  }

  const maxWords = parseInt(j.max_message_words, 10);
  sessionStorage.setItem(
    MAX_WORDS_KEY,
    String(Number.isFinite(maxWords) && maxWords > 0 ? maxWords : DEFAULT_MAX_WORDS),
  );
  return t;
}

function refreshSkewSeconds() {
  const n = parseInt(sessionStorage.getItem("pst_refresh_skew") || "", 10);
  return Number.isFinite(n) && n >= 0 ? n : DEFAULT_REFRESH_SKEW_SECONDS;
}

function secondsUntilExpiry() {
  const exp = parseInt(sessionStorage.getItem(TOKEN_EXPIRES_AT_KEY) || "", 10);
  if (!Number.isFinite(exp)) return -1;
  return exp - Math.floor(Date.now() / 1000);
}

async function issueNewToken() {
  const r = await fetch(TOKEN_URL, { method: "POST" });
  if (r.status === 429) {
    const retry = r.headers.get("Retry-After") || "60";
    throw new Error(`token_rate_limited:${retry}`);
  }
  if (!r.ok) throw new Error("token");
  return storeTokenResponse(await r.json());
}

async function refreshToken(current) {
  const r = await fetch(REFRESH_URL, {
    method: "POST",
    headers: { Authorization: `Bearer ${current}` },
  });
  if (r.status === 429) {
    const retry = r.headers.get("Retry-After") || "60";
    throw new Error(`token_rate_limited:${retry}`);
  }
  if (!r.ok) throw new Error("refresh");
  return storeTokenResponse(await r.json());
}

/**
 * Ensure a valid anonymous session JWT.
 * Issues a new token, or silently refreshes when within refresh_skew of expiry.
 */
export async function ensureToken() {
  let t = sessionStorage.getItem(TOKEN_KEY);
  const remaining = secondsUntilExpiry();

  if (t && remaining > refreshSkewSeconds()) {
    return t;
  }

  if (t && remaining > 0) {
    try {
      return await refreshToken(t);
    } catch {
      clearToken();
    }
  }

  return issueNewToken();
}

export function clearToken() {
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(TOKEN_EXPIRES_AT_KEY);
  sessionStorage.removeItem("pst_refresh_skew");
  sessionStorage.removeItem(MAX_WORDS_KEY);
  sessionStorage.removeItem("pst_chat_thread");
}
