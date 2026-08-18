"""FastAPI entrypoint: auth, chat (sync + SSE), voice, TTS."""
from __future__ import annotations

import html
import json
import logging
import os
import uuid
from io import BytesIO

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from openai import OpenAI
from pydantic import BaseModel, field_validator

from sqlalchemy import select

from backend.auth import create_access_token, verify_jwt
from backend.config import (
    CORS_ORIGINS,
    FIRM_NAME,
    MAX_MESSAGE_WORDS,
    TTS_MODEL,
    TTS_VOICE,
    WHISPER_MODEL,
)
from backend.db import Base, engine, ensure_schema, session_scope
from backend.models import Appointment, AvailabilityRule, EmailLog, Service, Ticket  # noqa: F401
from backend.services.scheduling import finalize_paid_hold, seed_defaults
from backend.services.stripe_checkout import live_checkout_url, parse_webhook_event

logger = logging.getLogger(__name__)

app = FastAPI(title=f"{FIRM_NAME} Client Services Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "Authorization"],
)


def _graph():
    from backend.agent.graph import get_graph

    return get_graph()


def _thread_config(thread_id: str | None) -> dict:
    tid = (thread_id or "").strip() or str(uuid.uuid4())
    return {"configurable": {"thread_id": tid}}, tid


def _content_to_text(content) -> str:
    """Normalize LLM message content (str or Claude/OpenAI content blocks) to plain text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
                continue
            if isinstance(block, dict):
                btype = (block.get("type") or "").strip().lower()
                if btype in ("text", "") or "text" in block:
                    parts.append(str(block.get("text") or ""))
                continue
            text = getattr(block, "text", None)
            if text is not None:
                parts.append(str(text))
                continue
            btype = str(getattr(block, "type", "") or "").lower()
            if btype == "text":
                parts.append(str(getattr(block, "text", "") or ""))
        return "".join(parts)
    return str(content)


def _final_text(result: dict) -> str:
    last = result["messages"][-1]
    text = _content_to_text(getattr(last, "content", None)).strip()
    return text if text else "I couldn’t generate a reply. Please try again."


@app.on_event("startup")
def on_startup() -> None:
    try:
        Base.metadata.create_all(bind=engine)
        ensure_schema()
        with session_scope() as session:
            seed_defaults(session)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Database init failed (%s). Start Postgres with "
            "`docker compose up -d` and check DATABASE_URL. Error: %s",
            type(exc).__name__,
            exc,
        )
        raise
    try:
        _graph()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Graph warm-up deferred: %s", exc)
    logger.info("Startup complete for %s", FIRM_NAME)


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None

    @field_validator("message")
    @classmethod
    def strip_and_limit_words(cls, v: str) -> str:
        text = v.strip()
        if not text:
            raise ValueError("Message cannot be empty")
        words = [w for w in text.split() if w]
        if len(words) > MAX_MESSAGE_WORDS:
            raise ValueError(f"Message must be at most {MAX_MESSAGE_WORDS} words")
        return text


class TtsRequest(BaseModel):
    message: str

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        text = v.strip()
        if not text:
            raise ValueError("Message cannot be empty")
        if len(text) > 4000:
            raise ValueError("Message is too long for speech synthesis")
        return text


@app.post("/auth/token")
async def issue_token():
    """Issue a short-lived JWT for the chat UI (protect JWT_SECRET in production)."""
    return {"access_token": create_access_token(), "token_type": "bearer"}


def _pay_html(title: str, body: str, extra_script: str = "") -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{title}</title></head><body>"
        f"<h1>{title}</h1><p>{body}</p>"
        f"{extra_script}"
        "</body></html>"
    )


@app.get("/pay/success")
async def pay_success(appointment_id: str = ""):
    extra = (
        f" Appointment ID: {html.escape(appointment_id)}." if appointment_id else ""
    )
    aid_js = json.dumps(appointment_id or "")
    script = (
        "<script>(function(){"
        f"var id={aid_js};"
        "try{if(window.opener&&!window.opener.closed){"
        "window.opener.postMessage({type:'pst-stripe-paid',appointment_id:id},'*');"
        "}}catch(e){}"
        "})();</script>"
    )
    return HTMLResponse(
        _pay_html(
            "Payment received",
            "Payment is confirmed. You can close this tab and return to chat. "
            "A confirmation email with the cancellation code has been sent."
            + extra,
            extra_script=script,
        )
    )


@app.get("/pay/cancel")
async def pay_cancel(appointment_id: str = ""):
    extra = (
        f" Appointment ID: {html.escape(appointment_id)}." if appointment_id else ""
    )
    return HTMLResponse(
        _pay_html(
            "Checkout cancelled",
            "The slot is held only until the payment deadline. Close this tab and return to chat to pay or pick another time."
            + extra,
        )
    )


@app.get("/pay/status")
async def pay_status(appointment_id: str = ""):
    """Public hold status for the chat widget (no cancel code)."""
    aid = (appointment_id or "").strip()
    if not aid:
        raise HTTPException(status_code=400, detail="appointment_id is required")
    with session_scope() as session:
        appt = session.scalar(
            select(Appointment).where(Appointment.appointment_id == aid)
        )
        if not appt:
            raise HTTPException(status_code=404, detail="Appointment not found")
        checkout_url = ""
        sid = (getattr(appt, "stripe_checkout_session_id", None) or "").strip()
        if appt.status == "pending_payment" and sid:
            try:
                checkout_url = live_checkout_url(sid)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not load Stripe checkout URL: %s", type(exc).__name__)
        return {
            "appointment_id": appt.appointment_id,
            "status": appt.status,
            "checkout_url": checkout_url,
        }


@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    try:
        event = parse_webhook_event(payload, signature)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Stripe webhook rejected: %s", type(exc).__name__)
        raise HTTPException(status_code=400, detail="Invalid Stripe signature") from exc

    etype = getattr(event, "type", None) or event["type"]
    raw = event["data"]["object"] if isinstance(event, dict) else event.data.object
    data = raw.to_dict() if hasattr(raw, "to_dict") else dict(raw)

    appointment_id = (
        (data.get("metadata") or {}).get("appointment_id")
        or data.get("client_reference_id")
        or ""
    )
    appointment_id = str(appointment_id).strip()

    if etype in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        if (data.get("payment_status") or "") != "paid":
            return {"received": True, "ignored": "not_paid"}
        if not appointment_id:
            logger.warning("Stripe paid session missing appointment_id")
            return {"received": True, "ignored": "no_appointment"}
        with session_scope() as session:
            appt = session.scalar(
                select(Appointment).where(Appointment.appointment_id == appointment_id)
            )
            if not appt:
                logger.warning("Stripe webhook: unknown appointment %s", appointment_id)
                return {"received": True, "ignored": "unknown_appointment"}
            result = finalize_paid_hold(session, appt)
            logger.info("Stripe payment finalized: %s", result[:200])
        return {"received": True}

    if etype in ("checkout.session.expired", "checkout.session.async_payment_failed"):
        if appointment_id:
            with session_scope() as session:
                appt = session.scalar(
                    select(Appointment).where(Appointment.appointment_id == appointment_id)
                )
                if appt and appt.status == "pending_payment":
                    appt.status = "expired"
                    session.flush()
        return {"received": True}

    return {"received": True}


@app.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    _: None = Depends(verify_jwt),
):
    """Transcribe uploaded audio with OpenAI Speech-to-Text (Whisper)."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not set.")

    raw = await file.read()
    if not raw or len(raw) < 256:
        raise HTTPException(status_code=400, detail="Audio file is empty or too short.")

    filename = file.filename or "recording.webm"
    suffix = os.path.splitext(filename)[1].lower()
    if suffix not in (
        ".webm",
        ".mp3",
        ".wav",
        ".m4a",
        ".mp4",
        ".mpeg",
        ".mpga",
        ".oga",
        ".ogg",
    ):
        suffix = ".webm"

    buf = BytesIO(raw)
    buf.seek(0)
    buf.name = f"audio{suffix}"

    try:
        client = OpenAI(api_key=api_key)
        tr = client.audio.transcriptions.create(model=WHISPER_MODEL, file=buf)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Transcription failed: {exc}",
        ) from exc

    text = (tr.text or "").strip()
    return {"text": text}


@app.post("/chat")
async def chat(req: ChatRequest, _: None = Depends(verify_jwt)):
    config, tid = _thread_config(req.thread_id)
    result = _graph().invoke(
        {"messages": [HumanMessage(content=req.message)]},
        config=config,
    )
    return {"response": _final_text(result), "thread_id": tid}


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest, _: None = Depends(verify_jwt)):
    """SSE stream of assistant tokens (+ optional status events)."""
    config, tid = _thread_config(req.thread_id)
    graph = _graph()

    def event_gen():
        yield f"event: meta\ndata: {json.dumps({'thread_id': tid})}\n\n"
        assembled = ""
        try:
            for item in graph.stream(
                {"messages": [HumanMessage(content=req.message)]},
                config=config,
                stream_mode="messages",
            ):
                # LangGraph may yield (message, metadata) tuples
                if isinstance(item, tuple) and len(item) >= 1:
                    message = item[0]
                    meta = item[1] if len(item) > 1 and isinstance(item[1], dict) else {}
                else:
                    message = item
                    meta = {}

                node = meta.get("langgraph_node") or meta.get("checkpoint_ns") or ""
                if isinstance(message, (AIMessageChunk, AIMessage)):
                    # Skip pure tool-call chunks without text
                    content = _content_to_text(message.content)
                    text = content if content else ""
                    if text:
                        assembled += text
                        yield f"event: token\ndata: {json.dumps({'text': text})}\n\n"
                    elif node == "tools" or getattr(message, "tool_calls", None):
                        yield f"event: status\ndata: {json.dumps({'status': 'working'})}\n\n"
            if not assembled.strip():
                # Fallback: read final state
                snap = graph.get_state(config)
                values = snap.values if snap else {}
                msgs = values.get("messages") or []
                if msgs:
                    assembled = _content_to_text(getattr(msgs[-1], "content", None))
                if assembled.strip():
                    yield f"event: token\ndata: {json.dumps({'text': assembled})}\n\n"
                else:
                    yield (
                        "event: token\ndata: "
                        + json.dumps(
                            {
                                "text": "I couldn’t generate a reply. Please try again."
                            }
                        )
                        + "\n\n"
                    )
            yield f"event: done\ndata: {json.dumps({'thread_id': tid})}\n\n"
        except Exception as exc:  # noqa: BLE001
            logger.exception("stream failed")
            yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/tts")
async def synthesize_speech(req: TtsRequest, _: None = Depends(verify_jwt)):
    """Turn assistant text into speech audio bytes."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not set.")

    text = req.message.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    try:
        client = OpenAI(api_key=api_key)
        speech = client.audio.speech.create(
            model=TTS_MODEL,
            voice=TTS_VOICE,
            input=text,
            response_format="mp3",
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"TTS failed: {exc}") from exc

    audio_bytes = speech.read()
    return StreamingResponse(BytesIO(audio_bytes), media_type="audio/mpeg")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.app:app", host="0.0.0.0", port=8000, reload=True)
