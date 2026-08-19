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
export const PAY_STATUS_URL = `${API_BASE}/pay/status`;

export const TOKEN_KEY = "pst_chat_jwt";
export const THREAD_KEY = "pst_chat_thread";
export const MAX_WORDS = 150;

/**
 * Widget chrome for this tenant. Swap firmName, title, subtitle, greeting,
 * and quickActions for another appointment business; keep the same agent.
 */
export const BRAND = {
  firmName: "Summit Advisory Group",
  widgetTitle: "Client Services Agent",
  widgetSubtitle: "Appointments • booking & tickets",
  version: "V 0.50",
  avatarSrc: "/assets/avatar.png",
  avatarAlt: "Advisor",
  greeting: (name) =>
    `Hi, I'm Emma with ${name}. How can I help today — booking, a quick question, or something else?`,
  quickActions: [
    {
      label: "Services Introduction",
      text: (name) => `What services does ${name} offer?`,
    },
    {
      label: "Book appointment",
      text: () =>
        "I'd like to book an appointment. Please list the bookable services and let me choose one.",
    },
    {
      label: "Check appointment",
      text: () =>
        "I'd like to check my appointment. Please look it up after I give the email I used to book.",
    },
    {
      label: "Cancel appointment",
      text: () => "I need to cancel my appointment.",
    },
    {
      label: "Support Ticket",
      text: () =>
        "Please create a support ticket. I will provide my name, question or request, email, phone number, and a convenient time to call.",
    },
  ],
};

export const FIRM_NAME = BRAND.firmName;

export function brandActionText(action) {
  const { text } = action;
  return typeof text === "function" ? text(BRAND.firmName) : String(text || "");
}
