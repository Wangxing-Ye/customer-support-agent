/** Resolve backend API base from current page origin. */
export function getApiBase() {
  const h = window.location.hostname;
  if (h === "localhost" || h === "127.0.0.1") {
    return `${window.location.protocol}//${h}:8000`;
  }
  return "http://127.0.0.1:8000";
}

export const API_BASE = getApiBase();
export const CHAT_URL = `${API_BASE}/chat`;
export const TRANSCRIBE_URL = `${API_BASE}/transcribe`;
export const TTS_URL = `${API_BASE}/tts`;
export const TOKEN_URL = `${API_BASE}/auth/token`;

export const TOKEN_KEY = "abc_chat_jwt";
export const MAX_WORDS = 50;
