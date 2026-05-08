import { MAX_WORDS } from "./config.js";
import { wordCount } from "./utils.js";
import { fetchChat } from "./api.js";
import {
  addMessage,
  showTypingIndicator,
  removeTypingIndicator,
} from "./messages.js";

export async function sendText() {
  const input = document.getElementById("input");
  const msg = input.value.trim();
  if (!msg) return;
  if (wordCount(msg) > MAX_WORDS) {
    alert(`Please use at most ${MAX_WORDS} words.`);
    return;
  }
  addMessage(msg, false);
  input.value = "";

  const typing = showTypingIndicator();
  try {
    const res = await fetchChat(msg);
    if (res.status === 422) {
      addMessage(`Message must be at most ${MAX_WORDS} words.`, true);
      throw new Error("validation");
    }
    if (!res.ok) throw new Error("Bad response");
    const data = await res.json();
    const reply = data.response != null ? String(data.response) : "";
    const finalReply = reply || "(No response)";
    addMessage(finalReply, true);
  } catch (e) {
    if (e && e.message !== "validation") {
      addMessage("Sorry, something went wrong. Please try again.", true);
    }
  } finally {
    removeTypingIndicator(typing);
  }
}
