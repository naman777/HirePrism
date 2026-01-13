from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from src.agent.nodes import (
    executor_node,
    planner_node,
    sql_generator_node,
    synthesizer_node,
    validator_node,
)

log = logging.getLogger(__name__)


class AgentState(TypedDict, total=False):
    question: str
    sub_questions: list[str]
    generated_sqls: list[str]
    results: list[dict]
    answer: str
    sql_trace: list[str]
    routing: str       # set by validator: "replan" | "synthesize"
    replanned: bool    # True after the first replan — prevents infinite loops
    error: str | None


@dataclass
class AgentResult:
    question: str
    answer: str
    sub_questions: list[str] = field(default_factory=list)
    sql_trace: list[str] = field(default_factory=list)
    results: list[dict] = field(default_factory=list)
    replanned: bool = False
    success: bool = True
    error: str | None = None


def _route_after_validation(state: AgentState) -> str:
    """Routing function: reads the 'routing' key set by validator_node."""
    return state.get("routing", "synthesize")


def _build_graph() -> Any:
    builder = StateGraph(AgentState)

    builder.add_node("planner", planner_node)
    builder.add_node("sql_generator", sql_generator_node)
    builder.add_node("executor", executor_node)
    builder.add_node("validator", validator_node)
    builder.add_node("synthesizer", synthesizer_node)

    builder.set_entry_point("planner")
    builder.add_edge("planner", "sql_generator")
    builder.add_edge("sql_generator", "executor")
    builder.add_edge("executor", "validator")
    builder.add_conditional_edges(
        "validator",
        _route_after_validation,
        {"replan": "planner", "synthesize": "synthesizer"},
    )
    builder.add_edge("synthesizer", END)

    return builder.compile()


# Module-level compiled graph — built once on import
_graph = _build_graph()


def run(question: str) -> AgentResult:
    """Run the full agent pipeline for a user question.

    Returns an AgentResult with the answer, SQL trace, and sub-questions.
    Safe to call from Streamlit — catches all exceptions and returns an error result.
    """
    log.info("Agent question: %s", question)
    initial_state: AgentState = {
        "question": question,
        "sub_questions": [],
        "generated_sqls": [],
        "results": [],
        "answer": "",
        "sql_trace": [],
        "routing": "synthesize",
        "replanned": False,
        "error": None,
    }
    try:
        final_state = _graph.invoke(initial_state)
        return AgentResult(
            question=question,
            answer=final_state.get("answer", "No answer generated."),
            sub_questions=final_state.get("sub_questions", []),
            sql_trace=final_state.get("sql_trace", []),
            results=final_state.get("results", []),
            replanned=final_state.get("replanned", False),
            success=True,
        )
    except Exception as exc:
        log.error("Agent error: %s", exc, exc_info=True)
        return AgentResult(
            question=question,
            answer="",
            success=False,
            error=str(exc),
        )
