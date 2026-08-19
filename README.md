# Client Services Agent (Professional Services)

AI client-services assistant for **booking / appointment businesses**. The runnable demo is **Summit Advisory Group**. Users chat by text or microphone. Answers are grounded in a firm knowledge base (local Markdown, or optional self-hosted **RAGFlow**), orchestrated by **LangGraph**, and backed by **PostgreSQL** for inquiries, appointments, payment status, tickets, and outbound email.

## Background

**ServiceEmma** (*Your AI front desk for client services*) is the product name for this client-services agent. This project concentrates on **booking / appointment businesses**: a catalog of services, a reservation, a pay-when rule, and a ticket when chat cannot resolve the question. 

The shipped example is **single-tenant Summit Advisory Group** (consulting: intro call, strategy session, on-site document review). Swap firm env, `BRAND`, service catalog, and the local knowledge-base Markdown for another shop. The same agent also fits:

- Dental clinic — [Columbia Dental Care](https://www.columbia-dentalcare.com/)
- Spa / beauty — [Geranium Spa](https://geraniumspa.com/)
- Sports venue — [Synergy Badminton](https://www.synergybadminton.com/)
- Education / classes — [Green Forest Art Studio](https://greenforestartstudio.com/)

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


Multi-staff capacity, Stripe Connect, and a live second tenant are not included.

This repo is a **lightweight, professional, shippable Client Services Agent**. It is not a generic auto-reply bot. The assistant grounds answers in a firm knowledge base (local Markdown by default; RAGFlow when configured), books or cancels appointments, and escalates to a human via a support ticket. It does **not** give licensed legal, tax, or medical advice.

It is built so the owner can:

- **Spend less time on repeat intake** — policy and catalog answers come from RAG; the widget handles text and voice.
- **Turn free chat into paid work** — show services and prices, book a complimentary intro consult, book Strategy Sessions on the hour, and book on-site Document Review billed after the visit.
- **Not lose the question** — if the user wants a person or the agent cannot resolve it, `create_ticket` stores the name, question, email, phone, and call window, computes `respond_by`, and emails the client a receipt. (Staff inbox notify is not in this release.)

Phase 1 is **single-tenant**: one firm, Postgres, outbound email, embeddable chat. Multi-tenant white-label and inbox tools are out of scope.

## Features (phase 1)

- Service catalog with pricing, photos, and bookable vs ticket-only services
- On-the-hour availability (Mon–Fri, America/Los_Angeles; no noon / no half-hour starts)
- Booking with confirmation email: cancellation code, Zoom or in-person location, Google Calendar add-event URL
- Pay-when: free intro confirms immediately; Strategy Session holds the slot until **Stripe Checkout**; Document Review is billed after the visit
- Complimentary Introductory Consultation (no per-email cap)
- Cancel with **email + cancellation code** (hashed at rest; 24-hour self-service window)
- Support tickets when the AI cannot resolve or the user wants a human: name, email, phone, preferred call window, question, server-computed **respond_by** SLA
- Outbound email (`console` / `smtp` / `resend`) with a shared plaintext footer
- Streaming chat widget (SSE): quick actions, markdown + service images + lightbox, typing dots, multiline input, Whisper STT + TTS (`TTS_PROVIDER`) voice path



## Design: catalog, booking, pay-when

Appointment businesses share three layers. This demo keeps **one** `Service` / `Appointment` shape. Summit intro consults confirm immediately on Zoom; Strategy Sessions use Stripe Checkout to hold the slot. Capacity and extra verticals are still **not covered**.

### Catalog


|                                                        | Phase 1                                                                                 |
| ------------------------------------------------------ | --------------------------------------------------------------------------------------- |
| Service name, duration, bookable vs ticket-only, photo | **Covered** (`services` + seed catalog)                                                 |
| Price as display copy (e.g. USD 500 / hour)            | **Covered** (catalog text plus `price_cents` / currency)                                |
| `price_cents` + currency for checkout                  | **Covered** (catalog amount; Strategy Session charges the Stripe product default price) |
| `pay_when`: `none`                                     | `checkout_to_hold`                                                                      |
| `fulfillment`: `online`                                | `in_person` (address vs meeting link)                                                   |
| Capacity > 1 (court party, class seats)                | **Not covered** (implicit capacity = 1)                                                 |
| Location / staff / court as a bookable resource        | **Not covered**                                                                         |




### Booking


|                                                                                         | Phase 1                                                      |
| --------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| Name + email, hourly open slots, confirm email, cancel code                             | **Covered**                                                  |
| Status `booked` immediately when `pay_when` is `none`, `pay_on_arrival`, or `pay_after` | **Covered**                                                  |
| Online meeting link + Google Calendar URL                                               | **Covered**                                                  |
| In-person location on the confirmation                                                  | **Covered** (when `fulfillment=in_person`)                   |
| `pending_payment` / expire unpaid holds                                                 | **Covered** (15-minute hold; overdue → `expired`, slot free) |
| Configurable hours (evenings, 90-minute services)                                       | **Not covered** (fixed 9–11 AM and 1–5 PM PT)                |
| `party_size`                                                                            | **Not covered**                                              |




### Pay-when


|                                                      | Phase 1                                                                                                                 |
| ---------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Free intro (skip payment)                            | **Covered** (complimentary consult; no per-email cap)                                                                   |
| Pay on arrival (book now, pay at the shop)           | **Covered** (`pay_when=pay_on_arrival`; not used on Summit seed)                                                        |
| Pay after the visit (invoice)                        | **Covered** (`pay_when=pay_after`; Document Review, due in 3 business days)                                             |
| Checkout to hold the slot (then `booked`)            | **Covered** — Stripe Checkout for Strategy Session (`STRIPE_PRODUCT_STRATEGY_SESSION`); webhook `POST /webhooks/stripe` |
| Agent must not say “confirmed” until `status=booked` | **Covered** (prompt + tool `status=pending_payment` vs `booked`)                                                        |


Cancel codes exist only after **booked**. Unpaid `pending_payment` rows expire; they cannot be cancelled with a code.

**Still later:** Stripe Connect, capacity / `party_size`, multi-location staff/courts as resources. Vertical differences (no clinical advice, child age in notes) belong in KB + these fields, not a new agent per NAICS.

## Architecture

```text
Vite React widget → FastAPI → LangGraph agent
                       ├─ Chat LLM: OpenAI or Anthropic Claude (`LLM_PROVIDER`)
                       ├─ Voice: Whisper STT (OpenAI) + TTS (`TTS_PROVIDER`: OpenAI or ElevenLabs)
                       ├─ Knowledge retrieval (local Markdown or RAGFlow)
                       ├─ Postgres (services, availability, appointments, tickets, email_log)
                       ├─ LangGraph PostgresSaver (falls back to MemorySaver / SQLite)
                       └─ Email provider (console | smtp | resend) + Stripe Checkout (Strategy Session)
```



## Demo services


| Service                   | Slug               | Price                                       | Booking                                                                                           |
| ------------------------- | ------------------ | ------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Introductory Consultation | `intro-consult`    | Free, 30 min                                | Online, confirm immediately (`pay_when=none`)                                                     |
| Strategy Session          | `strategy-session` | USD 500 / hour (1 hour)                     | Online, hold until Stripe Checkout (`checkout_to_hold`)                                           |
| Document Review           | `document-review`  | USD 250 / hour, **4 working hours minimum** | On-site; lunch 12:00–1:00 PM excluded; finishes by 5 PM; pay within 3 business days (`pay_after`) |


Slots offered: **9, 10, 11 AM and 1–5 PM** PT for 30- and 60-minute services. Document Review is **4 working hours** (lunch 12:00–1:00 PM not counted) and must finish by 5:00 PM, so starts are **9 AM (ends 2 PM), 10 AM (ends 3 PM), 11 AM (ends 4 PM), and 1:00 PM (ends 5 PM)**. Photos live under `frontend/public/assets/` (`intro-consult.jpg`, `strategy-session.jpg`, `document-review.jpg`).

## Booking, cancel, tickets

- **Book:** choose a bookable service → pick an open hourly slot → provide name and email. Confirmation email includes appointment ID, cancel code, Zoom or in-person `location_text`, and a Google Calendar template URL. The agent reply also includes that location.
- **Check:** booking email returns summaries (`appointment_id`, service, time, status). Full detail (Zoom or location) needs that email **and** the cancel code; unpaid holds use email + `appointment_id`.
- **Cancel:** email used at booking **and** the cancel code. Self-service cancel is blocked within `CANCEL_WINDOW_HOURS` (default 24); the agent then opens a high-priority ticket.
- **Ticket:** required name, email, phone (≥10 digits), preferred call window, and a question (≥10 characters). SLA is computed server-side (normal: next business-day end; high: 4 business hours, Mon–Fri 9–17 PT). Do not invent reply times — use `respond_by_display` from the tool.



## Outbound email

Templates: appointment confirmation, appointment cancelled, ticket created. Every send appends:

```
—
Summit Advisory Group
Our service agent is available 24/7
https://www.SummitAdvisoryGroup.com
```

Firm name and site come from `FIRM_NAME` and `FIRM_WEBSITE`. The assistant's display name is `AGENT_NAME` (default Emma).

## Chat widget

Open [http://localhost:3003](http://localhost:3003) after starting frontend + backend.

Header title, subtitle, greeting, and quick-action chips come from `BRAND` in [frontend/src/config.js](frontend/src/config.js). Change that object for another appointment business; keep the same agent. Default chips: **Services Introduction**, **Book appointment**, **Check appointment**, **Cancel appointment**, **Support Ticket**. Text chat uses `POST /chat/stream` (SSE). Voice uses `POST /chat` then TTS. Service images in replies can be clicked to enlarge.

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

Open [http://localhost:3003](http://localhost:3003)

### Knowledge base

`KB_PROVIDER=auto` (default):

- If `RAGFLOW_API_KEY` and `KNOWLEDGE_BASE_ID` are set, retrieve from self-hosted RAGFlow (brand-prefix retry). Empty or error responses fall back to the local file.
- Otherwise inject [docs/kb/summit-advisory-group.md](docs/kb/summit-advisory-group.md) in full — enough for a small firm FAQ (under ~20 pages).

Set `KB_PROVIDER=local` to skip RAGFlow, or `KB_PROVIDER=ragflow` to require it. Override the file with `KB_LOCAL_PATH`.

Optional RAGFlow: upload that sample Markdown (or your own KB), then set `RAGFLOW_URL`, `RAGFLOW_API_KEY`, and `KNOWLEDGE_BASE_ID`. Re-upload if you previously ingested an older catalog.

## API


| Endpoint                | Purpose                                                            |
| ----------------------- | ------------------------------------------------------------------ |
| `POST /auth/token`      | JWT for UI                                                         |
| `POST /chat`            | Sync chat (used by voice path)                                     |
| `POST /chat/stream`     | SSE token stream (text UI)                                         |
| `POST /transcribe`      | Whisper STT (OpenAI)                                               |
| `POST /tts`             | Speech synthesis (`TTS_PROVIDER`: OpenAI or ElevenLabs)            |
| `POST /webhooks/stripe` | Stripe Checkout events (no JWT; verify `STRIPE_WEBHOOK_SECRET`)    |
| `GET /pay/status`       | Appointment `status` for the chat widget (no JWT / no cancel code) |
| `GET /pay/success`      | Post-checkout landing page (notifies the chat tab)                 |
| `GET /pay/cancel`       | Checkout cancelled landing page                                    |


Chat body: `{ "message": "...", "thread_id": "optional-uuid" }`. Site JWT authenticates the widget; appointment cancel still requires **email + cancel code**, not the site JWT.

## Tools (LangGraph)

- `ragflow_retrieve` (local Markdown or RAGFlow), `get_services`, `list_availability`
- `book_appointment` → `booked` + confirmation email, or `pending_payment` + Stripe `checkout_url`
- `lookup_appointments(email [, appointment_id] [, cancel_code])` → summaries by email; detail with cancel code (or email + id for `pending_payment`)
- `simulate_payment` → checks Stripe (or local hold) then confirms and emails the cancel code
- `cancel_appointment(email, cancel_code)` → only for `booked` appointments
- `create_ticket` → requires name, email, phone, call window, question; returns `ticket_id` + `respond_by_display`



## Environment

See [env_copy](env_copy). Important keys: `OPENAI_API_KEY`, `OPENAI_MODEL`, `LLM_PROVIDER` (`openai` / `anthropic` / `auto`), `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `JWT_SECRET`, `DATABASE_URL`, `KB_PROVIDER`, RAGFlow vars, `EMAIL_PROVIDER`, `EMAIL_FROM`, `FIRM_NAME`, `AGENT_NAME`, `FIRM_TIMEZONE`, `FIRM_WEBSITE`, `MEETING_LINK`, `FIRM_LOCATION`, `PUBLIC_BASE_URL`, `PAYMENT_HOLD_MINUTES`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRODUCT_STRATEGY_SESSION`. Whisper STT stays on OpenAI. TTS uses `TTS_PROVIDER` (`openai` / `elevenlabs`) with `OPENAI_TTS_*` or `ELEVENLABS_*`.

Local Stripe webhook forwarding:

```bash
stripe listen --forward-to localhost:8000/webhooks/stripe
```

Use the CLI webhook secret in `STRIPE_WEBHOOK_SECRET`. The product must have an active default price. Checkout Session hold is at least 31 minutes (Stripe minimum).

Do not commit `.env` (it is gitignored).

## Phase 2 (not in this release)

Stripe Connect, capacity and multi-location resources, multi-tenant white-label (ServiceEmma), Calendly/Google Calendar API sync, reschedule, inbound email, magic-link cancel page, Chatwoot.

## License

MIT — see [LICENSE](LICENSE).