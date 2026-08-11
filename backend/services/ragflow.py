"""RAGFlow retrieval helpers."""
from __future__ import annotations

from typing import List

import requests

from backend.config import (
    KNOWLEDGE_BASE_ID,
    RAG_BRAND_PREFIX,
    RAG_BRAND_RETRY_SKIP_SUBSTRINGS,
    RAGFLOW_API_KEY,
    RAGFLOW_KEYWORD,
    RAGFLOW_RETRIEVAL_LOWERCASE,
    RAGFLOW_SIMILARITY_THRESHOLD,
    RAGFLOW_URL,
)


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
