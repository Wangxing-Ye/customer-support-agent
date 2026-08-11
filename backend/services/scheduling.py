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
    FIRM_NAME,
    FIRM_TIMEZONE,
    MEETING_LINK,
)
from backend.models import Appointment, AvailabilityRule, Service
from backend.services.email import send_template_email

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
            "Complimentary 30-minute discovery call to discuss your needs. "
            "Each client is eligible for one free Introductory Consultation only."
        ),
        "duration_minutes": 30,
        "bookable": True,
        "price": "Free (one 30-minute session per client)",
    },
    "strategy-session": {
        "name": "Strategy Session",
        "description": (
            "One-hour working session with a senior advisor. "
            "Priced at USD 500 per hour; each Strategy Session is one hour."
        ),
        "duration_minutes": 60,
        "bookable": True,
        "price": "USD 500 per hour (1 hour per session)",
    },
    "document-review": {
        "name": "Document Review",
        "description": (
            "Document review with detailed email feedback at USD 250 per hour. "
            "Not bookable online — request via a support ticket."
        ),
        "duration_minutes": 60,
        "bookable": False,
        "price": "USD 250 per hour, detailed email feedback (request via ticket)",
    },
}


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
        blocks.append(
            f"### {s.name}\n"
            f"Slug: `{s.slug}` · {s.duration_minutes} min · {bookable}\n"
            f"{price_line}"
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
    """Return on-the-hour slot starts for one local day (no noon)."""
    local_day = day.astimezone(tz).date()
    slots: list[datetime] = []
    for hour in SLOT_START_HOURS:
        slot = datetime.combine(local_day, time(hour, 0), tzinfo=tz)
        if slot.time() < rule.start_time:
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
    booked = session.scalars(
        select(Appointment).where(
            Appointment.status == "booked",
            Appointment.starts_at < end,
            Appointment.ends_at > start,
        )
    ).all()
    booked_starts = {a.starts_at.astimezone(tz).replace(second=0, microsecond=0) for a in booked}

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
                key = slot.replace(second=0, microsecond=0)
                if key in booked_starts:
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
        lines.append(f"  - {format_slot_clock(s)}  ({s.isoformat()})")
    text = (
        f"Open on-the-hour slots for {service.name} ({service.duration_minutes} min) "
        f"in {FIRM_TIMEZONE} (no noon). Offer these clock times to the user:\n"
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
    ends = starts + timedelta(minutes=service.duration_minutes)

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

    conflict = session.scalar(
        select(Appointment).where(
            Appointment.status == "booked",
            Appointment.starts_at < ends,
            Appointment.ends_at > starts,
        )
    )
    if conflict:
        return "[error] That time was just taken. Please pick another slot."

    if service.slug == "intro-consult":
        prior = session.scalar(
            select(Appointment).where(
                Appointment.customer_email == email,
                Appointment.service_id == service.id,
            )
        )
        if prior:
            return (
                "[error] This email has already used the complimentary Introductory "
                "Consultation (one free 30-minute session per client). "
                "Please book a Strategy Session or request Document Review via a support ticket."
            )

    cancel_code = generate_cancel_code()
    appt_id = generate_appointment_id(starts)
    appt = Appointment(
        appointment_id=appt_id,
        service_id=service.id,
        customer_name=(customer_name or "").strip(),
        customer_email=email,
        starts_at=starts,
        ends_at=ends,
        status="booked",
        cancel_code_hash=hash_cancel_code(cancel_code),
        cancel_code_attempts=0,
        notes=notes or "",
    )
    session.add(appt)
    session.flush()

    when_display = format_when(starts)
    cal_title = f"{service.name} — {FIRM_NAME}"
    cal_details = (
        f"Appointment ID: {appt_id}\n"
        f"Service: {service.name}\n"
        f"With: {FIRM_NAME}\n"
        f"Meeting link: {MEETING_LINK}\n"
        f"Cancellation code: {cancel_code}"
    )
    google_cal_url = google_calendar_template_url(
        title=cal_title,
        starts=starts,
        ends=ends,
        details=cal_details,
        location=MEETING_LINK,
    )
    send_template_email(
        "appointment_confirmation",
        email,
        {
            "service_name": service.name,
            "when_display": when_display,
            "customer_email": email,
            "appointment_id": appt_id,
            "cancel_code": cancel_code,
            "google_cal_url": google_cal_url,
            "meeting_link": MEETING_LINK,
        },
    )
    return (
        f"status=booked appointment_id={appt_id} service={service.name} "
        f"when={when_display} email={email} "
        f"cancel_code={cancel_code} meeting_link={MEETING_LINK} "
        f"(A confirmation email was sent with the cancellation code and this Zoom meeting link. "
        f"Tell the user the confirmation email includes the cancellation code and the meeting link: {MEETING_LINK})"
    )


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
                )
            )
        else:
            row.name = spec["name"]
            row.description = spec["description"]
            row.duration_minutes = spec["duration_minutes"]
            row.bookable = spec["bookable"]
            if not (getattr(row, "image_url", None) or "").strip():
                row.image_url = image

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
