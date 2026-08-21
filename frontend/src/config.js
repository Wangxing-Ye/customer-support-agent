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
export const CHAT_STREAM_URL = `${API_BASE}/chat/stream`;
export const TRANSCRIBE_URL = `${API_BASE}/transcribe`;
export const TTS_URL = `${API_BASE}/tts`;
export const TOKEN_URL = `${API_BASE}/auth/token`;
export const REFRESH_URL = `${API_BASE}/auth/refresh`;
export const PAY_STATUS_URL = `${API_BASE}/pay/status`;

export const TOKEN_KEY = "pst_chat_jwt";
/** Unix seconds when the current JWT expires (from /auth/token or /auth/refresh). */
export const TOKEN_EXPIRES_AT_KEY = "pst_chat_jwt_exp";
/** @deprecated Thread is derived server-side from JWT sid; kept only for cleanup. */
export const THREAD_KEY = "pst_chat_thread";
export const USER_INPUT_MAX_WORDS_KEY = "pst_user_input_max_words";
/** Fallback until /auth/token returns user_input_max_message_words from the API. */
export const DEFAULT_USER_INPUT_MAX_MESSAGE_WORDS = 150;

export function getUserInputMaxMessageWords() {
  const raw =
    typeof sessionStorage !== "undefined"
      ? sessionStorage.getItem(USER_INPUT_MAX_WORDS_KEY)
      : null;
  const n = parseInt(raw || "", 10);
  return Number.isFinite(n) && n > 0 ? n : DEFAULT_USER_INPUT_MAX_MESSAGE_WORDS;
}

/**
 * Widget chrome for this tenant. Swap firmName, title, subtitle, greeting,
 * and quickActions for another appointment business; keep the same agent.
 */
export const BRAND = {
  firmName: "Palo Alto Advisory CPA",
  /** Header title; defaults to firmName (FIRM_NAME for this tenant). */
  get widgetTitle() {
    return this.firmName;
  },
  widgetSubtitle: "Appointments • Booking & Tickets",
  version: "V 0.50",
  avatarSrc: "/assets/avatar.png",
  avatarAlt: "CPA",
  greeting: (name) =>
    `Hi, I'm Emma with ${name}. How can I help today — booking, a quick question, or something else?`,
  quickActions: [
    {
      label: "Our Services",
      text: (name) => `What services does ${name} offer?`,
    },
    {
      label: "Book Appointment",
      text: () =>
        "I'd like to book an appointment. Please list the bookable services and let me choose one.",
    },
    {
      label: "Check Appointment",
      text: () => "I'd like to check my appointment.",
    },
    {
      label: "Cancel Appointment",
      text: () => "I need to cancel my appointment.",
    },
    {
      label: "Support Ticket",
      text: () =>
        "Please create a support ticket. I have a specific question and would like someone to answer.",
    },
  ],
};

export const FIRM_NAME = BRAND.firmName;

export function brandActionText(action) {
  const { text } = action;
  return typeof text === "function" ? text(BRAND.firmName) : String(text || "");
}
