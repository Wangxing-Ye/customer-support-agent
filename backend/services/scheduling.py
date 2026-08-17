"""Scheduling: services, availability, book, cancel."""
from __future__ import annotations

import hashlib
import secrets
import string
from datetime import datetime, timedelta, time, timezone
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import (
    CANCEL_CODE_MAX_ATTEMPTS,
    CANCEL_CODE_PEPPER,
    CANCEL_WINDOW_HOURS,
    FIRM_LOCATION,
    FIRM_NAME,
    FIRM_TIMEZONE,
    MEETING_LINK,
    PAYMENT_HOLD_MINUTES,
    PUBLIC_BASE_URL,
)
from backend.models import Appointment, AvailabilityRule, Service
from backend.services.email import send_template_email
from backend.services.stripe_checkout import (
    create_checkout_session,
    product_id_for_slug,
    session_is_paid,
    stripe_enabled,
)

# Ambiguous-free alphabet for cancel codes
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def hash_cancel_code(code: str) -> str:
    normalized = (code or "").strip().upper().replace(" ", "").replace("-", "")
    raw = f"{CANCEL_CODE_PEPPER}:{normalized}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def generate_cancel_code() -> str:
    chars = [secrets.choice(_CODE_ALPHABET) for _ in range(8)]
    return f"{''.join(chars[:4])}-{''.join(chars[4:])}"


def generate_appointment_id(when: datetime) -> str:
    suffix = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
    return f"APT-{when.astimezone(timezone.utc).strftime('%Y%m%d')}-{suffix}"


def format_when(dt: datetime) -> str:
    local = dt.astimezone(ZoneInfo(FIRM_TIMEZONE))
    return local.strftime("%a, %b %d, %Y, %I:%M %p %Z").replace(" 0", " ")


def google_calendar_template_url(
    *,
    title: str,
    starts: datetime,
    ends: datetime,
    details: str = "",
    location: str = "",
) -> str:
    """Build a Google Calendar 'Add event' template URL (opens in the browser)."""
    start_utc = starts.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    end_utc = ends.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": f"{start_utc}/{end_utc}",
        "details": details,
        "ctz": FIRM_TIMEZONE,
    }
    if location:
        params["location"] = location
    return "https://calendar.google.com/calendar/render?" + urlencode(params)


# On-the-hour starts; skip noon. 5:00 PM is offered even if a 60-min session ends at 6:00 PM.
SLOT_START_HOURS = (9, 10, 11, 13, 14, 15, 16, 17)
LUNCH_START = time(12, 0)
LUNCH_END = time(13, 0)


def add_working_minutes(start: datetime, minutes: int, tz: ZoneInfo) -> datetime:
    """Advance start by working minutes, skipping lunch 12:00–1:00 local."""
    t = start.astimezone(tz)
    left = timedelta(minutes=max(0, int(minutes)))
    safety = 0
    while left > timedelta(0) and safety < 8:
        safety += 1
        day = t.date()
        lunch_s = datetime.combine(day, LUNCH_START, tzinfo=tz)
        lunch_e = datetime.combine(day, LUNCH_END, tzinfo=tz)
        if lunch_s <= t < lunch_e:
            t = lunch_e
            continue
        if t < lunch_s:
            chunk = min(left, lunch_s - t)
            t = t + chunk
            left -= chunk
            continue
        t = t + left
        left = timedelta(0)
    return t


def format_slot_clock(dt: datetime) -> str:
    local = dt.astimezone(ZoneInfo(FIRM_TIMEZONE))
    return local.strftime("%I:%M %p").lstrip("0")


SERVICE_IMAGES = {
    "intro-consult": "/assets/intro-consult.jpg",
    "strategy-session": "/assets/strategy-session.jpg",
    "document-review": "/assets/document-review.jpg",
}

SERVICE_CATALOG = {
    "intro-consult": {
        "name": "Introductory Consultation",
        "description": (
            "Complimentary 30-minute discovery call to discuss your needs."
        ),
        "duration_minutes": 30,
        "bookable": True,
        "price": "Free (30 minutes)",
        "price_cents": 0,
        "currency": "USD",
        "pay_when": "none",
        "fulfillment": "online",
        "location_text": MEETING_LINK,
    },
    "strategy-session": {
        "name": "Strategy Session",
        "description": (
            "One-hour working session with a senior advisor. "
            "Priced at USD 500 per hour; each Strategy Session is one hour. "
            "The slot is held until Stripe Checkout is completed."
        ),
        "duration_minutes": 60,
        "bookable": True,
        "price": "USD 500 per hour (1 hour per session)",
        "price_cents": 50000,
        "currency": "USD",
        "pay_when": "checkout_to_hold",
        "fulfillment": "online",
        "location_text": MEETING_LINK,
    },
    "document-review": {
        "name": "Document Review",
        "description": (
            "On-site guidance to organize, collect, interpret, and discuss documents "
            "across functions such as management, product, marketing, sales, finance, "
            "and HR. Bookable online. Minimum booking is 4 working hours "
            "(lunch 12:00–1:00 PM is not counted). "
            "Billed at USD 250 per hour for actual time (4-hour working minimum); "
            "payment is due within 3 business days after the visit."
        ),
        "duration_minutes": 240,
        "bookable": True,
        "price": "USD 250 per hour, 4 working hours minimum (lunch 12–1 excluded); due within 3 business days after the visit",
        "price_cents": 25000,
        "currency": "USD",
        "pay_when": "pay_after",
        "fulfillment": "in_person",
        "location_text": (
            "On-site at your office (management, product, marketing, sales, finance, HR as needed)"
        ),
    },
}


def service_pay_when(service: Service) -> str:
    raw = (getattr(service, "pay_when", None) or "none").strip().lower()
    if raw in ("none", "checkout_to_hold", "pay_on_arrival", "pay_after"):
        return raw
    return "none"


def service_fulfillment(service: Service) -> str:
    raw = (getattr(service, "fulfillment", None) or "online").strip().lower()
    return "in_person" if raw == "in_person" else "online"


def delivery_location(service: Service) -> str:
    stored = (getattr(service, "location_text", None) or "").strip()
    if service_fulfillment(service) == "in_person":
        return stored or FIRM_LOCATION
    return stored or MEETING_LINK


def checkout_url_for(appointment_id: str) -> str:
    return f"{PUBLIC_BASE_URL}/pay/simulate/{appointment_id}"


def expire_stale_holds(session: Session, skip_appointment_id: str | None = None) -> None:
    now = datetime.now(timezone.utc)
    rows = session.scalars(
        select(Appointment).where(Appointment.status == "pending_payment")
    ).all()
    for appt in rows:
        if skip_appointment_id and appt.appointment_id == skip_appointment_id:
            continue
        due = appt.payment_due_at
        if due is None:
            appt.status = "expired"
            continue
        if due.tzinfo is None:
            due = due.replace(tzinfo=ZoneInfo(FIRM_TIMEZONE)).astimezone(timezone.utc)
        if due <= now:
            appt.status = "expired"
    session.flush()


def service_image_url(service: Service) -> str:
    stored = (getattr(service, "image_url", None) or "").strip()
    if stored:
        return stored
    return SERVICE_IMAGES.get(service.slug, f"/assets/{service.slug}.jpg")


def list_services(session: Session) -> str:
    rows = session.scalars(
        select(Service).where(Service.active.is_(True)).order_by(Service.name)
    ).all()
    if not rows:
        return "No services are configured."
    blocks = [
        "Services (include each markdown image in your reply; do not drop the image lines):"
    ]
    for s in rows:
        bookable = "bookable online" if s.bookable else "not bookable online"
        img = service_image_url(s)
        spec = SERVICE_CATALOG.get(s.slug) or {}
        price = spec.get("price") or ""
        price_line = f"Price: {price}\n" if price else ""
        pay = service_pay_when(s)
        ful = service_fulfillment(s)
        loc = delivery_location(s)
        loc_line = f"Location: {loc}\n" if loc else ""
        blocks.append(
            f"### {s.name}\n"
            f"Slug: `{s.slug}` · {s.duration_minutes} min · {bookable}\n"
            f"{price_line}"
            f"Pay when: `{pay}` · Fulfillment: `{ful}`\n"
            f"{loc_line}"
            f"{s.description}\n"
            f"![{s.name}]({img})\n"
        )
    return "\n".join(blocks)


def _iter_day_slots(
    day: datetime,
    rule: AvailabilityRule,
    duration: timedelta,  # kept for call-site compatibility; slots are on the hour
    tz: ZoneInfo,
) -> list[datetime]:
    """Return on-the-hour slot starts for one local day (no noon).

    Services longer than 60 minutes must finish by the rule end time (5:00 PM),
    counting working time only (lunch 12:00–1:00 PM is skipped).
    30- and 60-minute sessions may still start at 5:00 PM.
    """
    local_day = day.astimezone(tz).date()
    slots: list[datetime] = []
    rule_end = datetime.combine(local_day, rule.end_time, tzinfo=tz)
    work_min = int(duration.total_seconds() // 60)
    for hour in SLOT_START_HOURS:
        slot = datetime.combine(local_day, time(hour, 0), tzinfo=tz)
        if slot.time() < rule.start_time:
            continue
        if duration > timedelta(minutes=60):
            slot_end = add_working_minutes(slot, work_min, tz)
            if slot_end > rule_end:
                continue
        slots.append(slot)
    return slots


def _open_slot_datetimes(
    session: Session,
    service: Service,
    start: datetime,
    end: datetime,
) -> list[datetime]:
    tz = ZoneInfo(FIRM_TIMEZONE)
    now = datetime.now(tz)
    rules = session.scalars(
        select(AvailabilityRule).where(AvailabilityRule.active.is_(True))
    ).all()
    if not rules:
        return []

    duration = timedelta(minutes=service.duration_minutes)
    expire_stale_holds(session)
    occupying = session.scalars(
        select(Appointment).where(
            Appointment.status.in_(("booked", "pending_payment")),
            Appointment.starts_at < end,
            Appointment.ends_at > start,
        )
    ).all()

    open_slots: list[datetime] = []
    day = start.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    end_day = end.astimezone(tz)
    while day <= end_day:
        weekday = day.weekday()
        for rule in rules:
            if rule.weekday != weekday:
                continue
            for slot in _iter_day_slots(day, rule, duration, tz):
                if slot < now:
                    continue
                if slot < start or slot >= end:
                    continue
                slot_end = add_working_minutes(slot, service.duration_minutes, tz)
                overlaps = False
                for other in occupying:
                    other_start = other.starts_at
                    other_end = other.ends_at
                    if other_start.tzinfo is None:
                        other_start = other_start.replace(tzinfo=tz)
                    if other_end.tzinfo is None:
                        other_end = other_end.replace(tzinfo=tz)
                    if other_start < slot_end and other_end > slot:
                        overlaps = True
                        break
                if overlaps:
                    continue
                open_slots.append(slot)
        day += timedelta(days=1)
    return open_slots


def list_availability(
    session: Session,
    service_slug: str,
    date_from: str | None = None,
    date_to: str | None = None,
) -> str:
    service = session.scalar(
        select(Service).where(Service.slug == service_slug, Service.active.is_(True))
    )
    if not service:
        return f"[error] Unknown service '{service_slug}'. Use get_services to list slugs."
    if not service.bookable:
        return f"[error] Service '{service_slug}' is not bookable online."

    tz = ZoneInfo(FIRM_TIMEZONE)
    now = datetime.now(tz)
    if date_from:
        start = datetime.fromisoformat(date_from)
        if start.tzinfo is None:
            start = start.replace(tzinfo=tz)
    else:
        start = now
    if date_to:
        end = datetime.fromisoformat(date_to)
        if end.tzinfo is None:
            end = end.replace(tzinfo=tz)
    else:
        end = start + timedelta(days=7)

    rules = session.scalars(
        select(AvailabilityRule).where(AvailabilityRule.active.is_(True))
    ).all()
    if not rules:
        return "[error] No availability rules configured."

    open_slots = _open_slot_datetimes(session, service, start, end)
    if not open_slots:
        return f"No open slots for '{service_slug}' between {start.isoformat()} and {end.isoformat()}."
    shown = open_slots[:24]
    extra = len(open_slots) - len(shown)
    lines: list[str] = []
    last_date = None
    for s in shown:
        local = s.astimezone(ZoneInfo(FIRM_TIMEZONE))
        dkey = local.date()
        if dkey != last_date:
            lines.append(f"{local.strftime('%a, %b %d, %Y')}:")
            last_date = dkey
        if service.duration_minutes > 60:
            slot_end = add_working_minutes(s, service.duration_minutes, ZoneInfo(FIRM_TIMEZONE))
            work_hours = service.duration_minutes // 60
            lines.append(
                f"  - {format_slot_clock(s)}–{format_slot_clock(slot_end)} "
                f"({work_hours} working hours; lunch 12:00–1:00 PM skipped)  ({s.isoformat()})"
            )
        else:
            lines.append(f"  - {format_slot_clock(s)}  ({s.isoformat()})")
    lunch_note = ""
    if service.duration_minutes > 60:
        lunch_note = "; lunch 12:00–1:00 PM is excluded from working time"
    text = (
        f"Open on-the-hour slots for {service.name} ({service.duration_minutes} min) "
        f"in {FIRM_TIMEZONE} (no noon{lunch_note}). Offer these clock times to the user:\n"
        + "\n".join(lines)
    )
    if extra > 0:
        text += f"\n…and {extra} more."
    return text


def book_appointment(
    session: Session,
    service_slug: str,
    start_iso: str,
    customer_email: str,
    customer_name: str = "",
    notes: str = "",
) -> str:
    email = normalize_email(customer_email)
    if not email or "@" not in email:
        return "[error] A valid customer_email is required to book."
    name = (customer_name or "").strip()
    if len(name) < 2:
        return "[error] customer_name is required (at least 2 characters)."

    service = session.scalar(
        select(Service).where(Service.slug == service_slug, Service.active.is_(True))
    )
    if not service or not service.bookable:
        return f"[error] Service '{service_slug}' is not available for booking."

    tz = ZoneInfo(FIRM_TIMEZONE)
    try:
        starts = datetime.fromisoformat(start_iso)
    except ValueError:
        return "[error] start_iso must be an ISO datetime."
    if starts.tzinfo is None:
        starts = starts.replace(tzinfo=tz)
    starts = starts.astimezone(tz).replace(second=0, microsecond=0)
    ends = add_working_minutes(starts, service.duration_minutes, tz)

    window_start = starts - timedelta(minutes=1)
    window_end = starts + timedelta(minutes=1)
    open_slots = _open_slot_datetimes(session, service, window_start, window_end)
    slot_ok = any(
        s.replace(second=0, microsecond=0) == starts for s in open_slots
    )
    if not slot_ok:
        return (
            "[error] That time is not available. Call list_availability and pick an open slot."
        )

    expire_stale_holds(session)
    conflict = session.scalar(
        select(Appointment).where(
            Appointment.status.in_(("booked", "pending_payment")),
            Appointment.starts_at < ends,
            Appointment.ends_at > starts,
        )
    )
    if conflict:
        return "[error] That time was just taken. Please pick another slot."

    pay_when = service_pay_when(service)
    appt_id = generate_appointment_id(starts)

    if pay_when == "checkout_to_hold":
        hold_minutes = PAYMENT_HOLD_MINUTES
        due = datetime.now(timezone.utc) + timedelta(minutes=hold_minutes)
        appt = Appointment(
            appointment_id=appt_id,
            service_id=service.id,
            customer_name=name,
            customer_email=email,
            starts_at=starts,
            ends_at=ends,
            status="pending_payment",
            cancel_code_hash=None,
            cancel_code_attempts=0,
            notes=notes or "",
            payment_due_at=due,
        )
        session.add(appt)
        session.flush()

        url = checkout_url_for(appt_id)
        used_stripe = False
        if stripe_enabled() and product_id_for_slug(service.slug):
            try:
                url, session_id, expires_at = create_checkout_session(
                    appointment_id=appt_id,
                    service_slug=service.slug,
                    customer_email=email,
                    customer_name=name,
                )
                appt.stripe_checkout_session_id = session_id
                appt.payment_due_at = expires_at
                due = expires_at
                hold_minutes = max(1, int((expires_at - datetime.now(timezone.utc)).total_seconds() / 60))
                used_stripe = True
                session.flush()
            except Exception as exc:  # noqa: BLE001
                appt.status = "expired"
                session.flush()
                return (
                    f"[error] Could not start Stripe Checkout ({exc}). "
                    "The slot was released. Call list_availability and book again."
                )

        when_display = format_when(starts)
        amount = getattr(service, "price_cents", 0) or 0
        currency = (getattr(service, "currency", None) or "USD").upper()
        dollars = amount / 100
        if used_stripe:
            extra = (
                f"(Slot is HELD until {due.isoformat()}, not confirmed. "
                f"Copy this exact markdown into your reply, using the real https URL, "
                f"not the words checkout_url or undefined: "
                f"[Pay with Stripe]({url}) "
                f"Stripe confirms payment via webhook and emails the cancellation code. "
                f"If they say they already paid but have no email, call simulate_payment. "
                f"No cancellation code was sent yet.)"
            )
        else:
            extra = (
                f"(Slot is HELD for {hold_minutes} minutes, not confirmed. "
                f"Do not say the appointment is confirmed. Give the user this checkout_url. "
                f"When they say they have paid, call simulate_payment with this appointment_id "
                f"and email. No cancellation code was sent yet.)"
            )
        return (
            f"status=pending_payment appointment_id={appt_id} service={service.name} "
            f"when={when_display} name={name} email={email} "
            f"amount={currency} {dollars:.2f} "
            f"payment_due_at={due.isoformat()} checkout_url={url} "
            f"{extra}"
        )

    cancel_code = generate_cancel_code()
    appt = Appointment(
        appointment_id=appt_id,
        service_id=service.id,
        customer_name=name,
        customer_email=email,
        starts_at=starts,
        ends_at=ends,
        status="booked",
        cancel_code_hash=hash_cancel_code(cancel_code),
        cancel_code_attempts=0,
        notes=notes or "",
        payment_due_at=None,
    )
    session.add(appt)
    session.flush()
    return _send_confirmation_and_result(appt, service, cancel_code, pay_when)


def _pay_copy_line(pay_when: str) -> str:
    if pay_when == "pay_on_arrival":
        return "Pay at your visit.\n"
    if pay_when == "pay_after":
        return (
            "Payment is due within 3 business days after the visit "
            "(billed for actual time).\n"
        )
    return ""


def _send_confirmation_and_result(
    appt: Appointment,
    service: Service,
    cancel_code: str,
    pay_when: str,
) -> str:
    name = appt.customer_name
    email = appt.customer_email
    loc = delivery_location(service)
    ful = service_fulfillment(service)
    when_display = format_when(appt.starts_at)
    cal_title = f"{service.name} — {FIRM_NAME}"
    if ful == "in_person":
        place_line = f"Location: {loc}\n"
        cal_location = loc
    else:
        place_line = f"Meeting link: {loc}\n"
        cal_location = loc
    pay_line = _pay_copy_line(pay_when)
    cal_details = (
        f"Appointment ID: {appt.appointment_id}\n"
        f"Service: {service.name}\n"
        f"Client: {name}\n"
        f"With: {FIRM_NAME}\n"
        f"{place_line}"
        f"{pay_line}"
        f"Cancellation code: {cancel_code}"
    )
    google_cal_url = google_calendar_template_url(
        title=cal_title,
        starts=appt.starts_at,
        ends=appt.ends_at,
        details=cal_details,
        location=cal_location,
    )
    if ful == "in_person":
        fulfillment_block = f"Location:\n{loc}\n\n"
        agent_place = f"location={loc}"
        email_hint = "the visit location"
    else:
        fulfillment_block = f"Meeting link (Zoom):\n{loc}\n\n"
        agent_place = f"meeting_link={loc}"
        email_hint = "the Zoom meeting link"
    pay_note = _pay_copy_line(pay_when)
    if pay_note and not pay_note.endswith("\n\n"):
        pay_note = pay_note.rstrip("\n") + "\n\n"
    send_template_email(
        "appointment_confirmation",
        email,
        {
            "service_name": service.name,
            "when_display": when_display,
            "customer_name": name,
            "customer_email": email,
            "appointment_id": appt.appointment_id,
            "cancel_code": cancel_code,
            "google_cal_url": google_cal_url,
            "fulfillment_block": fulfillment_block,
            "pay_note": pay_note,
            "meeting_link": loc,
        },
    )
    if pay_when == "pay_on_arrival":
        arrival = " Tell the user to pay at the visit."
    elif pay_when == "pay_after":
        arrival = (
            " Tell the user payment is due within 3 business days after the visit, "
            f"billed for actual time, and that the confirmation email includes the cancellation code and {email_hint}: {loc}"
        )
    else:
        arrival = (
            f" Tell the user the confirmation email includes the cancellation code and {email_hint}: {loc}"
        )
    return (
        f"status=booked appointment_id={appt.appointment_id} service={service.name} "
        f"when={when_display} name={name} email={email} "
        f"cancel_code={cancel_code} {agent_place} fulfillment={ful} pay_when={pay_when} "
        f"(A confirmation email was sent with the cancellation code.{arrival})"
    )


def simulate_payment(
    session: Session,
    appointment_id: str,
    customer_email: str,
) -> str:
    """Demo-only: mark a pending_payment hold as paid and send confirmation."""
    email = normalize_email(customer_email)
    aid = (appointment_id or "").strip()
    if not aid or not email or "@" not in email:
        return "[error] appointment_id and a valid customer_email are required."

    expire_stale_holds(session, skip_appointment_id=aid)
    appt = session.scalar(select(Appointment).where(Appointment.appointment_id == aid))
    if not appt or appt.customer_email != email:
        return "[error] No matching appointment for that id and email."

    if appt.status == "booked":
        return (
            f"status=booked appointment_id={appt.appointment_id} "
            "(Already confirmed. Do not invent a new cancellation code.)"
        )
    if appt.status == "expired":
        sid = (getattr(appt, "stripe_checkout_session_id", None) or "").strip()
        if not (sid and session_is_paid(sid)):
            return (
                "[error] The payment hold expired and the slot was released. "
                "Call list_availability and book again."
            )
    elif appt.status != "pending_payment":
        return f"[error] Appointment is {appt.status}, not awaiting payment."
    else:
        sid = (getattr(appt, "stripe_checkout_session_id", None) or "").strip()
        if sid:
            if not session_is_paid(sid):
                return (
                    "[error] Stripe has not marked this checkout as paid yet. "
                    "Ask the user to finish the checkout_url. "
                    "If they already paid, wait a moment and retry simulate_payment."
                )
        elif stripe_enabled() and product_id_for_slug(
            appt.service.slug if appt.service else ""
        ):
            return (
                "[error] This hold expects Stripe Checkout. "
                "Do not mark it paid without a Stripe session."
            )

    return finalize_paid_hold(session, appt)


def finalize_paid_hold(session: Session, appt: Appointment) -> str:
    """Move pending_payment → booked and send the confirmation email."""
    if appt.status == "booked":
        return (
            f"status=booked appointment_id={appt.appointment_id} "
            "(Already confirmed. Do not invent a new cancellation code.)"
        )
    expire_stale_holds(session, skip_appointment_id=appt.appointment_id)
    if appt.status == "expired":
        conflict = session.scalar(
            select(Appointment).where(
                Appointment.id != appt.id,
                Appointment.status.in_(("booked", "pending_payment")),
                Appointment.starts_at < appt.ends_at,
                Appointment.ends_at > appt.starts_at,
            )
        )
        if conflict:
            return (
                "[error] Payment arrived after the hold expired and the slot was taken. "
                "Create a support ticket."
            )
        appt.status = "pending_payment"
    if appt.status != "pending_payment":
        return f"[error] Appointment is {appt.status}, not awaiting payment."
    service = appt.service
    if service is None:
        return "[error] Appointment has no service catalog row."
    cancel_code = generate_cancel_code()
    appt.status = "booked"
    appt.cancel_code_hash = hash_cancel_code(cancel_code)
    appt.payment_due_at = None
    session.flush()
    pay_when = service_pay_when(service)
    return _send_confirmation_and_result(appt, service, cancel_code, pay_when)


def cancel_appointment(
    session: Session,
    email: str,
    cancel_code: str,
    appointment_id: str | None = None,
) -> str:
    email_n = normalize_email(email)
    if not email_n or not (cancel_code or "").strip():
        return "[error] Both email and cancel_code are required."

    q = select(Appointment).where(
        Appointment.customer_email == email_n,
        Appointment.status == "booked",
    )
    if appointment_id:
        q = q.where(Appointment.appointment_id == appointment_id.strip())
    rows = list(session.scalars(q).all())

    generic_fail = "Email or cancellation code is incorrect."

    if not rows:
        return generic_fail

    if len(rows) > 1 and not appointment_id:
        ids = ", ".join(a.appointment_id for a in rows[:5])
        return (
            "Multiple appointments found for this email. "
            f"Please provide appointment_id (one of: {ids})."
        )

    appt = rows[0]
    if appt.cancel_code_attempts >= CANCEL_CODE_MAX_ATTEMPTS:
        return (
            "[escalate] Too many failed cancellation attempts. "
            "Create a high-priority support ticket for this customer."
        )

    now = datetime.now(ZoneInfo(FIRM_TIMEZONE))
    starts = appt.starts_at
    if starts.tzinfo is None:
        # SQLite may drop tzinfo; treat naive values as firm-local.
        starts = starts.replace(tzinfo=ZoneInfo(FIRM_TIMEZONE))
    hours_until = (starts.astimezone(ZoneInfo(FIRM_TIMEZONE)) - now).total_seconds() / 3600
    if hours_until < CANCEL_WINDOW_HOURS:
        return (
            f"[escalate] Self-service cancellation is not allowed within "
            f"{CANCEL_WINDOW_HOURS} hours of the appointment. "
            "Create a high-priority support ticket."
        )

    if hash_cancel_code(cancel_code) != (appt.cancel_code_hash or ""):
        appt.cancel_code_attempts += 1
        session.flush()
        remaining = CANCEL_CODE_MAX_ATTEMPTS - appt.cancel_code_attempts
        if remaining <= 0:
            return (
                "[escalate] Too many failed cancellation attempts. "
                "Create a high-priority support ticket for this customer."
            )
        return generic_fail

    service = appt.service
    appt.status = "cancelled"
    appt.cancel_code_hash = None
    appt.cancelled_at = datetime.now(timezone.utc)
    session.flush()

    when_display = format_when(starts)
    send_template_email(
        "appointment_cancelled",
        email_n,
        {
            "service_name": service.name if service else "Appointment",
            "when_display": when_display,
            "appointment_id": appt.appointment_id,
        },
    )
    return (
        f"status=cancelled appointment_id={appt.appointment_id} "
        f"when={when_display} email={email_n} "
        "(A cancellation confirmation email was sent.)"
    )


def seed_defaults(session: Session) -> None:
    """Idempotent seed for demo services and Mon–Fri 9–17 availability."""
    by_slug = {s.slug: s for s in session.scalars(select(Service)).all()}
    for slug, spec in SERVICE_CATALOG.items():
        image = SERVICE_IMAGES.get(slug, f"/assets/{slug}.jpg")
        row = by_slug.get(slug)
        if row is None:
            session.add(
                Service(
                    slug=slug,
                    name=spec["name"],
                    description=spec["description"],
                    duration_minutes=spec["duration_minutes"],
                    bookable=spec["bookable"],
                    image_url=image,
                    price_cents=spec.get("price_cents", 0),
                    currency=spec.get("currency", "USD"),
                    pay_when=spec.get("pay_when", "none"),
                    fulfillment=spec.get("fulfillment", "online"),
                    location_text=spec.get("location_text")
                    or (
                        MEETING_LINK
                        if spec.get("fulfillment", "online") == "online"
                        else ""
                    ),
                )
            )
        else:
            row.name = spec["name"]
            row.description = spec["description"]
            row.duration_minutes = spec["duration_minutes"]
            row.bookable = spec["bookable"]
            if not (getattr(row, "image_url", None) or "").strip():
                row.image_url = image
            row.price_cents = spec.get("price_cents", 0)
            row.currency = spec.get("currency", "USD")
            row.pay_when = spec.get("pay_when", "none")
            row.fulfillment = spec.get("fulfillment", "online")
            row.location_text = spec.get("location_text") or (
                MEETING_LINK if spec.get("fulfillment", "online") == "online" else ""
            )

    existing_rules = session.scalar(select(AvailabilityRule).limit(1))
    if not existing_rules:
        for weekday in range(0, 5):  # Mon–Fri
            session.add(
                AvailabilityRule(
                    weekday=weekday,
                    start_time=time(9, 0),
                    end_time=time(17, 0),
                    timezone=FIRM_TIMEZONE,
                    active=True,
                )
            )
