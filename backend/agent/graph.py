"""LangGraph agent graph with optional Postgres checkpointing."""
from __future__ import annotations

import logging
import operator
from typing import Annotated, List, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from backend.agent.prompts import build_system_prompt
from backend.agent.tools import TOOLS
from backend.config import (
    ANTHROPIC_MODEL,
    CHECKPOINT_DATABASE_URL,
    OPENAI_MODEL,
    resolve_llm_provider,
)
from backend.services.ragflow import retrieve

logger = logging.getLogger(__name__)

_graph = None


class AgentState(TypedDict):
    messages: Annotated[List, operator.add]


def build_chat_llm():
    """Chat LLM for the agent. Voice (Whisper/TTS) stays on OpenAI in app.py."""
    provider = resolve_llm_provider()
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        logger.info("Chat LLM: Anthropic model=%s", ANTHROPIC_MODEL)
        # Newer Claude models reject temperature (deprecated); omit it.
        return ChatAnthropic(model=ANTHROPIC_MODEL)
    from langchain_openai import ChatOpenAI

    logger.info("Chat LLM: OpenAI model=%s", OPENAI_MODEL)
    return ChatOpenAI(model=OPENAI_MODEL, temperature=0, reasoning_effort="none")


llm = build_chat_llm()
llm_with_tools = llm.bind_tools(TOOLS)


def agent_node(state: AgentState):
    messages = [SystemMessage(content=build_system_prompt()), *state["messages"]]

    if state["messages"] and isinstance(state["messages"][-1], HumanMessage):
        question = state["messages"][-1].content
        rag_context = retrieve(str(question))
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


def _build_checkpointer():
    if not CHECKPOINT_DATABASE_URL:
        from langgraph.checkpoint.memory import MemorySaver

        logger.info("Using MemorySaver (no CHECKPOINT_DATABASE_URL)")
        return MemorySaver()
    try:
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg_pool import ConnectionPool

        pool = ConnectionPool(
            conninfo=CHECKPOINT_DATABASE_URL,
            max_size=5,
            kwargs={"autocommit": True},
        )
        saver = PostgresSaver(pool)
        saver.setup()
        logger.info("Using PostgresSaver checkpointer")
        return saver
    except Exception as exc:  # noqa: BLE001
        logger.warning("Using MemorySaver (Postgres checkpointer unavailable): %s", exc)
        from langgraph.checkpoint.memory import MemorySaver

        return MemorySaver()


def compile_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", ToolNode(TOOLS))
    workflow.set_entry_point("agent")
    workflow.add_conditional_edges(
        "agent",
        tools_condition,
        {"tools": "tools", "__end__": END},
    )
    workflow.add_edge("tools", "agent")
    checkpointer = _build_checkpointer()
    return workflow.compile(checkpointer=checkpointer)


def get_graph():
    global _graph
    if _graph is None:
        _graph = compile_graph()
    return _graph
