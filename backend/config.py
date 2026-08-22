"""Application configuration from environment."""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

USER_INPUT_MAX_MESSAGE_WORDS = int(os.getenv("USER_INPUT_MAX_MESSAGE_WORDS", "150"))

JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = "HS256"
# Anonymous widget session JWT TTL (default 30 minutes). Frontend silently refreshes.
SESSION_JWT_EXPIRE_MINUTES = int(os.getenv("SESSION_JWT_EXPIRE_MINUTES", "30"))
JWT_AUDIENCE = (os.getenv("JWT_AUDIENCE") or "customer-support-widget").strip() or (
    "customer-support-widget"
)
# Refresh when fewer than this many seconds remain on the token (frontend hint).
JWT_REFRESH_SKEW_SECONDS = int(os.getenv("JWT_REFRESH_SKEW_SECONDS", "300"))

# Owner dashboard (separate from anonymous widget JWT).
OWNER_USERNAME = (os.getenv("OWNER_USERNAME") or "admin").strip() or "admin"
OWNER_DEFAULT_PASSWORD = (os.getenv("OWNER_DEFAULT_PASSWORD") or "changeme").strip()
OWNER_JWT_AUDIENCE = (
    os.getenv("OWNER_JWT_AUDIENCE") or "owner-dashboard"
).strip() or "owner-dashboard"
OWNER_JWT_EXPIRE_MINUTES = int(os.getenv("OWNER_JWT_EXPIRE_MINUTES", "480"))
ADMIN_UI_ORIGIN = (
    os.getenv("ADMIN_UI_ORIGIN") or "http://localhost:3003"
).rstrip("/")

# Phase-1 in-process rate limit: anonymous session minting (POST /auth/token).
# Max new sessions per client IP per rolling hour (per API process).
SESSION_PER_IP_PER_HOUR = int(os.getenv("SESSION_PER_IP_PER_HOUR", "60"))
SESSION_REFRESH_PER_SID_PER_MINUTE = int(os.getenv("SESSION_REFRESH_PER_SID_PER_MINUTE", "10"))
# Max POST /chat (+ /chat/stream) per anonymous sid for the lifetime of that sid
# (refresh keeps the same sid and the same counter). 0 disables.
SESSION_CHAT_TURNS_PER_SID = int(os.getenv("SESSION_CHAT_TURNS_PER_SID", "100"))
# Only trust X-Forwarded-For when the app sits behind a known reverse proxy.
TRUST_PROXY_HEADERS = os.getenv("TRUST_PROXY_HEADERS", "false").lower() in (
    "1",
    "true",
    "yes",
)
_default_origins = (
    "http://127.0.0.1:3000,http://localhost:3000,"
    "http://127.0.0.1:3003,http://localhost:3003,"
    "http://127.0.0.1:4173,http://localhost:4173,"
    "http://127.0.0.1:5500,http://localhost:5500,"
    "http://127.0.0.1:8080,http://localhost:8080,"
    "http://127.0.0.1:8000,http://localhost:8000"
)
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", _default_origins).split(",")
    if o.strip()
]

# Set USE_SQLITE=true for local smoke tests without Docker Postgres.
_use_sqlite = os.getenv("USE_SQLITE", "false").lower() in ("1", "true", "yes")
if _use_sqlite:
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+pysqlite:///./pst_agent.db")
    CHECKPOINT_DATABASE_URL = os.getenv("CHECKPOINT_DATABASE_URL", "")
else:
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://pst:pst@127.0.0.1:5433/pst_agent",
    )
    # LangGraph checkpoint needs a plain postgres URL (no +psycopg).
    CHECKPOINT_DATABASE_URL = os.getenv(
        "CHECKPOINT_DATABASE_URL",
        DATABASE_URL.replace("postgresql+psycopg://", "postgresql://").replace(
            "postgresql+psycopg2://", "postgresql://"
        ),
    )

FIRM_NAME = (
    os.getenv("FIRM_NAME", "Palo Alto Advisory CPA").strip()
    or "Palo Alto Advisory CPA"
)
AGENT_NAME = (os.getenv("AGENT_NAME") or "Emma").strip() or "Emma"
FIRM_TIMEZONE = os.getenv("FIRM_TIMEZONE", "America/Los_Angeles").strip()
FIRM_WEBSITE = (
    os.getenv("FIRM_WEBSITE", "http://paloaltoadvisorycpa.com/").strip()
    or "http://paloaltoadvisorycpa.com/"
)
FIRM_LOCATION = os.getenv(
    "FIRM_LOCATION",
    "1451 Middlefield Rd, Palo Alto, CA 94301",
).strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
PAYMENT_HOLD_MINUTES = int(os.getenv("PAYMENT_HOLD_MINUTES", "15"))
BUSINESS_HOURS_START = int(os.getenv("BUSINESS_HOURS_START", "9"))
BUSINESS_HOURS_END = int(os.getenv("BUSINESS_HOURS_END", "17"))
CANCEL_WINDOW_HOURS = int(os.getenv("CANCEL_WINDOW_HOURS", "24"))
CANCEL_CODE_MAX_ATTEMPTS = int(os.getenv("CANCEL_CODE_MAX_ATTEMPTS", "5"))
CANCEL_CODE_PEPPER = os.getenv("CANCEL_CODE_PEPPER", JWT_SECRET or "dev-pepper-change-me")

# local = inject Markdown; ragflow = self-hosted RAGFlow; auto = RAGFlow if configured else local
_raw_kb_provider = os.getenv("KB_PROVIDER", "auto").strip().lower()
KB_PROVIDER = _raw_kb_provider if _raw_kb_provider in ("auto", "local", "ragflow") else "auto"
KB_LOCAL_PATH = os.getenv(
    "KB_LOCAL_PATH", "docs/kb/palo-alto-advisory-cpa.md"
).strip() or "docs/kb/palo-alto-advisory-cpa.md"

RAGFLOW_URL = os.getenv("RAGFLOW_URL", "http://127.0.0.1:9222").rstrip("/")
RAGFLOW_API_KEY = os.getenv("RAGFLOW_API_KEY")
KNOWLEDGE_BASE_ID = os.getenv("KNOWLEDGE_BASE_ID")
RAGFLOW_SIMILARITY_THRESHOLD = float(os.getenv("RAGFLOW_SIMILARITY_THRESHOLD", "0.2"))
RAGFLOW_KEYWORD = os.getenv("RAGFLOW_KEYWORD", "true").lower() in ("1", "true", "yes")
RAGFLOW_RETRIEVAL_LOWERCASE = os.getenv("RAGFLOW_RETRIEVAL_LOWERCASE", "true").lower() in (
    "1",
    "true",
    "yes",
)
RAG_BRAND_PREFIX = os.getenv("RAG_BRAND_PREFIX", FIRM_NAME).strip()
_raw_brand_skip = os.getenv("RAG_BRAND_RETRY_SKIP_SUBSTRINGS")
if _raw_brand_skip is None:
    _raw_brand_skip = ""
RAG_BRAND_RETRY_SKIP_SUBSTRINGS = [
    s.strip().lower() for s in _raw_brand_skip.split(",") if s.strip()
]

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
ANTHROPIC_API_KEY = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5").strip()
# openai | anthropic | auto (infer: claude-* → anthropic, else openai)
_raw_llm_provider = os.getenv("LLM_PROVIDER", "auto").strip().lower()
if _raw_llm_provider in ("openai", "anthropic", "auto"):
    LLM_PROVIDER = _raw_llm_provider
else:
    LLM_PROVIDER = "auto"
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-1")
# Upload size bounds for POST /transcribe (bytes).
WHISPER_MIN_BYTES = max(1, int(os.getenv("WHISPER_MIN_BYTES", "256")))
WHISPER_MAX_BYTES = max(
    WHISPER_MIN_BYTES,
    int(os.getenv("WHISPER_MAX_BYTES", "3145728")),  # 3 MiB default
)
# TTS: openai | elevenlabs (STT / Whisper stays on OpenAI)
_raw_tts_provider = os.getenv("TTS_PROVIDER", "openai").strip().lower()
TTS_PROVIDER = _raw_tts_provider if _raw_tts_provider in ("openai", "elevenlabs") else "openai"
# Max Unicode characters per /tts request (assistant speech).
TTS_MAX_CHARS = max(1, int(os.getenv("TTS_MAX_CHARS", "2000")))
# Legacy aliases still accepted; prefer OPENAI_TTS_* / ELEVENLABS_*
TTS_MODEL = os.getenv("TTS_MODEL", "tts-1")
TTS_VOICE = os.getenv("TTS_VOICE", "alloy")
OPENAI_TTS_MODEL = (os.getenv("OPENAI_TTS_MODEL") or TTS_MODEL or "tts-1").strip()
OPENAI_TTS_VOICE_ID = (os.getenv("OPENAI_TTS_VOICE_ID") or TTS_VOICE or "alloy").strip()
ELEVENLABS_API_KEY = (os.getenv("ELEVENLABS_API_KEY") or "").strip()
ELEVENLABS_TTS_VOICE_ID = (os.getenv("ELEVENLABS_TTS_VOICE_ID") or "").strip()
ELEVENLABS_TTS_MODEL = (
    os.getenv("ELEVENLABS_TTS_MODEL") or "eleven_multilingual_v2"
).strip()


def resolve_llm_provider() -> str:
    """Return 'openai' or 'anthropic' for the chat agent."""
    if LLM_PROVIDER == "openai":
        return "openai"
    if LLM_PROVIDER == "anthropic":
        return "anthropic"
    # auto: only treat as Claude if OPENAI_MODEL is a Claude id, or OpenAI key is absent
    if (OPENAI_MODEL or "").strip().lower().startswith("claude"):
        return "anthropic"
    if ANTHROPIC_API_KEY and not (os.getenv("OPENAI_API_KEY") or "").strip():
        return "anthropic"
    return "openai"

EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "console").lower()  # console | smtp | resend
EMAIL_FROM = os.getenv("EMAIL_FROM", f"noreply@{FIRM_NAME.lower().replace(' ', '')}.example")
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes")
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
MEETING_LINK = os.getenv(
    "MEETING_LINK",
    "https://us04web.zoom.us/j/7154373528?pwd=c1NLYW1kRXQxa1RPZGlWbVJDOEZzUT09",
).strip()

STRIPE_SECRET_KEY = (os.getenv("STRIPE_SECRET_KEY") or "").strip()
STRIPE_WEBHOOK_SECRET = (os.getenv("STRIPE_WEBHOOK_SECRET") or "").strip()
STRIPE_PRODUCT_CONSULT_30 = (os.getenv("STRIPE_PRODUCT_CONSULT_30") or "").strip()
STRIPE_PRODUCT_CONSULT_60 = (os.getenv("STRIPE_PRODUCT_CONSULT_60") or "").strip()
# Optional legacy fallback so existing env with STRATEGY_SESSION still works.
STRIPE_PRODUCT_STRATEGY_SESSION = (os.getenv("STRIPE_PRODUCT_STRATEGY_SESSION") or "").strip()

TICKET_DEDUP_HOURS = int(os.getenv("TICKET_DEDUP_HOURS", "24"))
