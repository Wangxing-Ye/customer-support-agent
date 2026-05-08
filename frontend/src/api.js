import { CHAT_URL, TRANSCRIBE_URL, TTS_URL } from "./config.js";
import { ensureToken, clearToken } from "./auth.js";

export async function fetchChat(message, retryOn401 = true) {
  const token = await ensureToken();
  const res = await fetch(CHAT_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ message }),
  });
  if (res.status === 401 && retryOn401) {
    clearToken();
    return fetchChat(message, false);
  }
  return res;
}

export async function fetchTts(message, retryOn401 = true) {
  const token = await ensureToken();
  const res = await fetch(TTS_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ message }),
  });
  if (res.status === 401 && retryOn401) {
    clearToken();
    return fetchTts(message, false);
  }
  return res;
}

export async function fetchTranscribe(blob, filename, retryOn401 = true) {
  const token = await ensureToken();
  const fd = new FormData();
  fd.append("file", blob, filename);
  const res = await fetch(TRANSCRIBE_URL, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: fd,
  });
  if (res.status === 401 && retryOn401) {
    clearToken();
    return fetchTranscribe(blob, filename, false);
  }
  return res;
}

export async function playAssistantAudio(text) {
  const clean = String(text || "").trim();
  if (!clean) return;
  try {
    const res = await fetchTts(clean);
    if (!res.ok) {
      try {
        const errBody = await res.json();
        console.warn("TTS failed:", errBody.detail || errBody);
      } catch {
        console.warn("TTS failed with status", res.status);
      }
      return;
    }
    const buf = await res.arrayBuffer();
    const blob = new Blob([buf], { type: "audio/mpeg" });
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audio.onended = () => URL.revokeObjectURL(url);
    audio.onerror = () => URL.revokeObjectURL(url);
    audio.play().catch(() => URL.revokeObjectURL(url));
  } catch {
    /* text bubble already shown */
  }
}
