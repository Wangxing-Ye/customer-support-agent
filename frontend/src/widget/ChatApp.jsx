import React, { useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { MAX_WORDS, FIRM_NAME } from "../config.js";
import { wordCount } from "../utils.js";
import { streamChat, fetchChat, playAssistantAudio } from "../api.js";
import { renderBotMarkdown } from "../markdown.js";
import { ensureToken } from "../auth.js";
import { toggleVoice } from "../voice.js";

const QUICK = [
  { label: "Services Introduction", text: "What services does Summit Advisory Group offer?" },
  {
    label: "Book appointment",
    text: "I'd like to book an appointment. Please list the bookable services and let me choose one.",
  },
  { label: "Cancel appointment", text: "I need to cancel my appointment." },
  {
    label: "Support Ticket",
    text: "Please create a support ticket. I will provide my question or request, email, phone number, and a convenient time to call.",
  },
];

function MessageBubble({ role, text, streaming }) {
  const isBot = role === "bot";
  const waiting = isBot && streaming && !String(text || "").trim();
  return (
    <div
      className={`message ${isBot ? "bot" : "user"}${streaming ? " streaming" : ""}${waiting ? " typing-msg" : ""}`}
      role={waiting ? "status" : undefined}
      aria-label={waiting ? "Assistant is thinking" : undefined}
    >
      {waiting ? (
        <span className="typing-dots" aria-hidden="true">
          <span />
          <span />
          <span />
        </span>
      ) : isBot ? (
        <div
          dangerouslySetInnerHTML={{
            __html: renderBotMarkdown(text),
          }}
        />
      ) : (
        <span>{text}</span>
      )}
    </div>
  );
}

function ImageLightbox({ src, alt, onClose }) {
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="img-lightbox"
      role="dialog"
      aria-modal="true"
      aria-label={alt || "Enlarged image"}
      onClick={onClose}
    >
      <button type="button" className="img-lightbox-close" aria-label="Close">
        ×
      </button>
      <img
        src={src}
        alt={alt || ""}
        className="img-lightbox-photo"
        onClick={(e) => e.stopPropagation()}
      />
    </div>
  );
}

function ChatApp() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [authError, setAuthError] = useState(null);
  const [lightbox, setLightbox] = useState(null);
  const bodyRef = useRef(null);

  useEffect(() => {
    (async () => {
      try {
        await ensureToken();
        setMessages([
          {
            id: "welcome",
            role: "bot",
            text: `Hi! I'm the client services assistant for ${FIRM_NAME}. I can help with our services, booking or cancelling appointments, and creating a support ticket when needed.`,
          },
        ]);
      } catch {
        setAuthError(
          "Could not authenticate with the server. Ensure the API is running, CORS includes this page’s origin, and JWT_SECRET is set in .env.",
        );
      }
    })();
  }, []);

  useEffect(() => {
    if (bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [messages, busy]);

  // Allow voice.js to push messages into React state
  useEffect(() => {
    window.__pstChat = {
      addMessage(text, isBot) {
        setMessages((prev) => [
          ...prev,
          { id: crypto.randomUUID(), role: isBot ? "bot" : "user", text },
        ]);
      },
      setBusy,
      async sendVoiceTranscript(transcript) {
        setMessages((prev) => [
          ...prev,
          { id: crypto.randomUUID(), role: "user", text: transcript },
        ]);
        setBusy(true);
        try {
          // Voice path uses non-streaming chat then TTS (per product rules)
          const res = await fetchChat(transcript);
          if (!res.ok) throw new Error("bad");
          const data = await res.json();
          const reply = data.response != null ? String(data.response) : "";
          const finalReply = reply || "(No response)";
          setMessages((prev) => [
            ...prev,
            { id: crypto.randomUUID(), role: "bot", text: finalReply },
          ]);
          await playAssistantAudio(finalReply);
        } catch {
          setMessages((prev) => [
            ...prev,
            {
              id: crypto.randomUUID(),
              role: "bot",
              text: "Sorry, something went wrong. Please try again.",
            },
          ]);
        } finally {
          setBusy(false);
        }
      },
    };
    return () => {
      delete window.__pstChat;
    };
  }, []);

  const send = useCallback(
    async (raw) => {
      const msg = String(raw || "").trim();
      if (!msg || busy) return;
      if (wordCount(msg) > MAX_WORDS) {
        alert(`Please use at most ${MAX_WORDS} words.`);
        return;
      }
      setInput("");
      const userId = crypto.randomUUID();
      const botId = crypto.randomUUID();
      setMessages((prev) => [
        ...prev,
        { id: userId, role: "user", text: msg },
        { id: botId, role: "bot", text: "", streaming: true },
      ]);
      setBusy(true);
      try {
        await streamChat(msg, {
          onToken(_chunk, assembled) {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === botId ? { ...m, text: assembled, streaming: true } : m,
              ),
            );
          },
          onError(detail) {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === botId
                  ? {
                      ...m,
                      text: detail || "Sorry, something went wrong. Please try again.",
                      streaming: false,
                    }
                  : m,
              ),
            );
          },
          onDone(assembled) {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === botId
                  ? {
                      ...m,
                      text: assembled || m.text || "(No response)",
                      streaming: false,
                    }
                  : m,
              ),
            );
          },
        });
      } catch {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === botId && !m.text
              ? {
                  ...m,
                  text: "Sorry, something went wrong. Please try again.",
                  streaming: false,
                }
              : { ...m, streaming: false },
          ),
        );
      } finally {
        setBusy(false);
      }
    },
    [busy],
  );

  if (authError) {
    return (
      <div className="chat-body" ref={bodyRef}>
        <MessageBubble role="bot" text={authError} />
      </div>
    );
  }

  return (
    <>
      <div className="quick-actions">
        {QUICK.map((q) => (
          <button
            key={q.label}
            type="button"
            className="quick-btn"
            disabled={busy}
            onClick={() => send(q.text)}
          >
            {q.label}
          </button>
        ))}
      </div>
      <div
        id="chat-body"
        className="chat-body"
        ref={bodyRef}
        onClick={(e) => {
          const img = e.target.closest("img");
          if (!img || img.closest(".img-lightbox")) return;
          if (!bodyRef.current?.contains(img)) return;
          e.preventDefault();
          setLightbox({ src: img.currentSrc || img.src, alt: img.alt || "" });
        }}
      >
        {messages.map((m) => (
          <MessageBubble
            key={m.id}
            role={m.role}
            text={m.text}
            streaming={m.streaming}
          />
        ))}
        {busy && messages[messages.length - 1]?.streaming === false ? (
          <div className="message bot typing-msg" role="status">
            <span className="typing-dots">
              <span />
              <span />
              <span />
            </span>
          </div>
        ) : null}
      </div>
      <div className="input-area">
        <textarea
          id="input"
          rows={1}
          value={input}
          placeholder="Type or click mic…"
          autoComplete="off"
          disabled={busy}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              send(input);
            }
          }}
        />
        <div className="icon-btn-group">
        <button
          type="button"
          id="send-btn"
          className="icon-btn"
          aria-label="Send message"
          disabled={busy}
          onClick={() => send(input)}
        >
          <img className="icon-default" src="/assets/icon_send.png" alt="" width="22" height="22" />
          <img className="icon-focus" src="/assets/icon_send_focus.png" alt="" width="22" height="22" />
        </button>
        <button
          type="button"
          id="voice-btn"
          className="voice-btn icon-btn"
          aria-label="Voice input"
          aria-pressed="false"
          disabled={busy}
          onClick={() => toggleVoice()}
        >
          <img className="icon-default" src="/assets/icon_microphone.png" alt="" width="22" height="22" />
          <img className="icon-focus" src="/assets/icon_microphone_focus.png" alt="" width="22" height="22" />
        </button>
        </div>
      </div>
      {lightbox ? (
        <ImageLightbox
          src={lightbox.src}
          alt={lightbox.alt}
          onClose={() => setLightbox(null)}
        />
      ) : null}
    </>
  );
}

export function mountChatWidget(el) {
  const root = createRoot(el);
  root.render(<ChatApp />);
  return root;
}
