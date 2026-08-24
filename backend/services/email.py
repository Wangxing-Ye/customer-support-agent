"""Outbound email: console | smtp | resend."""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Any

import requests

from backend.config import (
    EMAIL_FROM,
    EMAIL_PROVIDER,
    FIRM_NAME,
    FIRM_TIMEZONE,
    FIRM_WEBSITE,
    MEETING_LINK,
    RESEND_API_KEY,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USE_TLS,
    SMTP_USER,
)
from backend.db import session_scope
from backend.models import EmailLog
from backend.services.sla import format_respond_by

logger = logging.getLogger(__name__)


TEMPLATES = {
    "appointment_confirmation": {
        "subject": "Appointment confirmed — {firm_name}",
        "body": (
            "Appointment confirmed\n\n"
            "Service: {service_name}\n"
            "When: {when_display}\n"
            "Name: {customer_name}\n"
            "Email: {customer_email}\n"
            "Appointment ID: {appointment_id}\n\n"
            "Cancellation code: {cancel_code}\n"
            "To cancel via chat, provide this email and cancellation code.\n\n"
            "{fulfillment_block}"
            "{pay_note}"
            "Add to Google Calendar:\n"
            "{google_cal_url}\n"
        ),
    },
    "appointment_cancelled": {
        "subject": "Appointment cancelled — {firm_name}",
        "body": (
            "Your appointment has been cancelled.\n\n"
            "Service: {service_name}\n"
            "Was scheduled: {when_display}\n"
            "Appointment ID: {appointment_id}\n"
        ),
    },
    "appointment_rescheduled": {
        "subject": "Appointment rescheduled — {firm_name}",
        "body": (
            "Your appointment has been rescheduled.\n\n"
            "Service: {service_name}\n"
            "Previously: {old_when_display}\n"
            "New time: {when_display}\n"
            "Name: {customer_name}\n"
            "Appointment ID: {appointment_id}\n\n"
            "{fulfillment_block}"
            "Your existing cancellation code still applies.\n\n"
            "Add to Google Calendar:\n"
            "{google_cal_url}\n"
        ),
    },
    "ticket_created": {
        "subject": "Support ticket {ticket_id} — {firm_name}",
        "body": (
            "We received your request and created support ticket {ticket_id}.\n\n"
            "Your question / request:\n{summary}\n\n"
            "Name: {name}\n"
            "Email: {email}\n"
            "Phone: {phone}\n"
            "Best time to call: {preferred_call_window}\n"
            "A team member will reply by email by {respond_by_display}, "
            "and may call during your preferred window if needed.\n"
        ),
    },
    "owner_email_verify": {
        "subject": "Verify owner email — {firm_name}",
        "body": (
            "Your owner dashboard verification code is: {code}\n\n"
            "This code expires in {expires_minutes} minutes.\n"
            "If you did not request this, ignore this email.\n"
        ),
    },
    "owner_password_reset": {
        "subject": "Reset owner password — {firm_name}",
        "body": (
            "Reset your owner dashboard password using this link:\n"
            "{reset_url}\n\n"
            "Or enter this token in the reset form: {token}\n\n"
            "This link expires in {expires_minutes} minutes.\n"
            "If you did not request a reset, ignore this email.\n"
        ),
    },
}


def format_email_footer() -> str:
    return (
        f"—\n"
        f"{FIRM_NAME}\n"
        "Our service agent is available 24/7\n"
        f"{FIRM_WEBSITE}"
    )


def _render(template: str, ctx: dict[str, Any]) -> tuple[str, str]:
    spec = TEMPLATES[template]
    return spec["subject"].format(**ctx), spec["body"].format(**ctx)


def _deliver(to_email: str, subject: str, body: str) -> tuple[str, str]:
    provider = EMAIL_PROVIDER
    try:
        if provider == "console":
            logger.info("EMAIL console → %s | %s\n%s", to_email, subject, body)
            print(f"\n===== EMAIL ({provider}) → {to_email} =====\n{subject}\n\n{body}\n=====\n")
            return "sent", "console"

        if provider == "resend":
            if not RESEND_API_KEY:
                return "error", "RESEND_API_KEY not set"
            resp = requests.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={"from": EMAIL_FROM, "to": [to_email], "subject": subject, "text": body},
                timeout=30,
            )
            if resp.status_code >= 300:
                return "error", resp.text
            return "sent", "resend"

        if provider == "smtp":
            if not SMTP_HOST:
                return "error", "SMTP_HOST not set"
            msg = EmailMessage()
            msg["From"] = EMAIL_FROM
            msg["To"] = to_email
            msg["Subject"] = subject
            msg.set_content(body)
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
                if SMTP_USE_TLS:
                    smtp.starttls()
                if SMTP_USER:
                    smtp.login(SMTP_USER, SMTP_PASSWORD)
                smtp.send_message(msg)
            return "sent", "smtp"

        return "error", f"Unknown EMAIL_PROVIDER={provider}"
    except Exception as exc:  # noqa: BLE001
        logger.exception("email delivery failed")
        return "error", str(exc)[:2000]


def send_template_email(template: str, to_email: str, context: dict[str, Any]) -> dict[str, str]:
    ctx = {
        "firm_name": FIRM_NAME,
        "timezone": FIRM_TIMEZONE,
        "meeting_link": MEETING_LINK,
        "fulfillment_block": "",
        "pay_note": "",
        **context,
    }
    if "respond_by" in ctx and "respond_by_display" not in ctx:
        ctx["respond_by_display"] = format_respond_by(ctx["respond_by"])
    subject, body = _render(template, ctx)
    body = body.rstrip() + "\n\n" + format_email_footer() + "\n"
    status, detail = _deliver(to_email, subject, body)
    try:
        with session_scope() as session:
            session.add(
                EmailLog(
                    template=template,
                    to_email=to_email,
                    subject=subject,
                    status=status,
                    detail=detail[:2000],
                )
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to log email: %s", exc)
    return {"status": status, "detail": detail, "subject": subject}
