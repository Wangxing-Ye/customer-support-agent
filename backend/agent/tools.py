"""LangGraph-callable tools wrapping business services."""
from __future__ import annotations

from backend.db import session_scope
from backend.services.ragflow import ragflow_retrieve as _ragflow_retrieve
from backend.services.scheduling import (
    book_appointment as _book,
    cancel_appointment as _cancel,
    list_availability as _list_availability,
    list_services as _list_services,
)
from backend.services.tickets import create_support_ticket as _create_ticket


def ragflow_retrieve(query: str) -> str:
    """Search the firm knowledge base for facts relevant to the user's question."""
    return _ragflow_retrieve(query)


def get_services() -> str:
    """Return the current professional service catalog (names, duration, bookable flag)."""
    with session_scope() as session:
        return _list_services(session)


def list_availability(
    service_slug: str,
    date_from: str = "",
    date_to: str = "",
) -> str:
    """List open on-the-hour appointment slots for a bookable service_slug (clock time + ISO)."""
    with session_scope() as session:
        return _list_availability(
            session,
            service_slug=service_slug,
            date_from=date_from or None,
            date_to=date_to or None,
        )


def book_appointment(
    service_slug: str,
    start_iso: str,
    customer_email: str,
    customer_name: str = "",
    notes: str = "",
) -> str:
    """Book an open slot. Sends confirmation email with cancellation code and Zoom meeting link. Requires customer_email."""
    with session_scope() as session:
        return _book(
            session,
            service_slug=service_slug,
            start_iso=start_iso,
            customer_email=customer_email,
            customer_name=customer_name,
            notes=notes,
        )


def cancel_appointment(
    email: str,
    cancel_code: str,
    appointment_id: str = "",
) -> str:
    """Cancel a booked appointment using customer email + cancellation code from the confirmation email."""
    with session_scope() as session:
        return _cancel(
            session,
            email=email,
            cancel_code=cancel_code,
            appointment_id=appointment_id or None,
        )


def create_ticket(
    email: str,
    phone: str,
    preferred_call_window: str,
    question: str,
    reason: str,
    name: str = "",
    appointment_id: str = "",
    priority_hint: str = "normal",
) -> str:
    """Create a support ticket when the user asks for a human or the issue cannot be resolved.

    Requires email, phone, preferred_call_window, and question (the user's request in their own words).
    reason must be 'user_requested' or 'unresolved'.
    Returns ticket_id and respond_by_display — use that display time exactly in your reply.
    """
    with session_scope() as session:
        return _create_ticket(
            session,
            email=email,
            summary=question,
            reason=reason,
            name=name,
            phone=phone,
            preferred_call_window=preferred_call_window,
            appointment_id=appointment_id or None,
            priority_hint=priority_hint,
        )


TOOLS = [
    ragflow_retrieve,
    get_services,
    list_availability,
    book_appointment,
    cancel_appointment,
    create_ticket,
]
