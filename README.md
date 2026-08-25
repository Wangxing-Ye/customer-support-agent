# Client Services Agent (Professional Services)

A client-services AI Agent for **booking / appointment businesses**. **ServiceEmma** is the product name. This project focuses on **booking and appointment businesses**: online Q&A, a service catalog, reservations, pay-when rules, and tickets when chat cannot resolve the question.

## Background

Major U.S. industries that need online appointment / booking services, with estimated small and midsize business counts (nonemployer firms plus employers with fewer than 500 employees):


| Industry                                                          | Estimated SMEs       |
| ----------------------------------------------------------------- | -------------------- |
| Professional services (law, accounting, consulting, design, etc.) | 4.88 million         |
| Education and training                                            | 0.96 million         |
| Beauty and wellness (hair, nails, spa, massage, etc.)             | 1.3–1.5 million      |
| Fitness / sports venues (gyms, studios, personal training, etc.)  | 0.4–0.5 million      |
| Traditional Chinese medicine / tuina / acupuncture                | 30,000–40,000        |
| Veterinary clinics                                                | 30,000–35,000        |
| Motels / vacation rentals / RV parks                              | 40,000–50,000        |
| **Total**                                                         | **~7.7–8.3 million** |


This repo is a **lightweight, professional, shippable Client Services Agent**. It is not a generic auto-reply bot. The assistant grounds answers in a firm knowledge base (local Markdown by default; RAGFlow when configured), books or cancels appointments, and escalates to a human via a support ticket. 

It is built so the owner can:

- **Spend less time on repeat intake** — grounded in the knowledge base (RAG), the agent answers questions about the company info, services, contact details, policies, and other frequent FAQs.
- **Turn free chat into paid work** — a customer-acquisition window that shows services and prices, then guides clients to book and pay in the conversation.
- **Not lose the question** — if the user has other needs or wants a person, open a ticket so feedback is tracked and follow-up stays on track.

The shipped example is **single-tenant Palo Alto Advisory CPA.** 

<p align="center">
  <img src="docs/Screenshot%201.jpg" alt="Screenshot 1" width="32%" />
  <img src="docs/Screenshot%202.jpg" alt="Screenshot 2" width="32%" />
  <img src="docs/Screenshot%203.jpg" alt="Screenshot 3" width="32%" />
</p>

## Features

- Service catalog with pricing, photos, and bookable vs ticket-only services
- On-the-hour availability (Mon–Fri, America/Los_Angeles; no noon / no half-hour starts)
- Booking with confirmation email: cancellation code, Zoom or in-person location, Google Calendar add-event URL
- Pay-when: free initial consult confirms immediately; paid 30- and 60-minute consultations hold the slot until **Stripe Checkout**; Annual Tax Reporting confirms immediately and invoices after the visit (`pay_after`)
- Complimentary Free Initial Consultation (15 min Zoom; no per-email cap)
- Cancel with **email + cancellation code** (hashed at rest; 24-hour self-service window)
- Support tickets when the AI cannot resolve or the user wants a human: name, email, phone, preferred call window, question, server-computed **respond_by** SLA
- Outbound email (`console` / `smtp` / `resend`) with a shared plaintext footer
- Streaming chat widget (SSE): quick actions, markdown + service images + lightbox, typing dots, multiline input, Whisper STT + TTS (`TTS_PROVIDER`) voice path
- Owner dashboard (`/admin.html`): bootstrap admin login, first-time email bind + password change, appointments and tickets



## Design: catalog, booking, pay-when

Appointment businesses share three layers. This demo keeps **one** `Service` / `Appointment` shape. Palo Alto Advisory CPA free consults confirm immediately on Zoom; paid consultations use Stripe Checkout to hold the slot.

### Catalog


|                                                        | Phase 1                                                                             |
| ------------------------------------------------------ | ----------------------------------------------------------------------------------- |
| Service name, duration, bookable vs ticket-only, photo | **Covered** (`services` + seed catalog)                                             |
| Price as display copy (e.g. USD 175 / 30 min)          | **Covered** (catalog text plus `price_cents` / currency)                            |
| `price_cents` + currency for checkout                  | **Covered** (catalog amount; paid consults charge the Stripe product default price) |
| `pay_when`                                             | `none` / `checkout_to_hold` / `pay_after`                                               |
| `fulfillment`                                          | `online` / `in_person`                                                                  |


### Booking


|                                                                                         |                                                              |
| --------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| Name + email, hourly open slots, confirm email, cancel code                             | **Covered**                                                  |
| Status `booked` immediately when `pay_when` is `none`, `pay_on_arrival`, or `pay_after` | **Covered**                                                  |
| Online meeting link + Google Calendar URL                                               | **Covered**                                                  |
| In-person location on the confirmation                                                  | **Covered** (when `fulfillment=in_person`)                   |
| `pending_payment` / expire unpaid holds                                                 | **Covered** (15-minute hold; overdue → `expired`, slot free) |


### Pay-when


|                                                      |                                                                                                                                      |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| Free intro (skip payment)                            | **Covered** (complimentary 15-min consult; no per-email cap)                                                                         |
| Pay on arrival (book now, pay at the shop)           | **Covered** (`pay_when=pay_on_arrival`; not used on Palo Alto Advisory CPA seed)                                                     |
| Pay after the visit (invoice)                        | **Covered** (`pay_when=pay_after`; Annual Tax Reporting on Palo Alto Advisory CPA seed)                                              |
| Checkout to hold the slot (then `booked`)            | **Covered** — Stripe Checkout for `consult-30` / `consult-60` (`STRIPE_PRODUCT_CONSULT_30` / `_60`); webhook `POST /webhooks/stripe` |
| Agent must not say “confirmed” until `status=booked` | **Covered** (prompt + tool `status=pending_payment` vs `booked`)                                                                     |


Cancel codes exist only after **booked**. Unpaid `pending_payment` rows expire; they cannot be cancelled with a code.

## Architecture

```text
Vite React widget → FastAPI → LangGraph agent
                       ├─ Chat LLM: OpenAI or Anthropic Claude (`LLM_PROVIDER`)
                       ├─ Voice: Whisper STT (OpenAI) + TTS (`TTS_PROVIDER`: OpenAI or ElevenLabs)
                       ├─ Knowledge retrieval (local Markdown or RAGFlow)
                       ├─ Postgres (services, availability, appointments, tickets, email_log)
                       ├─ LangGraph PostgresSaver (falls back to MemorySaver / SQLite)
                       ├─ Email provider (console | smtp | resend)
                       └─ Payment (Stripe Checkout for consultations)
```



## Demo services


| Service                       | Slug                    | Price                                      | Booking                                                          |
| ----------------------------- | ----------------------- | ------------------------------------------ | ---------------------------------------------------------------- |
| Free Initial Consultation     | `free-consult`          | Free, 15 min                               | Zoom, confirm immediately (`pay_when=none`)                      |
| 30-Minute Client Consultation | `consult-30`            | USD 175 (30 minutes)                       | Zoom, hold until Stripe Checkout (`checkout_to_hold`)            |
| 60-Minute Client Consultation | `consult-60`            | USD 350 (60 minutes)                       | In person, hold until Stripe Checkout (`checkout_to_hold`)       |
| Annual Tax Reporting          | `annual-tax-reporting`  | USD 250/hour (2-hour min, USD 500)         | In person, confirm immediately; invoice after (`pay_when=pay_after`) |


Slots offered: **9, 10, 11 AM and 1–5 PM** PT on the hour for 15 / 30 / 60-minute services. Annual Tax Reporting is **120 minutes** of working time (must finish by 5:00 PM PT; lunch skipped), so later starts may be unavailable. Photos live under `frontend/public/assets/` (`Free-Initial-Consultation.jpg`, `30-Minute-Client-Consultation.jpg`, `60-Minute-Client-Consultation.jpg`, `Annual-Tax-Reporting.jpg`).

## Booking, cancel, tickets

- **Book:** choose a bookable service → pick an open hourly slot → provide name and email. Confirmation email includes appointment ID, cancel code, Zoom or in-person `location_text`, and a Google Calendar template URL. The agent reply also includes that location.
- **Check:** booking email returns summaries (`appointment_id`, service, time, status). Full detail (Zoom or location) needs that email **and** the cancel code; unpaid holds use email + `appointment_id`.
- **Cancel:** email used at booking **and** the cancel code. Self-service cancel is blocked within `CANCEL_WINDOW_HOURS` (default 24); the agent then opens a high-priority ticket.
- **Ticket:** required name, email, phone (≥10 digits), preferred call window, and a question (≥10 characters). SLA is computed server-side (normal: next business-day end; high: 4 business hours, Mon–Fri 9–17 PT). Do not invent reply times — use `respond_by_display` from the tool.



## Outbound email

Templates: appointment confirmation, appointment cancelled, ticket created. Every send appends:

```
—
Palo Alto Advisory CPA
Our service agent is available 24/7
http://paloaltoadvisorycpa.com/
```

Firm name and site come from `FIRM_NAME` and `FIRM_WEBSITE`. The assistant's display name is `AGENT_NAME` (default Emma).

## Chat widget

Open [http://localhost:3003](http://localhost:3003) after starting frontend + backend.

Header title, subtitle, greeting, and quick-action chips come from `BRAND` in [frontend/src/config.js](frontend/src/config.js). Change that object for another appointment business; keep the same agent. Default chips: **Our Services**, **Book appointment**, **Check appointment**, **Cancel appointment**, **Support Ticket**. Text chat uses `POST /chat/stream` (SSE). Voice uses `POST /chat` then TTS. Service images in replies can be clicked to enlarge.

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

Open [http://localhost:3003](http://localhost:3003) for the chat widget, or [http://localhost:3003/admin.html](http://localhost:3003/admin.html) for the **Owner dashboard** (default `admin` / `OWNER_DEFAULT_PASSWORD`, then bind email and change password on first login).

### Knowledge base

**local Markdown** = simple, local, full-file injection; **RAGFlow** = optional retrieval service that returns relevant passages per question.

`KB_PROVIDER=auto` (default):

- If `RAGFLOW_API_KEY` and `KNOWLEDGE_BASE_ID` are set, retrieve from self-hosted RAGFlow (brand-prefix retry). Empty or error responses fall back to the local file.
- Otherwise inject [docs/kb/palo-alto-advisory-cpa.md](docs/kb/palo-alto-advisory-cpa.md) in full — enough for a small firm FAQ (under ~20 pages).

Set `KB_PROVIDER=local` to skip RAGFlow, or `KB_PROVIDER=ragflow` to require it. Override the file with `KB_LOCAL_PATH`.

Optional RAGFlow: upload that sample Markdown (or your own KB), then set `RAGFLOW_URL`, `RAGFLOW_API_KEY`, and `KNOWLEDGE_BASE_ID`. Re-upload if you previously ingested an older catalog.

## API


| Endpoint                | Purpose                                                                   |
| ----------------------- | ------------------------------------------------------------------------- |
| `POST /auth/token`      | Anonymous session JWT (`sid`, 30 min TTL by default); rate-limited per IP |
| `POST /auth/refresh`    | Same `sid`, new JWT (Bearer required; rate-limited per sid / IP)          |
| `POST /chat`            | Sync chat (used by voice path); thread = `chat:{sid}`                     |
| `POST /chat/stream`     | SSE token stream (text UI); thread = `chat:{sid}`                         |
| `POST /transcribe`      | Whisper STT (OpenAI)                                                      |
| `POST /tts`             | Speech synthesis (`TTS_PROVIDER`: OpenAI or ElevenLabs)                   |
| `POST /webhooks/stripe` | Stripe Checkout events (no JWT; verify `STRIPE_WEBHOOK_SECRET`)           |
| `GET /pay/status`       | Appointment `status` for the chat widget (no JWT / no cancel code)        |
| `GET /pay/success`      | Post-checkout landing page (notifies the chat tab)                        |
| `GET /pay/cancel`       | Checkout cancelled landing page                                           |
| `POST /admin/login`     | Owner login (username/password → Owner JWT; rate-limited)                 |
| `POST /admin/setup/*`   | First-time bind email + set password (Owner JWT, setup pending)           |
| `POST /admin/forgot-password` / `reset-password` | Email reset for verified owner email                    |
| `GET /admin/appointments` · `POST .../cancel` | List / staff-cancel appointments (setup complete)              |
| `GET /admin/tickets` · `PATCH ...` | List / update ticket status                                     |


Chat body: `{ "message": "..." }` (`thread_id` is ignored if sent). Appointment cancel still requires **email + cancel code**, not the site JWT. Owners cancel via `/admin/appointments/{id}/cancel` without the customer code.

### Owner dashboard

Single-tenant staff console at `/admin.html` (dev: port 3003).

1. Bootstrap user from `OWNER_USERNAME` / `OWNER_DEFAULT_PASSWORD` (seeded on API startup if no owner row exists).
2. First login returns `setup_required: true` → bind admin email (verification code via `EMAIL_PROVIDER`) → set a new password (min 10 chars). Default password stops working afterward.
3. Forgot password sends a link/token to the verified email (`ADMIN_UI_ORIGIN/admin.html?reset=...`).
4. Dashboard tabs: **Appointments** (filter + cancel booked) and **Tickets** (filter + close / in progress).

Owner JWT uses the same `JWT_SECRET` with audience `OWNER_JWT_AUDIENCE` (`owner-dashboard`). It is separate from the anonymous widget JWT.

### Anonymous session and access control


| Item              | Behavior                                                                                                  |
| ----------------- | --------------------------------------------------------------------------------------------------------- |
| Identity          | Anonymous JWT (`sub=anonymous-chat`). Not a login account; unrelated to appointment cancel codes.         |
| Issue             | `POST /auth/token` → new `sid` + Bearer token                                                             |
| Refresh           | `POST /auth/refresh` (valid Bearer required) → **same** `sid`, new `exp` only                             |
| TTL               | `SESSION_JWT_EXPIRE_MINUTES` (default 30). Frontend silently refreshes within `JWT_REFRESH_SKEW_SECONDS`. |
| Thread binding    | LangGraph `thread_id = chat:{sid}` is **server-derived**; any client `thread_id` is ignored               |
| JWT required      | `/chat`, `/chat/stream`, `/transcribe`, `/tts`, `/auth/refresh`                                           |
| No JWT            | Stripe webhook, `/pay/*` landing and status endpoints                                                     |
| Secrets / storage | `JWT_SECRET` + `JWT_AUDIENCE`; widget stores the token in `sessionStorage`                                |




### Session rate limits

In-process sliding windows (phase 1, **per API worker**). Over-limit → **429** with `Retry-After`. Multi-instance deployments should move counters to Redis later.


| Variable                             | Default | Effect                                                           |
| ------------------------------------ | ------- | ---------------------------------------------------------------- |
| `SESSION_PER_IP_PER_HOUR`            | 60      | Max `POST /auth/token` (new sid) per client IP per rolling hour  |
| `SESSION_REFRESH_PER_SID_PER_MINUTE` | 10      | Max refresh per `sid` per minute; soft per-IP cap ≈ 3× that rate |
| `TRUST_PROXY_HEADERS`                | `false` | Trust `X-Forwarded-For` only behind a known reverse proxy        |


Refresh does **not** mint a new session and does **not** reset the chat-turn quota below.

### Model / cost limits

There is no direct OpenAI/Anthropic RPM integration. Volume is capped by **chat turns per sid** plus **input size** limits.


| Variable                                  | Default     | Effect                                                                                                                                        |
| ----------------------------------------- | ----------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `SESSION_CHAT_TURNS_PER_SID`              | 100         | Lifetime max user turns on `POST /chat` and `POST /chat/stream` per `sid` (not internal LLM `invoke`s). Refresh does not reset. `0` disables. |
| `USER_INPUT_MAX_MESSAGE_WORDS`            | 150         | Max words per chat message                                                                                                                    |
| `TTS_MAX_CHARS`                           | 2000        | Max characters per `/tts` request                                                                                                             |
| `WHISPER_MIN_BYTES` / `WHISPER_MAX_BYTES` | 256 / 3 MiB | Audio size bounds for `/transcribe` (oversize → 413)                                                                                          |


Rough upper bound with defaults: about **60 new sid/IP/hour × 100 turns ≈ 6000 chat requests/IP/hour** (same process / same in-memory counters).

Not in this release: daily per-IP quotas, CAPTCHA, Origin checks, Redis-shared counters, vendor LLM quota APIs.

## Tools

- `ragflow_retrieve` (local Markdown or RAGFlow), `get_services`, `list_availability`
- `book_appointment` → `booked` + confirmation email, or `pending_payment` + Stripe `checkout_url`
- `lookup_appointments(email [, appointment_id] [, cancel_code])` → summaries by email; detail with cancel code (or email + id for `pending_payment`)
- `simulate_payment` → checks Stripe (or local hold) then confirms and emails the cancel code
- `cancel_appointment(email, cancel_code)` → only for `booked` appointments
- `create_ticket` → requires name, email, phone, call window, question; returns `ticket_id` + `respond_by_display`



## LangGraph

**LangGraph** orchestrates the chat agent as a stateful graph (not a single one-shot LLM call): the model can reason, call tools, see tool results, and loop until it finishes. Conversation state is checkpointed by `thread_id` (`chat:{sid}`) via PostgresSaver when `CHECKPOINT_DATABASE_URL` is set, otherwise MemorySaver.

In this repo (`backend/agent/graph.py`): user message → agent node (LLM + system prompt + RAG context) → optional tools node (booking, lookup, tickets, …) → back to agent → end. The LLM writes replies; the tools perform real side effects (DB, email, Stripe).



## Environment

See [env_copy](env_copy). Important keys: `OPENAI_API_KEY`, `OPENAI_MODEL`, `LLM_PROVIDER` (`openai` / `anthropic` / `auto`), `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `JWT_SECRET`, `SESSION_JWT_EXPIRE_MINUTES` (default 30), `JWT_AUDIENCE`, `JWT_REFRESH_SKEW_SECONDS` (frontend renew window, default 300), `OWNER_USERNAME`, `OWNER_DEFAULT_PASSWORD`, `OWNER_JWT_AUDIENCE`, `OWNER_JWT_EXPIRE_MINUTES`, `ADMIN_UI_ORIGIN`, `SESSION_PER_IP_PER_HOUR` (default 60), `SESSION_REFRESH_PER_SID_PER_MINUTE`, `SESSION_CHAT_TURNS_PER_SID` (default 100), `TRUST_PROXY_HEADERS`, `DATABASE_URL`, `KB_PROVIDER`, RAGFlow vars, `EMAIL_PROVIDER`, `EMAIL_FROM`, `FIRM_NAME`, `AGENT_NAME`, `FIRM_TIMEZONE`, `FIRM_WEBSITE`, `MEETING_LINK`, `FIRM_LOCATION`, `PUBLIC_BASE_URL`, `PAYMENT_HOLD_MINUTES`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRODUCT_CONSULT_30`, `STRIPE_PRODUCT_CONSULT_60` (optional legacy `STRIPE_PRODUCT_STRATEGY_SESSION` fallback). Whisper STT stays on OpenAI (`WHISPER_MIN_BYTES` / `WHISPER_MAX_BYTES`, default 256 / 3 MiB). TTS uses `TTS_PROVIDER` (`openai` / `elevenlabs`) with `OPENAI_TTS_*` or `ELEVENLABS_*`, and `TTS_MAX_CHARS` (default 2000) caps each `/tts` request.
Local Stripe webhook forwarding:

```bash
stripe listen --forward-to localhost:8000/webhooks/stripe
```

Use the CLI webhook secret in `STRIPE_WEBHOOK_SECRET`. Create Stripe products with default prices (USD 175 for `consult-30`, USD 350 for `consult-60`) and set `STRIPE_PRODUCT_CONSULT_30` / `STRIPE_PRODUCT_CONSULT_60`. If those are unset, the optional legacy `STRIPE_PRODUCT_STRATEGY_SESSION` is used as a fallback for both. Checkout Session hold is at least 31 minutes (Stripe minimum).

Do not commit `.env` (it is gitignored).

## Next Steps

None for now — maintain as time allows.

## License

MIT — see [LICENSE](LICENSE).
