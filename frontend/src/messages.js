import { renderBotMarkdown } from "./markdown.js";

function isLikelyImageUrl(url) {
  return /\.(?:png|jpe?g|gif|webp|svg)(?:\?[^\s<]*)?(?:#[^\s<]*)?$/i.test(url);
}

function appendUserMessageContent(el, text) {
  const raw = String(text);
  const urlRe = /(https?:\/\/[^\s<]+)/gi;
  let idx = 0;
  let m;
  while ((m = urlRe.exec(raw)) !== null) {
    if (m.index > idx) {
      el.appendChild(document.createTextNode(raw.slice(idx, m.index)));
    }
    const url = m[1];
    if (/^https?:\/\//i.test(url)) {
      if (isLikelyImageUrl(url)) {
        const img = document.createElement("img");
        img.src = url;
        img.alt = "Attached image";
        img.loading = "lazy";
        img.decoding = "async";
        img.className = "chat-img";
        el.appendChild(img);
      } else {
        const a = document.createElement("a");
        a.href = url;
        a.textContent = url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        el.appendChild(a);
      }
    }
    idx = m.index + m[0].length;
  }
  if (idx < raw.length) {
    el.appendChild(document.createTextNode(raw.slice(idx)));
  }
  if (!el.childNodes.length) {
    el.textContent = raw;
  }
}

export function addMessage(text, isBot) {
  const body = document.getElementById("chat-body");
  const div = document.createElement("div");
  div.className = `message ${isBot ? "bot" : "user"}`;
  if (isBot) {
    div.innerHTML = renderBotMarkdown(text);
    div.querySelectorAll("img").forEach((img) => {
      img.loading = "lazy";
      img.decoding = "async";
    });
    div.querySelectorAll("a[href]").forEach((a) => {
      a.setAttribute("target", "_blank");
      a.setAttribute("rel", "noopener noreferrer");
    });
  } else {
    appendUserMessageContent(div, text);
  }
  body.appendChild(div);
  body.scrollTop = body.scrollHeight;
}

export function showTypingIndicator() {
  const body = document.getElementById("chat-body");
  const div = document.createElement("div");
  div.className = "message bot typing-msg";
  div.setAttribute("role", "status");
  div.setAttribute("aria-live", "polite");
  div.setAttribute("aria-label", "Assistant is replying");
  div.innerHTML =
    '<span class="typing-dots"><span></span><span></span><span></span></span>';
  body.appendChild(div);
  body.scrollTop = body.scrollHeight;
  return div;
}

export function removeTypingIndicator(el) {
  if (el && el.parentNode) el.parentNode.removeChild(el);
}
