"""Call the configured workflow model inside LangGraph nodes."""

from __future__ import annotations

from contextvars import ContextVar
import importlib.util
import json
import os
from pathlib import Path
import threading
import time
from typing import Callable

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from openai import APIConnectionError, InternalServerError, RateLimitError

from career_ops.web_search import tavily


CALL_TIMEOUT_SECONDS = 600
# High reasoning effort can spend the endpoint default (8192) on reasoning alone; Hermes retried up to this cap.
MAX_OUTPUT_TOKENS = 32768
MODEL_ATTEMPTS = 3
RETRYABLE = (APIConnectionError, InternalServerError, RateLimitError)  # APITimeoutError subclasses APIConnectionError
RESEARCH_LIMITS = {"web_search": 5, "web_extract": 1}
DEADLINE: ContextVar[float | None] = ContextVar("career_ops_model_deadline", default=None)


def remaining_seconds() -> float:
    """Fail before a model call once the owning task has spent its time budget."""
    deadline = DEADLINE.get()
    if deadline is None:
        return CALL_TIMEOUT_SECONDS
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("time_budget_exhausted")
    return min(CALL_TIMEOUT_SECONDS, remaining)


def chat_model() -> ChatOpenAI:
    """Build the single workflow model from project settings."""
    missing = [name for name in ("CAREER_OPS_MODEL", "CAREER_OPS_LLM_BASE_URL", "CAREER_OPS_LLM_API_KEY")
               if not os.environ.get(name)]
    if missing:
        raise RuntimeError("Model settings are missing: " + ", ".join(missing))
    return ChatOpenAI(
        model=os.environ["CAREER_OPS_MODEL"],
        base_url=os.environ["CAREER_OPS_LLM_BASE_URL"],
        api_key=os.environ["CAREER_OPS_LLM_API_KEY"],
        reasoning_effort=os.environ.get("CAREER_OPS_REASONING_EFFORT", "high"),
        max_tokens=MAX_OUTPUT_TOKENS,
        timeout=remaining_seconds(),
        max_retries=0,
    )


def invoke(prepare: Callable[[ChatOpenAI], Runnable], messages: list[BaseMessage], name: str) -> BaseMessage:
    """Retry transient endpoint failures, giving every attempt only the task time that is left."""
    for attempt in range(MODEL_ATTEMPTS):
        try:
            return prepare(chat_model()).invoke(messages, {"run_name": name})
        except RETRYABLE:
            if attempt == MODEL_ATTEMPTS - 1:
                raise


def complete_json(system: str, prompt: str, name: str = "model") -> str:
    """Run one tool-free JSON-mode model call and return its raw text."""
    return invoke(lambda model: model.bind(response_format={"type": "json_object"}),
                  [SystemMessage(system), HumanMessage(prompt)], name).text


def research_tools(record: Callable[[], None], usage: dict | None) -> list:
    """Expose bounded Tavily search and extraction; budget is enforced before dispatch."""
    counts = dict.fromkeys(RESEARCH_LIMITS, 0)
    lock = threading.Lock()

    def claim(name: str) -> bool:
        with lock:
            if counts[name] >= RESEARCH_LIMITS[name]:
                return False
            record()
            counts[name] += 1
            if usage is not None:
                usage["tool_calls"] = usage.get("tool_calls", 0) + 1
            return True

    budget_reached = json.dumps({"error": "Research budget reached. This call did NOT execute. "
                                          "Finish JSON using completed results; missing evidence remains unknown."})

    @tool
    def web_search(query: str) -> str:
        """Search the web and return result titles, URLs and snippets."""
        if not claim("web_search"):
            return budget_reached
        try:
            response = tavily("search", {"query": query, "max_results": 5})
        except Exception as error:
            return json.dumps({"error": f"{type(error).__name__}: {error}"})
        return json.dumps({"web": [{"title": item.get("title", ""), "url": item.get("url", ""),
                                    "description": item.get("content", "")}
                                   for item in response.get("results", [])]}, ensure_ascii=False)

    @tool
    def web_extract(urls: list[str], char_limit: int = 4000) -> str:
        """Read up to three web pages and return their text content."""
        if not claim("web_extract"):
            return budget_reached
        urls = urls[:3]
        try:
            response = tavily("extract", {"urls": urls})
        except Exception as error:
            return json.dumps({"results": [{"url": url, "content": "", "error": str(error)} for url in urls]})
        results = [{"url": item.get("url", ""), "content": (item.get("raw_content") or "")[:4000]}
                   for item in response.get("results", [])]
        results += [{"url": item.get("url", ""), "content": "", "error": item.get("error", "extraction failed")}
                    for item in response.get("failed_results", [])]
        return json.dumps({"results": results}, ensure_ascii=False)

    return [web_search, web_extract]


def research(system: str, prompt: str, record: Callable[[], None], usage: dict | None = None,
             max_iterations: int = 12) -> tuple[str, list[BaseMessage]]:
    """Run the research tool loop as a LangGraph subgraph and return final text plus messages."""
    tools = research_tools(record, usage)

    def agent(state: MessagesState) -> dict:
        return {"messages": [invoke(lambda model: model.bind_tools(tools), state["messages"], "research")]}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")
    result = graph.compile(name="research").invoke(
        {"messages": [SystemMessage(system), HumanMessage(prompt)]},
        {"recursion_limit": 2 * max_iterations + 1},
    )
    return result["messages"][-1].text, result["messages"]


def load_stub(variable: str) -> Callable[[str, dict], dict] | None:
    """Load an offline test double's run(phase, payload) from a file named by the environment."""
    path = os.environ.get(variable)
    if not path:
        return None
    spec = importlib.util.spec_from_file_location(f"career_ops_stub_{Path(path).stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run
