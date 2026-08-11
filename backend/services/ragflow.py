"""Knowledge retrieval: local Markdown and/or RAGFlow."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List

import requests

from backend.config import (
    KB_LOCAL_PATH,
    KB_PROVIDER,
    KNOWLEDGE_BASE_ID,
    RAG_BRAND_PREFIX,
    RAG_BRAND_RETRY_SKIP_SUBSTRINGS,
    RAGFLOW_API_KEY,
    RAGFLOW_KEYWORD,
    RAGFLOW_RETRIEVAL_LOWERCASE,
    RAGFLOW_SIMILARITY_THRESHOLD,
    RAGFLOW_URL,
)

logger = logging.getLogger(__name__)


def dataset_ids_from_env() -> List[str]:
    if not KNOWLEDGE_BASE_ID:
        return []
    return [x.strip() for x in KNOWLEDGE_BASE_ID.split(",") if x.strip()]


def retrieval_question_text(query: str) -> str:
    text = (query or "").strip()
    if not text:
        return ""
    if not RAGFLOW_RETRIEVAL_LOWERCASE:
        return text
    return " ".join(text.split()).lower()


def chunks_from_ragflow_response(body: dict) -> List[dict]:
    if not isinstance(body, dict):
        return []
    data = body.get("data")
    if isinstance(data, dict) and data.get("chunks") is not None:
        return data.get("chunks") or []
    return body.get("chunks") or []


def should_skip_branded_prefix_retry(question: str) -> bool:
    q_lower = str(question).lower()
    bp = RAG_BRAND_PREFIX.lower()
    if bp and bp in q_lower:
        return True
    for sub in RAG_BRAND_RETRY_SKIP_SUBSTRINGS:
        if sub in q_lower:
            return True
    return False


def ragflow_is_configured() -> bool:
    return bool(RAGFLOW_API_KEY and dataset_ids_from_env())


def resolve_kb_provider() -> str:
    if KB_PROVIDER == "local":
        return "local"
    if KB_PROVIDER == "ragflow":
        return "ragflow"
    return "ragflow" if ragflow_is_configured() else "local"


def local_kb_path() -> Path:
    raw = Path(KB_LOCAL_PATH)
    if raw.is_file():
        return raw
    return Path(__file__).resolve().parents[2] / KB_LOCAL_PATH


def local_kb_text() -> str:
    path = local_kb_path()
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        return f"[error] Could not read local knowledge file {path}: {exc}"
    return text or "[empty]"


def _rag_unusable(text: str) -> bool:
    t = (text or "").strip()
    if not t or t == "[empty]":
        return True
    if t.startswith("[error]"):
        return True
    if t.startswith("Could not retrieve knowledge"):
        return True
    return False


def retrieve(query: str) -> str:
    """Firm knowledge for the agent: local Markdown, RAGFlow, or auto with fallback."""
    provider = resolve_kb_provider()
    if provider == "local":
        return local_kb_text()

    text = retrieve_with_brand_fallback(query)
    if _rag_unusable(text):
        local = local_kb_text()
        if not _rag_unusable(local):
            logger.info("RAGFlow returned no usable context; falling back to local KB")
            return local
    return text


def ragflow_retrieve(query: str) -> str:
    """Search the knowledge base for facts relevant to the user's question."""
    dataset_ids = dataset_ids_from_env()
    if not dataset_ids:
        return "[error] KNOWLEDGE_BASE_ID is not set. Add your RAGFlow dataset id(s) to .env."

    if not RAGFLOW_API_KEY:
        return "[error] RAGFLOW_API_KEY is not set."

    question_for_api = retrieval_question_text(str(query))
    if not question_for_api:
        return ""

    headers = {
        "Authorization": f"Bearer {RAGFLOW_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "question": question_for_api,
        "dataset_ids": dataset_ids,
        "top_k": 6,
        "similarity_threshold": RAGFLOW_SIMILARITY_THRESHOLD,
        "keyword": RAGFLOW_KEYWORD,
    }
    url = f"{RAGFLOW_URL}/api/v1/retrieval"
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
    except requests.RequestException as exc:
        return f"[error] RAGFlow request failed: {exc}"

    try:
        body = resp.json()
    except ValueError:
        return "Could not retrieve knowledge (invalid JSON response)."

    code = body.get("code")
    if resp.status_code != 200 or (code is not None and code != 0):
        msg = body.get("message") or body.get("msg") or resp.text or resp.reason
        return f"Could not retrieve knowledge ({resp.status_code}, code={code}): {msg}"

    chunks = chunks_from_ragflow_response(body)
    texts = []
    for c in chunks:
        if isinstance(c, dict) and c.get("content"):
            texts.append(str(c["content"]))
    return "\n\n".join(texts) if texts else ""


def retrieve_with_brand_fallback(question: str) -> str:
    rag_context = ragflow_retrieve(question)
    rag_text = str(rag_context or "").strip()
    is_error = rag_text.startswith("[error]")
    is_empty = (not rag_text) or (rag_text == "[empty]")
    if (
        is_empty
        and not is_error
        and RAG_BRAND_PREFIX
        and not should_skip_branded_prefix_retry(question)
    ):
        rag_context_2 = ragflow_retrieve(f"{RAG_BRAND_PREFIX} {question}")
        rag_text_2 = str(rag_context_2 or "").strip()
        is_error_2 = rag_text_2.startswith("[error]")
        is_empty_2 = (not rag_text_2) or (rag_text_2 == "[empty]")
        if not is_error_2 and not is_empty_2:
            return rag_context_2
    return rag_context
