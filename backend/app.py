from fastapi import FastAPI, Depends, HTTPException, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.responses import StreamingResponse
from io import BytesIO
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, field_validator
from typing import TypedDict, Annotated, List
import operator
import requests
import os
import time
from datetime import datetime, timezone
import jwt
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

MAX_MESSAGE_WORDS = 50
JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))

_default_origins = (
    "http://127.0.0.1:3000,http://localhost:3000,"
    "http://127.0.0.1:4173,http://localhost:4173,"
    "http://127.0.0.1:5500,http://localhost:5500,"
    "http://127.0.0.1:8080,http://localhost:8080,"
    "http://127.0.0.1:8000,http://localhost:8000"
)
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", _default_origins).split(",")
    if o.strip()
]

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "Authorization"],
)

# Default includes port 9222 per RAGFlow docs; override via env, e.g. http://127.0.0.1:9222
RAGFLOW_URL = os.getenv("RAGFLOW_URL", "http://127.0.0.1:9222").rstrip("/")
RAGFLOW_API_KEY = os.getenv("RAGFLOW_API_KEY")
# Dataset / knowledge-base UUID(s) from RAGFlow; comma-separated for multiple datasets
KNOWLEDGE_BASE_ID = os.getenv("KNOWLEDGE_BASE_ID")
RAGFLOW_SIMILARITY_THRESHOLD = float(os.getenv("RAGFLOW_SIMILARITY_THRESHOLD", "0.2"))
RAGFLOW_KEYWORD = os.getenv("RAGFLOW_KEYWORD", "true").lower() in ("1", "true", "yes")
# Lowercase + collapse whitespace for RAGFlow `question` only (chat message unchanged).
RAGFLOW_RETRIEVAL_LOWERCASE = os.getenv("RAGFLOW_RETRIEVAL_LOWERCASE", "true").lower() in (
    "1",
    "true",
    "yes",
)

# Branded-prefix retrieval retry: if the first RAG call returns empty, retry once with
# "{RAG_BRAND_PREFIX} {user question}". Empty RAG_BRAND_PREFIX disables this retry.
RAG_BRAND_PREFIX = os.getenv("RAG_BRAND_PREFIX", "ABC").strip()
_raw_brand_skip = os.getenv("RAG_BRAND_RETRY_SKIP_SUBSTRINGS")
if _raw_brand_skip is None:
    _raw_brand_skip = ""
RAG_BRAND_RETRY_SKIP_SUBSTRINGS = [
    s.strip().lower() for s in _raw_brand_skip.split(",") if s.strip()
]


def should_skip_branded_prefix_retry(question: str) -> bool:
    """Skip branded-prefix retry if the user already named the brand or a configured entity."""
    q_lower = str(question).lower()
    bp = RAG_BRAND_PREFIX.lower()
    if bp and bp in q_lower:
        return True
    for sub in RAG_BRAND_RETRY_SKIP_SUBSTRINGS:
        if sub in q_lower:
            return True
    return False


OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0)

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-1")
TTS_MODEL = os.getenv("TTS_MODEL", "tts-1")
TTS_VOICE = os.getenv("TTS_VOICE", "alloy")

AGENT_SYSTEM_PROMPT = """
You are a customer support assistant of ABC company.

Grounding rules:
- For factual questions, policy questions, project details, or company-specific info, use the provided RAG context as the primary source of truth.
- If the RAG context is empty or clearly unrelated, say you could not find this in the knowledge base and then provide a best-effort general answer.
- Do not claim information came from the knowledge base unless it is present in the provided context.

Style rules:
- Answer directly; end when the answer is complete. Do not add filler closings.
- Do not use phrases like "If you want", "If you'd like", "Let me know if", "Feel free to", "I'm happy to", or similar offers to continue — unless the user explicitly asked for options or next steps.
- Do not volunteer summaries, extra tutorials, or "I can also help with..." unless the user asked.
"""

security = HTTPBearer()


def create_access_token() -> str:
    if not JWT_SECRET:
        raise HTTPException(
            status_code=500,
            detail="JWT_SECRET is not set. Add a strong secret to .env.",
        )
    exp = int(time.time()) + JWT_EXPIRE_MINUTES * 60
    payload = {"sub": "chat", "exp": exp}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_jwt(credentials: HTTPAuthorizationCredentials = Depends(security)) -> None:
    if not JWT_SECRET:
        raise HTTPException(
            status_code=500,
            detail="JWT_SECRET is not set. Add a strong secret to .env.",
        )
    token = credentials.credentials
    try:
        jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


class ChatRequest(BaseModel):
    message: str

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


class AgentState(TypedDict):
    messages: Annotated[List, operator.add]


# ====================== TOOLS ======================
def _dataset_ids_from_env() -> List[str]:
    if not KNOWLEDGE_BASE_ID:
        return []
    return [x.strip() for x in KNOWLEDGE_BASE_ID.split(",") if x.strip()]


def _retrieval_question_text(query: str) -> str:
    """Normalize text sent to RAGFlow only; user-facing message stays unchanged."""
    text = (query or "").strip()
    if not text:
        return ""
    if not RAGFLOW_RETRIEVAL_LOWERCASE:
        return text
    return " ".join(text.split()).lower()


def _chunks_from_ragflow_response(body: dict) -> List[dict]:
    """RAGFlow wraps payloads as {code, data: {chunks: [...]}}; older clients used top-level chunks."""
    if not isinstance(body, dict):
        return []
    data = body.get("data")
    if isinstance(data, dict) and data.get("chunks") is not None:
        return data.get("chunks") or []
    return body.get("chunks") or []


def ragflow_retrieve(query: str):
    """Search the knowledge base for facts relevant to the user's question."""
    dataset_ids = _dataset_ids_from_env()
    if not dataset_ids:
        return "[error] KNOWLEDGE_BASE_ID is not set. Add your RAGFlow dataset id(s) to .env."

    if not RAGFLOW_API_KEY:
        return "[error] RAGFLOW_API_KEY is not set."

    question_for_api = _retrieval_question_text(str(query))
    if not question_for_api:
        return ""

    headers = {"Authorization": f"Bearer {RAGFLOW_API_KEY}", "Content-Type": "application/json"}
    # Official HTTP API: dataset_ids (list). Some builds accept kb_id; dataset_ids matches UI retrieval.
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

    chunks = _chunks_from_ragflow_response(body)
    texts = []
    for c in chunks:
        if isinstance(c, dict) and c.get("content"):
            texts.append(str(c["content"]))
    return "\n\n".join(texts) if texts else ""


def get_product():
    """Return the current product and service catalog with prices."""
    return (
        "Products: Enterprise Suite $12,999/year, Team License $499/seat, "
        "Premium Support $199/mo"
    )


def place_order(items: list, customer: str):
    """Place an order for the given products or services for the named customer."""
    now_utc = datetime.now(timezone.utc)
    order_number = f"ORD-{now_utc.strftime('%Y%m%d-%H%M%S')}"
    order_date = now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
    return (
        f"✅ Order placed! Order Number: {order_number} | Date: {order_date} | "
        f"Items: {items} for {customer}"
    )


def create_ticket(title: str, desc: str):
    """Create a support ticket with a short title and description."""
    return f"✅ Ticket created: {title}"


tools = [ragflow_retrieve, get_product, place_order, create_ticket]
llm_with_tools = llm.bind_tools(tools)


def agent_node(state: AgentState):
    messages = [SystemMessage(content=AGENT_SYSTEM_PROMPT), *state["messages"]]

    # Prefetch RAG context once per user turn so the model is grounded in KB data.
    if state["messages"] and isinstance(state["messages"][-1], HumanMessage):
        question = state["messages"][-1].content
        rag_context = ragflow_retrieve(question)

        rag_text = str(rag_context or "").strip()
        is_error = rag_text.startswith("[error]")
        is_empty = (not rag_text) or (rag_text == "[empty]")

        # Retry once with a branded-prefix query when retrieval is empty (see RAG_BRAND_PREFIX).
        if (
            is_empty
            and not is_error
            and RAG_BRAND_PREFIX
            and not should_skip_branded_prefix_retry(question)
        ):
            fallback_query = f"{RAG_BRAND_PREFIX} {question}"
            rag_context_2 = ragflow_retrieve(fallback_query)
            rag_text_2 = str(rag_context_2 or "").strip()
            is_error_2 = rag_text_2.startswith("[error]")
            is_empty_2 = (not rag_text_2) or (rag_text_2 == "[empty]")
            if not is_error_2 and not is_empty_2:
                rag_context = rag_context_2

        messages.insert(
            1,
            SystemMessage(
                content=(
                    "RAG context from knowledge base:\n"
                    f"{rag_context if rag_context else '[empty]'}"
                )
            ),
        )

    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


workflow = StateGraph(AgentState)
workflow.add_node("agent", agent_node)
workflow.add_node("tools", ToolNode(tools))
workflow.set_entry_point("agent")
workflow.add_conditional_edges(
    "agent",
    tools_condition,
    {"tools": "tools", "__end__": END},
)
workflow.add_edge("tools", "agent")
graph = workflow.compile()


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
    if suffix not in (".webm", ".mp3", ".wav", ".m4a", ".mp4", ".mpeg", ".mpga", ".oga", ".ogg"):
        suffix = ".webm"

    buf = BytesIO(raw)
    buf.seek(0)
    buf.name = f"audio{suffix}"

    try:
        client = OpenAI(api_key=api_key)
        tr = client.audio.transcriptions.create(
            model=WHISPER_MODEL,
            file=buf,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Transcription failed: {exc}",
        ) from exc

    text = (tr.text or "").strip()
    return {"text": text}


@app.post("/chat")
async def chat(req: ChatRequest, _: None = Depends(verify_jwt)):
    user_message = req.message
    result = graph.invoke({"messages": [HumanMessage(content=user_message)]})
    last = result["messages"][-1]
    text = getattr(last, "content", None) or ""
    return {"response": text if str(text).strip() else "I couldn’t generate a reply. Please try again."}


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

    uvicorn.run(app, host="0.0.0.0", port=8000)
