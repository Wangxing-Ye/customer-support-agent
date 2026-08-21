import React, { useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { getUserInputMaxMessageWords, BRAND, brandActionText, API_BASE } from "../config.js";
import { wordCount } from "../utils.js";
import { streamChat, fetchChat, playAssistantAudio, stopAssistantAudio, setAssistantSpeakingListener, fetchPayStatus } from "../api.js";
import { renderBotMarkdown } from "../markdown.js";
import { ensureToken } from "../auth.js";
import { toggleVoice } from "../voice.js";

function WidgetHeader() {
  return (
    <div className="header">
      <div className="avatar">
        <img src={BRAND.avatarSrc} alt={BRAND.avatarAlt} />
      </div>
      <div>
        <div className="header-title-row">
          <h2>{BRAND.widgetTitle}</h2>
          <span className="version-label">{BRAND.version}</span>
        </div>
        <p>{BRAND.widgetSubtitle}</p>
      </div>
    </div>
  );
}

function isStripeCheckoutUrl(href) {
  try {
    const u = new URL(href, window.location.href);
    const host = u.hostname.toLowerCase();
    return host === "checkout.stripe.com";
  } catch {
    return /stripe\.com/i.test(String(href || ""));
  }
}

function isApiOrigin(origin) {
  try {
    const a = new URL(API_BASE);
    const o = new URL(origin);
    if (o.protocol !== a.protocol || o.port !== a.port) return false;
    return o.hostname === a.hostname || o.hostname === "127.0.0.1" || o.hostname === "localhost";
  } catch {
    return origin === API_BASE;
  }
}
function appointmentIdFromText(text) {
  const m = String(text || "").match(/APT-\d{8}-[A-Z0-9]+/i);
  return m ? m[0].toUpperCase() : "";
}

function needsCheckoutLinkFix(text) {
  const t = String(text || "");
  if (!appointmentIdFromText(t)) return false;
  if (/\]\(\s*(undefined|checkout_url|null)\s*\)/i.test(t)) return true;
  if (/\bthrough undefined\b/i.test(t)) return true;
  if (/https?:\/\/checkout\.stripe\.com/i.test(t)) return false;
  return /pay with stripe|checkout|hold the slot|payment is processed/i.test(t);
}

function withCheckoutLink(text, url) {
  if (!url) return text;
  let out = String(text || "");
  out = out.replace(/\]\(\s*(undefined|checkout_url|null)\s*\)/gi, `](${url})`);
  out = out.replace(/\bthrough undefined\b/gi, `through [Pay with Stripe](${url})`);
  if (!/https?:\/\/checkout\.stripe\.com/i.test(out)) {
    out = `${out.trim()}\n\n[Pay with Stripe](${url})`;
  }
  return out;
}

function isBrokenPayHref(href) {
  const h = String(href || "").trim();
  if (!h || /^(undefined|checkout_url|null)$/i.test(h)) return true;
  try {
    const u = new URL(h, window.location.href);
    return /\/undefined\/?$/i.test(u.pathname);
  } catch {
    return true;
  }
}

const PAID_NOTICE =
  "Payment received. Your appointment is confirmed, and a confirmation email with the cancellation code has been sent.";

function MessageBubble({ role, text, streaming, waiting: waitingProp }) {
  const isBot = role === "bot";
  const waiting =
    Boolean(waitingProp) ||
    (isBot && streaming && !String(text || "").trim());
  return (
    <div
      className={`message ${isBot ? "bot" : "user"}${streaming ? " streaming" : ""}${waiting ? " typing-msg" : ""}`}
      role={waiting ? "status" : undefined}
      aria-label={
        waiting
          ? isBot
            ? "Assistant is thinking"
            : "Transcribing your speech"
          : undefined
      }
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
  const [speaking, setSpeaking] = useState(false);
  const [authError, setAuthError] = useState(null);
  const [lightbox, setLightbox] = useState(null);
  const bodyRef = useRef(null);
  const watchRef = useRef({ aid: "", timer: null, announced: new Set() });

  useEffect(() => {
    setAssistantSpeakingListener(setSpeaking);
    return () => {
      setAssistantSpeakingListener(null);
      stopAssistantAudio();
    };
  }, []);

  useEffect(() => {
    (async () => {
      try {
        await ensureToken();
        setMessages([
          {
            id: "welcome",
            role: "bot",
            text: BRAND.greeting(BRAND.firmName),
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

  const announcePaid = useCallback((appointmentId) => {
    const aid = String(appointmentId || "").toUpperCase();
    if (!aid || watchRef.current.announced.has(aid)) return;
    watchRef.current.announced.add(aid);
    if (watchRef.current.timer) {
      clearInterval(watchRef.current.timer);
      watchRef.current.timer = null;
    }
    watchRef.current.aid = "";
    setMessages((prev) => {
      if (prev.some((m) => m.id === `pay-${aid}`)) return prev;
      return [
        ...prev,
        {
          id: `pay-${aid}`,
          role: "bot",
          text: `${PAID_NOTICE} Appointment ID: ${aid}.`,
        },
      ];
    });
  }, []);

  const startWatch = useCallback(
    (appointmentId) => {
      const aid = String(appointmentId || "").toUpperCase();
      if (!aid || watchRef.current.announced.has(aid)) return;
      if (watchRef.current.aid === aid && watchRef.current.timer) return;
      if (watchRef.current.timer) clearInterval(watchRef.current.timer);
      watchRef.current.aid = aid;
      let ticks = 0;
      const tick = async () => {
        ticks += 1;
        if (ticks > 450) {
          clearInterval(watchRef.current.timer);
          watchRef.current.timer = null;
          return;
        }
        const data = await fetchPayStatus(aid);
        if (data?.status === "booked") announcePaid(aid);
        if (data?.status === "expired" || data?.status === "cancelled") {
          clearInterval(watchRef.current.timer);
          watchRef.current.timer = null;
        }
      };
      tick();
      watchRef.current.timer = setInterval(tick, 2000);
    },
    [announcePaid],
  );

  useEffect(() => {
    const last = [...messages].reverse().find((m) => m.role === "bot" && !m.streaming);
    if (!last?.text) return;
    const aid = appointmentIdFromText(last.text);
    if (!aid) return;
    let cancelled = false;
    fetchPayStatus(aid).then((data) => {
      if (cancelled || !data) return;
      if (data.status === "pending_payment") {
        startWatch(aid);
        if (data.checkout_url && needsCheckoutLinkFix(last.text)) {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === last.id
                ? { ...m, text: withCheckoutLink(m.text, data.checkout_url) }
                : m,
            ),
          );
        }
      }
      if (data.status === "booked" && /stripe|hold the slot|pending|undefined|checkout/i.test(last.text)) {
        announcePaid(aid);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [messages, startWatch, announcePaid]);

  useEffect(() => {
    const onMsg = (event) => {
      if (!isApiOrigin(event.origin)) return;
      if (event.data?.type !== "pst-stripe-paid") return;
      const aid = String(event.data.appointment_id || "").toUpperCase();
      if (aid) {
        startWatch(aid);
        fetchPayStatus(aid).then((data) => {
          if (data?.status === "booked") announcePaid(aid);
        });
      }
    };
    const onVis = () => {
      if (document.visibilityState !== "visible") return;
      const aid = watchRef.current.aid;
      if (!aid) return;
      fetchPayStatus(aid).then((data) => {
        if (data?.status === "booked") announcePaid(aid);
      });
    };
    window.addEventListener("message", onMsg);
    document.addEventListener("visibilitychange", onVis);
    return () => {
      window.removeEventListener("message", onMsg);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [announcePaid, startWatch]);

  useEffect(() => {
    return () => {
      if (watchRef.current.timer) clearInterval(watchRef.current.timer);
    };
  }, []);

  // Allow voice.js to push messages into React state
  useEffect(() => {
    const VOICE_PENDING_ID = "voice-stt-pending";
    window.__pstChat = {
      addMessage(text, isBot) {
        setMessages((prev) => [
          ...prev.filter((m) => m.id !== VOICE_PENDING_ID),
          { id: crypto.randomUUID(), role: isBot ? "bot" : "user", text },
        ]);
      },
      beginVoicePending() {
        setMessages((prev) => {
          const without = prev.filter((m) => m.id !== VOICE_PENDING_ID);
          return [
            ...without,
            {
              id: VOICE_PENDING_ID,
              role: "user",
              text: "",
              waiting: true,
            },
          ];
        });
      },
      clearVoicePending() {
        setMessages((prev) => prev.filter((m) => m.id !== VOICE_PENDING_ID));
      },
      setBusy,
      async sendVoiceTranscript(transcript) {
        setMessages((prev) => {
          const without = prev.filter((m) => m.id !== VOICE_PENDING_ID);
          return [
            ...without,
            { id: crypto.randomUUID(), role: "user", text: transcript },
          ];
        });
        setBusy(true);
        try {
          // Voice path uses non-streaming chat then TTS (per product rules)
          const res = await fetchChat(transcript);
          if (!res.ok) throw new Error("bad");
          const data = await res.json();
          const replyRaw = data.response;
          const reply =
            typeof replyRaw === "string"
              ? replyRaw
              : Array.isArray(replyRaw)
                ? replyRaw
                    .map((p) =>
                      typeof p === "string"
                        ? p
                        : p && typeof p === "object"
                          ? String(p.text || "")
                          : "",
                    )
                    .join("")
                : replyRaw != null
                  ? String(replyRaw)
                  : "";
          const finalReply = reply.trim() || "(No response)";
          setMessages((prev) => [
            ...prev,
            { id: crypto.randomUUID(), role: "bot", text: finalReply },
          ]);
          setBusy(false);
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
      if (wordCount(msg) > getUserInputMaxMessageWords()) {
        alert(`Please use at most ${getUserInputMaxMessageWords()} words.`);
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
      <div className="chat-container">
        <WidgetHeader />
        <div className="widget-body">
          <div className="chat-body" ref={bodyRef}>
            <MessageBubble role="bot" text={authError} />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-container">
      <WidgetHeader />
      <div className="widget-body">
      <div className="quick-actions">
        {BRAND.quickActions.map((q) => (
          <button
            key={q.label}
            type="button"
            className="quick-btn"
            disabled={busy}
            onClick={() => send(brandActionText(q))}
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
          const a = e.target.closest("a");
          if (a && bodyRef.current?.contains(a)) {
            const broken = isBrokenPayHref(a.href) || a.getAttribute("href") === "undefined";
            if (isStripeCheckoutUrl(a.href) || broken) {
              e.preventDefault();
              const bubble = a.closest(".message")?.innerText || "";
              const aid =
                appointmentIdFromText(bubble) ||
                appointmentIdFromText(
                  [...messages].reverse().find((m) => m.role === "bot")?.text || "",
                );
              const openUrl = async () => {
                let href = a.href;
                if (!isStripeCheckoutUrl(href) && aid) {
                  const data = await fetchPayStatus(aid);
                  href = data?.checkout_url || "";
                }
                if (isStripeCheckoutUrl(href)) window.open(href, "_blank");
                if (aid) startWatch(aid);
              };
              openUrl();
              return;
            }
          }
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
            waiting={m.waiting}
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
          className={`voice-btn icon-btn${speaking ? " speaking" : ""}`}
          aria-label={speaking ? "Stop speaking" : "Voice input"}
          aria-pressed={speaking ? "true" : "false"}
          disabled={busy && !speaking}
          onClick={() => {
            if (speaking) {
              stopAssistantAudio();
              return;
            }
            toggleVoice();
          }}
        >
          <img className="icon-default" src="/assets/icon_microphone.png" alt="" width="22" height="22" />
          <img className="icon-focus" src="/assets/icon_microphone_focus.png" alt="" width="22" height="22" />
          <img className="icon-recording" src="/assets/icon_microphone_recording.png" alt="" width="22" height="22" />
          <span className="icon-stop" aria-hidden="true" />
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
      </div>
    </div>
  );
}

export function mountChatWidget(el) {
  document.title = BRAND.widgetTitle;
  const root = createRoot(el);
  root.render(<ChatApp />);
  return root;
}
