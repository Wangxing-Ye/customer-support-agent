import "./styles.css";
import { ensureToken } from "./auth.js";
import { sendText } from "./chat.js";
import { toggleVoice } from "./voice.js";
import { addMessage } from "./messages.js";

document.getElementById("input")?.addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendText();
});
document.getElementById("send-btn")?.addEventListener("click", () => sendText());
document.getElementById("voice-btn")?.addEventListener("click", () => toggleVoice());

async function bootstrap() {
  try {
    await ensureToken();
  } catch {
    addMessage(
      "Could not authenticate with the server. Ensure the API is running, CORS includes this page’s origin, and JWT_SECRET is set in .env.",
      true,
    );
    return;
  }
  addMessage(
    "Hi! I'm ABC Company's customer support assistant. Ask anything about products, placing orders, or creating tickets.",
    true,
  );
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => void bootstrap());
} else {
  void bootstrap();
}
