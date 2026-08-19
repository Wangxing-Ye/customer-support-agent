"""Text-to-speech providers: OpenAI or ElevenLabs."""
from __future__ import annotations

import logging

import requests
from openai import OpenAI

from backend.config import (
    ELEVENLABS_API_KEY,
    ELEVENLABS_TTS_MODEL,
    ELEVENLABS_TTS_VOICE_ID,
    OPENAI_TTS_MODEL,
    OPENAI_TTS_VOICE_ID,
    TTS_PROVIDER,
)

logger = logging.getLogger(__name__)


def resolve_tts_provider() -> str:
    p = (TTS_PROVIDER or "openai").strip().lower()
    return "elevenlabs" if p == "elevenlabs" else "openai"


def synthesize_speech_bytes(text: str) -> bytes:
    """Return mp3 bytes for assistant speech."""
    provider = resolve_tts_provider()
    if provider == "elevenlabs":
        return _elevenlabs_tts(text)
    return _openai_tts(text)


def _openai_tts(text: str) -> bytes:
    import os

    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")
    client = OpenAI(api_key=api_key)
    speech = client.audio.speech.create(
        model=OPENAI_TTS_MODEL,
        voice=OPENAI_TTS_VOICE_ID,
        input=text,
        response_format="mp3",
    )
    return speech.read()


def _elevenlabs_tts(text: str) -> bytes:
    if not ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY is not set.")
    voice_id = (ELEVENLABS_TTS_VOICE_ID or "").strip()
    if not voice_id:
        raise RuntimeError("ELEVENLABS_TTS_VOICE_ID is not set.")
    model_id = (ELEVENLABS_TTS_MODEL or "eleven_multilingual_v2").strip()
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    resp = requests.post(
        url,
        headers={
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        json={"text": text, "model_id": model_id},
        params={"output_format": "mp3_44100_128"},
        timeout=120,
    )
    if resp.status_code >= 400:
        detail = (resp.text or "").strip()[:500]
        logger.warning("ElevenLabs TTS failed status=%s detail=%s", resp.status_code, detail)
        raise RuntimeError(f"ElevenLabs TTS failed ({resp.status_code}): {detail or 'unknown error'}")
    return resp.content
