"""FastAPI entrypoint: auth, chat (sync + SSE), voice, TTS."""
from __future__ import annotations

import json
import logging
import os
import uuid
from io import BytesIO

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from openai import OpenAI
from pydantic import BaseModel, field_validator

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
from backend.services.scheduling import seed_defaults

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


def _final_text(result: dict) -> str:
    last = result["messages"][-1]
    text = getattr(last, "content", None) or ""
    return text if str(text).strip() else "I couldn’t generate a reply. Please try again."


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
                    content = message.content
                    if isinstance(content, list):
                        parts = []
                        for p in content:
                            if isinstance(p, dict) and p.get("type") == "text":
                                parts.append(p.get("text") or "")
                            elif isinstance(p, str):
                                parts.append(p)
                        content = "".join(parts)
                    text = content if isinstance(content, str) else ""
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
                    assembled = str(getattr(msgs[-1], "content", "") or "")
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
