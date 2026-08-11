# Client Services Agent (Professional Services)

AI client-services assistant for a **US professional services** demo firm — **Summit Advisory Group**. Users chat by text or microphone. Answers are grounded in a firm knowledge base (local Markdown, or optional self-hosted **RAGFlow**), orchestrated by **LangGraph**, and backed by **PostgreSQL** for appointments, tickets, and email logs.

This is a **single-tenant** demo. It does **not** place product orders.

## Background

US **Professional, Scientific, and Technical Services** (NAICS 54) includes about **4.88 million** small businesses (SBA Office of Advocacy 2025 profile, Census 2022). About **82%** have no paid employees; the rest are mostly 1–19 person shops. Owners still answer the same questions about services, pricing, and availability, and they lose leads when a chat does not become a booked consult—or when an unresolved request never becomes a follow-up.

This repo is a **lightweight, professional, shippable Client Services Agent** for that kind of firm. It is not a generic auto-reply bot. The demo tenant is **Summit Advisory Group**. The assistant grounds answers in a firm knowledge base (local Markdown by default; RAGFlow when configured), books or cancels appointments, and escalates to a human via a support ticket. It does **not** place product orders and does **not** give licensed legal, tax, or medical advice.

It is built so the owner can:

- **Spend less time on repeat intake** — policy and catalog answers come from RAG; the widget handles text and voice.
- **Turn free chat into paid work** — show services and prices, offer one complimentary intro consult per email, book Strategy Sessions on the hour, and route Document Review through a ticket instead of an open-ended thread.
- **Not lose the question** — if the user wants a person or the agent cannot resolve it, `create_ticket` stores the question, email, phone, and call window, computes `respond_by`, and emails the client a receipt. (Staff inbox notify is not in this release.)

Phase 1 is **single-tenant**: one firm, Postgres, outbound email, embeddable chat. Multi-tenant white-label and inbox tools are out of scope.

## Features (phase 1)

- Service catalog with pricing, photos, and bookable vs ticket-only services
- On-the-hour availability (Mon–Fri, America/Los_Angeles; no noon / no half-hour starts)
- Booking with confirmation email: cancellation code, Zoom meeting link, Google Calendar add-event URL
- One complimentary Introductory Consultation per email
- Cancel with **email + cancellation code** (hashed at rest; 24-hour self-service window)
- Support tickets when the AI cannot resolve or the user wants a human: email, phone, preferred call window, question, server-computed **respond_by** SLA
- Outbound email (`console` / `smtp` / `resend`) with a shared plaintext footer
- Streaming chat widget (SSE): quick actions, markdown + service images + lightbox, typing dots, multiline input, Whisper / TTS voice path

## Architecture

```text
Vite React widget → FastAPI → LangGraph agent
                       ├─ Knowledge retrieval (local Markdown or RAGFlow)
                       ├─ Postgres (services, availability, appointments, tickets, email_log)
                       ├─ LangGraph PostgresSaver (falls back to MemorySaver / SQLite)
                       └─ Email provider (console | smtp | resend)
```

## Demo services

| Service | Slug | Price | Booking |
|---------|------|-------|---------|
| Introductory Consultation | `intro-consult` | Free, 30 min, **one per client email** | Online |
| Strategy Session | `strategy-session` | USD 500 / hour (1 hour) | Online |
| Document Review | `document-review` | USD 250 / hour, email feedback | Support ticket only |

Slots offered: **9, 10, 11 AM and 1–5 PM** PT. Photos live under `frontend/public/assets/` (`intro-consult.jpg`, `strategy-session.jpg`, `document-review.jpg`).

## Booking, cancel, tickets

- **Book:** choose a bookable service → pick an open hourly slot → provide email. Confirmation email includes appointment ID, cancel code, Zoom `MEETING_LINK`, and a Google Calendar template URL. The agent reply also includes the meeting link.
- **Cancel:** email used at booking **and** the cancel code. Self-service cancel is blocked within `CANCEL_WINDOW_HOURS` (default 24); the agent then opens a high-priority ticket.
- **Ticket:** required email, phone (≥10 digits), preferred call window, and a question (≥10 characters). SLA is computed server-side (normal: next business-day end; high: 4 business hours, Mon–Fri 9–17 PT). Do not invent reply times — use `respond_by_display` from the tool.

## Outbound email

Templates: appointment confirmation, appointment cancelled, ticket created. Every send appends:

```
—
Summit Advisory Group
Our service agent is available 24/7
https://www.SummitAdvisoryGroup.com
```

Firm name and site come from `FIRM_NAME` and `FIRM_WEBSITE`.

## Chat widget

Open http://localhost:3000 after starting frontend + backend.

Quick actions: **Services Introduction**, **Book appointment**, **Cancel appointment**, **Support Ticket**. Text chat uses `POST /chat/stream` (SSE). Voice uses `POST /chat` then TTS. Service images in replies can be clicked to enlarge.

## Quick start

### 1. Postgres

Start **Docker Desktop**, then:

```bash
docker compose up -d
```

Compose publishes Postgres on host port **5433** (avoids Homebrew/system Postgres on **5432**). `.env` should use:

```bash
DATABASE_URL=postgresql+psycopg://pst:pst@127.0.0.1:5433/pst_agent
CHECKPOINT_DATABASE_URL=postgresql://pst:pst@127.0.0.1:5433/pst_agent
USE_SQLITE=false
```

Smoke test without Docker:

```bash
# in .env
USE_SQLITE=true
```

(Checkpointer falls back to in-memory; prefer Postgres for real use.)

### 2. Python

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp env_copy .env   # then edit secrets
```

### 3. Backend

```bash
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
```

### 4. Frontend

```bash
cd frontend && npm install && npm run dev
```

Open http://localhost:3000

### Knowledge base

`KB_PROVIDER=auto` (default):

- If `RAGFLOW_API_KEY` and `KNOWLEDGE_BASE_ID` are set, retrieve from self-hosted RAGFlow (brand-prefix retry). Empty or error responses fall back to the local file.
- Otherwise inject [docs/sample_kb_professional_services.md](docs/sample_kb_professional_services.md) in full — enough for a small firm FAQ (under ~20 pages).

Set `KB_PROVIDER=local` to skip RAGFlow, or `KB_PROVIDER=ragflow` to require it. Override the file with `KB_LOCAL_PATH`.

Optional RAGFlow: upload that sample Markdown (or your own KB), then set `RAGFLOW_URL`, `RAGFLOW_API_KEY`, and `KNOWLEDGE_BASE_ID`. Re-upload if you previously ingested an older catalog.

## API

| Endpoint | Purpose |
|----------|---------|
| `POST /auth/token` | JWT for UI |
| `POST /chat` | Sync chat (used by voice path) |
| `POST /chat/stream` | SSE token stream (text UI) |
| `POST /transcribe` | Whisper |
| `POST /tts` | Speech MP3 |

Chat body: `{ "message": "...", "thread_id": "optional-uuid" }`. Site JWT authenticates the widget; appointment cancel still requires **email + cancel code**, not the site JWT.

## Tools (LangGraph)

- `ragflow_retrieve` (local Markdown or RAGFlow), `get_services`, `list_availability`
- `book_appointment` → confirmation email (cancel code + Zoom + Google Calendar)
- `cancel_appointment(email, cancel_code)` → server-side verification
- `create_ticket` → requires email, phone, call window, question; returns `ticket_id` + `respond_by_display`

## Environment

See [env_copy](env_copy). Important keys: `OPENAI_API_KEY`, `JWT_SECRET`, `DATABASE_URL`, `KB_PROVIDER`, RAGFlow vars, `EMAIL_PROVIDER`, `EMAIL_FROM`, `FIRM_NAME`, `FIRM_TIMEZONE`, `FIRM_WEBSITE`, `MEETING_LINK`.

Do not commit `.env` (it is gitignored).

## Phase 2 (not in this release)

Multi-tenant white-label, Calendly/Google Calendar API sync, reschedule, inbound email, magic-link cancel page, Chatwoot.

## License

MIT — see [LICENSE](LICENSE).
