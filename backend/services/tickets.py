"""Support ticket creation with SLA respond_by."""
from __future__ import annotations

import secrets
import string
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import FIRM_TIMEZONE, TICKET_DEDUP_HOURS
from backend.models import Ticket
from backend.services.email import send_template_email
from backend.services.sla import compute_respond_by, format_respond_by
from backend.services.scheduling import normalize_email


def generate_ticket_id() -> str:
    suffix = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
    return f"TKT-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{suffix}"


def _normalize_phone(phone: str) -> str:
    raw = (phone or "").strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) < 10:
        return ""
    return raw


def create_support_ticket(
    session: Session,
    email: str,
    summary: str,
    reason: str,
    name: str = "",
    phone: str = "",
    preferred_call_window: str = "",
    appointment_id: str | None = None,
    priority_hint: str | None = None,
) -> str:
    email_n = normalize_email(email)
    if not email_n or "@" not in email_n:
        return "[error] A valid email is required to create a ticket."
    name_n = (name or "").strip()
    if len(name_n) < 2:
        return "[error] A name is required (at least 2 characters)."
    phone_n = _normalize_phone(phone)
    if not phone_n:
        return "[error] A phone number (at least 10 digits) is required so we can call if needed."
    window = (preferred_call_window or "").strip()
    if not window:
        return (
            "[error] preferred_call_window is required "
            "(e.g. 'Weekdays 2-4 PM PT' or 'Tomorrow after 10 AM')."
        )
    summary_t = (summary or "").strip()
    if len(summary_t) < 10:
        return (
            "[error] A question or request description is required "
            "(what the user wants help with, in their own words)."
        )

    reason_n = (reason or "unresolved").strip().lower()
    if reason_n not in ("user_requested", "unresolved"):
        reason_n = "unresolved"

    priority = (priority_hint or "normal").strip().lower()
    if priority not in ("normal", "high"):
        priority = "normal"
    # Escalate hints from cancel flow
    if "high" in (priority_hint or "").lower():
        priority = "high"

    # Dedup: same email + open ticket within window with similar summary prefix
    since = datetime.now(timezone.utc) - timedelta(hours=TICKET_DEDUP_HOURS)
    recent = session.scalars(
        select(Ticket).where(
            Ticket.email == email_n,
            Ticket.status == "open",
            Ticket.created_at >= since,
        )
    ).all()
    for t in recent:
        if t.summary[:80].lower() == summary_t[:80].lower():
            return (
                f"ticket_id={t.ticket_id} status={t.status} priority={t.priority} "
                f"respond_by={t.respond_by.isoformat()} "
                f"respond_by_display={format_respond_by(t.respond_by)} "
                f"preferred_call_window={getattr(t, 'preferred_call_window', '') or window} "
                "(Existing open ticket reused — do not invent a new SLA. "
                "Do not repeat full email, phone, or name in your reply.)"
            )

    respond_by = compute_respond_by(priority)
    ticket_id = generate_ticket_id()
    ticket = Ticket(
        ticket_id=ticket_id,
        email=email_n,
        name=name_n,
        phone=phone_n,
        preferred_call_window=window,
        summary=summary_t,
        reason=reason_n,
        priority=priority,
        status="open",
        appointment_id=(appointment_id or None),
        respond_by=respond_by,
    )
    session.add(ticket)
    session.flush()

    display = format_respond_by(respond_by)
    send_template_email(
        "ticket_created",
        email_n,
        {
            "ticket_id": ticket_id,
            "summary": summary_t,
            "name": name_n,
            "email": email_n,
            "phone": phone_n,
            "preferred_call_window": window,
            "respond_by": respond_by,
            "respond_by_display": display,
        },
    )
    return (
        f"ticket_id={ticket_id} status=open priority={priority} reason={reason_n} "
        f"respond_by={respond_by.isoformat()} "
        f"respond_by_display={display} "
        f"preferred_call_window={window} "
        "(Use respond_by_display exactly in your reply. Do not invent another time. "
        "A confirmation email was sent. Do not repeat full email, phone, or name.)"
    )
