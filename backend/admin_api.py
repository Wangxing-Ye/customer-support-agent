"""Owner dashboard API: auth, setup, appointments, tickets."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from backend.config import ADMIN_UI_ORIGIN
from backend.db import session_scope
from backend.models import Appointment, Owner, Ticket, TicketActivity
from backend.owner_auth import (
    create_owner_token,
    generate_email_code,
    generate_reset_token,
    hash_opaque_token,
    hash_password,
    require_owner_ready,
    require_owner_setup_pending,
    validate_new_password,
    verify_owner_jwt,
    verify_password,
)
from backend.rate_limit import enforce_admin_login_limits
from backend.services.email import send_template_email
from backend.services.scheduling import (
    cancel_appointment_as_owner,
    delivery_location,
    list_open_slots,
    mark_appointment_outcome_as_owner,
    normalize_email,
    reschedule_appointment_as_owner,
)
from backend.services.sla import format_respond_by
from backend.services.tickets import (
    PHONE_OUTCOMES,
    add_ticket_note,
    add_ticket_phone_log,
    list_ticket_activities,
    send_ticket_email_reply,
)

router = APIRouter(prefix="/admin", tags=["admin"])

VERIFY_CODE_TTL_MINUTES = 30
RESET_TOKEN_TTL_MINUTES = 60


class LoginBody(BaseModel):
    username: str
    password: str


class RequestEmailCodeBody(BaseModel):
    email: str


class VerifySetupBody(BaseModel):
    code: str
    new_password: str = Field(min_length=1)


class ForgotPasswordBody(BaseModel):
    email: str


class ResetPasswordBody(BaseModel):
    token: str
    new_password: str = Field(min_length=1)


class TicketPatchBody(BaseModel):
    status: Literal["open", "in_progress", "closed"]


class TicketNoteBody(BaseModel):
    body: str = Field(min_length=1)


class TicketPhoneLogBody(BaseModel):
    phone_outcome: Literal[
        "reached",
        "no_answer",
        "left_voicemail",
        "wrong_number",
        "other",
    ]
    body: str = Field(min_length=1)


class TicketReplyBody(BaseModel):
    body: str = Field(min_length=1)


class RescheduleBody(BaseModel):
    start_iso: str


class AppointmentOutcomeBody(BaseModel):
    status: Literal["no_show", "completed"]


def _get_owner(session: Session, owner_id: int) -> Owner:
    owner = session.get(Owner, owner_id)
    if owner is None:
        raise HTTPException(status_code=401, detail="Owner not found")
    return owner


def _appointment_dict(appt: Appointment) -> dict[str, Any]:
    svc = appt.service
    loc = (getattr(appt, "location_for_service", None) or "").strip()
    if not loc and svc is not None:
        loc = delivery_location(svc)
    return {
        "appointment_id": appt.appointment_id,
        "status": appt.status,
        "customer_name": appt.customer_name,
        "customer_email": appt.customer_email,
        "starts_at": appt.starts_at.isoformat() if appt.starts_at else None,
        "ends_at": appt.ends_at.isoformat() if appt.ends_at else None,
        "service_name": svc.name if svc else None,
        "service_slug": svc.slug if svc else None,
        "location_for_service": loc,
        "notes": appt.notes or "",
        "created_at": appt.created_at.isoformat() if appt.created_at else None,
        "cancelled_at": appt.cancelled_at.isoformat() if appt.cancelled_at else None,
        "payment_due_at": (
            appt.payment_due_at.isoformat() if appt.payment_due_at else None
        ),
    }


def _ticket_dict(t: Ticket, *, latest_note: str | None = None) -> dict[str, Any]:
    data = {
        "ticket_id": t.ticket_id,
        "status": t.status,
        "priority": t.priority,
        "name": t.name,
        "email": t.email,
        "phone": t.phone,
        "preferred_call_window": t.preferred_call_window,
        "summary": t.summary,
        "reason": t.reason,
        "appointment_id": t.appointment_id,
        "respond_by": t.respond_by.isoformat() if t.respond_by else None,
        "respond_by_display": format_respond_by(t.respond_by) if t.respond_by else None,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }
    if latest_note is not None:
        data["latest_note"] = latest_note
    return data


def _latest_notes_by_ticket(
    session: Session, ticket_ids: list[str]
) -> dict[str, str]:
    ids = [tid for tid in ticket_ids if tid]
    if not ids:
        return {}
    rows = list(
        session.scalars(
            select(TicketActivity)
            .where(
                TicketActivity.ticket_id.in_(ids),
                TicketActivity.kind == "note",
            )
            .order_by(TicketActivity.created_at.desc())
        ).all()
    )
    latest: dict[str, str] = {}
    for a in rows:
        if a.ticket_id not in latest:
            latest[a.ticket_id] = a.body or ""
    return latest


def _activity_dict(a: TicketActivity) -> dict[str, Any]:
    return {
        "id": a.id,
        "ticket_id": a.ticket_id,
        "kind": a.kind,
        "body": a.body,
        "phone_outcome": a.phone_outcome or "",
        "created_by": a.created_by or "",
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _owner_username(claims: dict) -> str:
    return str(claims.get("username") or claims.get("sub") or "").strip()


@router.post("/login")
def admin_login(body: LoginBody, request: Request):
    enforce_admin_login_limits(request)
    username = (body.username or "").strip()
    with session_scope() as session:
        owner = session.scalars(
            select(Owner).where(Owner.username == username)
        ).first()
        if owner is None or not verify_password(body.password, owner.password_hash):
            raise HTTPException(status_code=401, detail="Invalid username or password")
        issued = create_owner_token(
            owner_id=owner.id,
            username=owner.username,
            setup_completed=bool(owner.setup_completed),
        )
        issued["email"] = owner.email
        issued["email_verified"] = bool(owner.email_verified)
        return issued


@router.post("/setup/request-email-code")
def setup_request_email_code(
    body: RequestEmailCodeBody,
    claims: dict = Depends(require_owner_setup_pending),
):
    email = normalize_email(body.email)
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email is required")
    code = generate_email_code()
    with session_scope() as session:
        owner = _get_owner(session, int(claims["uid"]))
        if owner.setup_completed:
            raise HTTPException(status_code=400, detail="Setup already completed")
        owner.email = email
        owner.email_verified = False
        owner.email_verify_code_hash = hash_opaque_token(code)
        owner.email_verify_expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=VERIFY_CODE_TTL_MINUTES
        )
    send_template_email(
        "owner_email_verify",
        email,
        {"code": code, "expires_minutes": VERIFY_CODE_TTL_MINUTES},
    )
    return {"ok": True, "detail": "If the email is valid, a verification code was sent."}


@router.post("/setup/verify-and-set-password")
def setup_verify_and_set_password(
    body: VerifySetupBody,
    claims: dict = Depends(require_owner_setup_pending),
):
    new_password = validate_new_password(body.new_password)
    code = (body.code or "").strip()
    with session_scope() as session:
        owner = _get_owner(session, int(claims["uid"]))
        if owner.setup_completed:
            raise HTTPException(status_code=400, detail="Setup already completed")
        if not owner.email or not owner.email_verify_code_hash:
            raise HTTPException(
                status_code=400,
                detail="Request an email verification code first",
            )
        expires = owner.email_verify_expires_at
        if expires is not None and expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if not expires or expires < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="Verification code expired")
        if hash_opaque_token(code) != owner.email_verify_code_hash:
            raise HTTPException(status_code=400, detail="Invalid verification code")

        owner.password_hash = hash_password(new_password)
        owner.email_verified = True
        owner.setup_completed = True
        owner.email_verify_code_hash = None
        owner.email_verify_expires_at = None
        username = owner.username
        owner_id = owner.id
        email = owner.email

    issued = create_owner_token(
        owner_id=owner_id,
        username=username,
        setup_completed=True,
    )
    issued["email"] = email
    issued["email_verified"] = True
    return issued


@router.post("/forgot-password")
def forgot_password(body: ForgotPasswordBody, request: Request):
    enforce_admin_login_limits(request)
    email = normalize_email(body.email)
    generic = {
        "ok": True,
        "detail": "If that email is registered, a reset link was sent.",
    }
    if not email:
        return generic

    token = generate_reset_token()
    send_to: str | None = None
    with session_scope() as session:
        owner = session.scalars(
            select(Owner).where(
                Owner.email == email,
                Owner.email_verified.is_(True),
                Owner.setup_completed.is_(True),
            )
        ).first()
        if owner is None:
            return generic
        owner.password_reset_token_hash = hash_opaque_token(token)
        owner.password_reset_expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=RESET_TOKEN_TTL_MINUTES
        )
        send_to = owner.email

    if send_to:
        reset_url = f"{ADMIN_UI_ORIGIN}/admin.html?reset={token}"
        send_template_email(
            "owner_password_reset",
            send_to,
            {
                "token": token,
                "reset_url": reset_url,
                "expires_minutes": RESET_TOKEN_TTL_MINUTES,
            },
        )
    return generic


@router.post("/reset-password")
def reset_password(body: ResetPasswordBody, request: Request):
    enforce_admin_login_limits(request)
    new_password = validate_new_password(body.new_password)
    token = (body.token or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="Reset token is required")
    token_hash = hash_opaque_token(token)
    with session_scope() as session:
        owner = session.scalars(
            select(Owner).where(Owner.password_reset_token_hash == token_hash)
        ).first()
        if owner is None:
            raise HTTPException(status_code=400, detail="Invalid or expired reset token")
        expires = owner.password_reset_expires_at
        if expires is not None and expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if not expires or expires < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="Invalid or expired reset token")
        owner.password_hash = hash_password(new_password)
        owner.password_reset_token_hash = None
        owner.password_reset_expires_at = None
    return {"ok": True, "detail": "Password updated. You can log in."}


@router.get("/me")
def admin_me(claims: dict = Depends(verify_owner_jwt)):
    with session_scope() as session:
        owner = _get_owner(session, int(claims["uid"]))
        return {
            "username": owner.username,
            "email": owner.email,
            "email_verified": bool(owner.email_verified),
            "setup_completed": bool(owner.setup_completed),
            "setup_required": not bool(owner.setup_completed),
        }


@router.get("/appointments")
def list_appointments(
    status: str | None = None,
    from_ts: str | None = None,
    to_ts: str | None = None,
    _claims: dict = Depends(require_owner_ready),
):
    with session_scope() as session:
        q = select(Appointment).options(joinedload(Appointment.service))
        if status:
            q = q.where(Appointment.status == status.strip())
        if from_ts:
            try:
                start = datetime.fromisoformat(from_ts.replace("Z", "+00:00"))
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="Invalid from") from exc
            q = q.where(Appointment.starts_at >= start)
        if to_ts:
            try:
                end = datetime.fromisoformat(to_ts.replace("Z", "+00:00"))
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="Invalid to") from exc
            q = q.where(Appointment.starts_at <= end)
        q = q.order_by(Appointment.starts_at.desc()).limit(200)
        rows = list(session.scalars(q).unique().all())
        return {"appointments": [_appointment_dict(a) for a in rows]}


@router.get("/appointments/{appointment_id}")
def get_appointment(
    appointment_id: str,
    _claims: dict = Depends(require_owner_ready),
):
    with session_scope() as session:
        appt = session.scalars(
            select(Appointment)
            .options(joinedload(Appointment.service))
            .where(Appointment.appointment_id == appointment_id.strip())
        ).first()
        if appt is None:
            raise HTTPException(status_code=404, detail="Appointment not found")
        return _appointment_dict(appt)


@router.post("/appointments/{appointment_id}/cancel")
def cancel_appointment(
    appointment_id: str,
    _claims: dict = Depends(require_owner_ready),
):
    with session_scope() as session:
        result = cancel_appointment_as_owner(session, appointment_id)
    if result.startswith("[error]"):
        raise HTTPException(status_code=400, detail=result.removeprefix("[error]").strip())
    return {"ok": True, "detail": result}


@router.post("/appointments/{appointment_id}/outcome")
def mark_appointment_outcome(
    appointment_id: str,
    body: AppointmentOutcomeBody,
    _claims: dict = Depends(require_owner_ready),
):
    with session_scope() as session:
        result = mark_appointment_outcome_as_owner(
            session, appointment_id, body.status
        )
    if result.startswith("[error]"):
        raise HTTPException(status_code=400, detail=result.removeprefix("[error]").strip())
    return {"ok": True, "detail": result}


@router.get("/appointments/{appointment_id}/slots")
def appointment_open_slots(
    appointment_id: str,
    date_from: str | None = None,
    date_to: str | None = None,
    _claims: dict = Depends(require_owner_ready),
):
    with session_scope() as session:
        appt = session.scalars(
            select(Appointment)
            .options(joinedload(Appointment.service))
            .where(Appointment.appointment_id == appointment_id.strip())
        ).first()
        if appt is None:
            raise HTTPException(status_code=404, detail="Appointment not found")
        if appt.status != "booked":
            raise HTTPException(
                status_code=400,
                detail="Only booked appointments can be rescheduled",
            )
        svc = appt.service
        if svc is None:
            raise HTTPException(status_code=400, detail="Appointment has no service")
        slots = list_open_slots(
            session,
            svc.slug,
            date_from=date_from,
            date_to=date_to,
            exclude_appointment_id=appt.appointment_id,
            limit=64,
        )
        return {
            "appointment_id": appt.appointment_id,
            "service_slug": svc.slug,
            "slots": slots,
        }


@router.post("/appointments/{appointment_id}/reschedule")
def reschedule_appointment(
    appointment_id: str,
    body: RescheduleBody,
    _claims: dict = Depends(require_owner_ready),
):
    with session_scope() as session:
        result = reschedule_appointment_as_owner(
            session, appointment_id, body.start_iso
        )
    if result.startswith("[error]"):
        raise HTTPException(status_code=400, detail=result.removeprefix("[error]").strip())
    return {"ok": True, "detail": result}


@router.get("/tickets")
def list_tickets(
    status: str | None = None,
    _claims: dict = Depends(require_owner_ready),
):
    with session_scope() as session:
        q = select(Ticket)
        if status:
            q = q.where(Ticket.status == status.strip())
        q = q.order_by(Ticket.respond_by.asc()).limit(200)
        rows = list(session.scalars(q).all())
        latest = _latest_notes_by_ticket(session, [t.ticket_id for t in rows])
        return {
            "tickets": [
                _ticket_dict(t, latest_note=latest.get(t.ticket_id, ""))
                for t in rows
            ]
        }


@router.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: str, _claims: dict = Depends(require_owner_ready)):
    with session_scope() as session:
        t = session.scalars(
            select(Ticket).where(Ticket.ticket_id == ticket_id.strip())
        ).first()
        if t is None:
            raise HTTPException(status_code=404, detail="Ticket not found")
        activities = list_ticket_activities(session, t.ticket_id)
        data = _ticket_dict(t)
        data["activities"] = [_activity_dict(a) for a in activities]
        data["phone_outcomes"] = list(PHONE_OUTCOMES)
        return data


@router.post("/tickets/{ticket_id}/notes")
def post_ticket_note(
    ticket_id: str,
    body: TicketNoteBody,
    claims: dict = Depends(require_owner_ready),
):
    with session_scope() as session:
        result = add_ticket_note(
            session,
            ticket_id,
            body.body,
            created_by=_owner_username(claims),
        )
        if isinstance(result, str):
            raise HTTPException(
                status_code=400, detail=result.removeprefix("[error]").strip()
            )
        return {"ok": True, "activity": _activity_dict(result)}


@router.post("/tickets/{ticket_id}/phone-log")
def post_ticket_phone_log(
    ticket_id: str,
    body: TicketPhoneLogBody,
    claims: dict = Depends(require_owner_ready),
):
    with session_scope() as session:
        result = add_ticket_phone_log(
            session,
            ticket_id,
            phone_outcome=body.phone_outcome,
            body=body.body,
            created_by=_owner_username(claims),
        )
        if isinstance(result, str):
            raise HTTPException(
                status_code=400, detail=result.removeprefix("[error]").strip()
            )
        t = session.scalars(
            select(Ticket).where(Ticket.ticket_id == ticket_id.strip())
        ).first()
        return {
            "ok": True,
            "activity": _activity_dict(result),
            "ticket": _ticket_dict(t) if t else None,
        }


@router.post("/tickets/{ticket_id}/reply")
def post_ticket_reply(
    ticket_id: str,
    body: TicketReplyBody,
    claims: dict = Depends(require_owner_ready),
):
    with session_scope() as session:
        result = send_ticket_email_reply(
            session,
            ticket_id,
            reply_body=body.body,
            created_by=_owner_username(claims),
        )
        if isinstance(result, str):
            raise HTTPException(
                status_code=400, detail=result.removeprefix("[error]").strip()
            )
        t = session.scalars(
            select(Ticket).where(Ticket.ticket_id == ticket_id.strip())
        ).first()
        return {
            "ok": True,
            "activity": _activity_dict(result),
            "ticket": _ticket_dict(t) if t else None,
        }


@router.patch("/tickets/{ticket_id}")
def patch_ticket(
    ticket_id: str,
    body: TicketPatchBody,
    _claims: dict = Depends(require_owner_ready),
):
    with session_scope() as session:
        t = session.scalars(
            select(Ticket).where(Ticket.ticket_id == ticket_id.strip())
        ).first()
        if t is None:
            raise HTTPException(status_code=404, detail="Ticket not found")
        t.status = body.status
        session.flush()
        return _ticket_dict(t)
