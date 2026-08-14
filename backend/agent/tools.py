"""LangGraph-callable tools wrapping business services."""
from __future__ import annotations

from backend.db import session_scope
from backend.services.ragflow import retrieve as _retrieve
from backend.services.scheduling import (
    book_appointment as _book,
    cancel_appointment as _cancel,
    list_availability as _list_availability,
    list_services as _list_services,
    simulate_payment as _simulate_payment,
)
from backend.services.tickets import create_support_ticket as _create_ticket


def ragflow_retrieve(query: str) -> str:
    """Search the firm knowledge base (local Markdown or RAGFlow) for facts relevant to the user's question."""
    return _retrieve(query)


def get_services() -> str:
    """Return the catalog: names, duration, bookable, price, pay_when, fulfillment, location."""
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
    customer_name: str,
    customer_email: str,
    notes: str = "",
) -> str:
    """Book an open slot. Requires customer_name and customer_email.

    For pay_when=none or pay_on_arrival, confirms immediately and emails a cancellation code.
    For checkout_to_hold, holds the slot (pending_payment) and returns checkout_url; not confirmed yet.
    """
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


def simulate_payment(appointment_id: str, customer_email: str) -> str:
    """Demo-only: confirm a pending_payment hold after the user says they paid. Not real Stripe."""
    with session_scope() as session:
        return _simulate_payment(
            session,
            appointment_id=appointment_id,
            customer_email=customer_email,
        )


def create_ticket(
    name: str,
    email: str,
    phone: str,
    preferred_call_window: str,
    question: str,
    reason: str,
    appointment_id: str = "",
    priority_hint: str = "normal",
) -> str:
    """Create a support ticket when the user asks for a human or the issue cannot be resolved.

    Requires name, email, phone, preferred_call_window, and question (the user's request in their own words).
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
    simulate_payment,
    cancel_appointment,
    create_ticket,
]
