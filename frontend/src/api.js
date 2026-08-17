import { CHAT_URL, CHAT_STREAM_URL, TRANSCRIBE_URL, TTS_URL, THREAD_KEY, PAY_STATUS_URL } from "./config.js";
import { ensureToken, clearToken } from "./auth.js";

export function getThreadId() {
  let t = sessionStorage.getItem(THREAD_KEY);
  if (!t) {
    t = crypto.randomUUID();
    sessionStorage.setItem(THREAD_KEY, t);
  }
  return t;
}

export function setThreadId(id) {
  if (id) sessionStorage.setItem(THREAD_KEY, id);
}

export async function fetchChat(message, retryOn401 = true) {
  const token = await ensureToken();
  const res = await fetch(CHAT_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ message, thread_id: getThreadId() }),
  });
  if (res.status === 401 && retryOn401) {
    clearToken();
    return fetchChat(message, false);
  }
  if (res.ok) {
    try {
      const data = await res.clone().json();
      if (data.thread_id) setThreadId(data.thread_id);
    } catch {
      /* ignore */
    }
  }
  return res;
}

/**
 * Stream chat via SSE. Calls onToken(text), onStatus(status), onDone(), onError(msg).
 * Returns the full assembled assistant text.
 */
export async function streamChat(message, { onToken, onStatus, onDone, onError } = {}, retryOn401 = true) {
  const token = await ensureToken();
  const res = await fetch(CHAT_STREAM_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      Accept: "text/event-stream",
    },
    body: JSON.stringify({ message, thread_id: getThreadId() }),
  });

  if (res.status === 401 && retryOn401) {
    clearToken();
    return streamChat(message, { onToken, onStatus, onDone, onError }, false);
  }
  if (!res.ok) {
    const err = `Chat stream failed (${res.status})`;
    onError?.(err);
    throw new Error(err);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let assembled = "";
  let eventName = "message";

  const handleBlock = (block) => {
    const lines = block.split("\n");
    let dataLines = [];
    for (const line of lines) {
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trim());
      }
    }
    if (!dataLines.length) return;
    let payload = {};
    try {
      payload = JSON.parse(dataLines.join("\n"));
    } catch {
      payload = { text: dataLines.join("\n") };
    }
    if (payload.thread_id) setThreadId(payload.thread_id);
    if (eventName === "token" && payload.text) {
      assembled += payload.text;
      onToken?.(payload.text, assembled);
    } else if (eventName === "status") {
      onStatus?.(payload.status || "working");
    } else if (eventName === "error") {
      onError?.(payload.detail || "Stream error");
    } else if (eventName === "done") {
      onDone?.(assembled);
    }
    eventName = "message";
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const part of parts) {
      if (part.trim()) handleBlock(part);
    }
  }
  if (buffer.trim()) handleBlock(buffer);
  onDone?.(assembled);
  return assembled;
}

export async function fetchPayStatus(appointmentId) {
  const raw = String(appointmentId || "").trim();
  if (!raw) return null;
  const res = await fetch(
    `${PAY_STATUS_URL}?appointment_id=${encodeURIComponent(raw)}`,
  );
  if (!res.ok) return null;
  return res.json();
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
