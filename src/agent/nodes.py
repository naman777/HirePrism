from __future__ import annotations

import json
import logging
import os
from typing import Any

import anthropic

from src.agent.prompts import (
    PLANNER_SYSTEM,
    REPLAN_SUFFIX,
    SQL_GENERATOR_SYSTEM,
    SYNTHESIZER_SYSTEM,
)
from src.agent.tools import execute_sql

log = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
MAX_SUB_QUESTIONS = 3


def _client() -> anthropic.Anthropic:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise EnvironmentError("ANTHROPIC_API_KEY is not set.")
    return anthropic.Anthropic(api_key=key)


def _chat(system: str, user: str, max_tokens: int = 512) -> str:
    """Single Claude turn, returns the assistant text."""
    response = _client().messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return response.content[0].text.strip()


# ── Node functions ─────────────────────────────────────────────────────────────


def planner_node(state: dict[str, Any]) -> dict[str, Any]:
    """Decompose the user question into 1-3 sub-questions."""
    question = state["question"]
    system = PLANNER_SYSTEM
    if state.get("replanned", False):
        system = PLANNER_SYSTEM + REPLAN_SUFFIX

    log.info("[planner] question: %s", question)
    raw = _chat(system, question, max_tokens=256)

    try:
        sub_questions = json.loads(raw)
        if not isinstance(sub_questions, list):
            sub_questions = [question]
    except json.JSONDecodeError:
        sub_questions = [question]

    sub_questions = [str(q).strip() for q in sub_questions[:MAX_SUB_QUESTIONS]]
    log.info("[planner] sub-questions: %s", sub_questions)
    return {"sub_questions": sub_questions}


def sql_generator_node(state: dict[str, Any]) -> dict[str, Any]:
    """Generate one SQL query per sub-question."""
    generated: list[str] = []
    for sq in state.get("sub_questions", []):
        prompt = f"Sub-question: {sq}"
        sql = _chat(SQL_GENERATOR_SYSTEM, prompt, max_tokens=512)
        sql = sql.strip().rstrip(";")
        generated.append(sql)
        log.info("[sql_gen] %s → %s", sq, sql[:80])
    return {"generated_sqls": generated}


def executor_node(state: dict[str, Any]) -> dict[str, Any]:
    """Execute each generated SQL against DuckDB."""
    results = []
    sql_trace = []
    for sql in state.get("generated_sqls", []):
        result = execute_sql(sql)
        results.append(result)
        sql_trace.append(sql)
        if result["error"]:
            log.warning("[executor] error: %s", result["error"])
        else:
            log.info("[executor] %d rows returned", result["row_count"])
    return {"results": results, "sql_trace": sql_trace}


def validator_node(state: dict[str, Any]) -> dict[str, Any]:
    """Decide whether to replan (empty results) or proceed to synthesis."""
    results = state.get("results", [])
    already_replanned = state.get("replanned", False)

    all_empty = all(
        r.get("row_count", 0) == 0 and not r.get("error")
        for r in results
    ) if results else True

    should_replan = all_empty and not already_replanned

    routing = "replan" if should_replan else "synthesize"
    log.info("[validator] all_empty=%s, already_replanned=%s → %s",
             all_empty, already_replanned, routing)
    return {"routing": routing, "replanned": already_replanned or should_replan}


def synthesizer_node(state: dict[str, Any]) -> dict[str, Any]:
    """Combine all sub-results into a final natural-language answer."""
    question = state["question"]
    sub_questions = state.get("sub_questions", [])
    results = state.get("results", [])

    # Build context block for Claude
    context_parts = []
    for sq, result in zip(sub_questions, results):
        context_parts.append(f"Sub-question: {sq}")
        if result.get("error"):
            context_parts.append(f"Error: {result['error']}")
        elif result.get("row_count", 0) == 0:
            context_parts.append("Result: no data found")
        else:
            rows = result["data"][:10]  # cap for prompt size
            context_parts.append(f"Result ({result['row_count']} rows): {json.dumps(rows, default=str)}")

    context = "\n\n".join(context_parts)
    user_prompt = f"Question: {question}\n\nData:\n{context}\n\nAnswer:"

    answer = _chat(SYNTHESIZER_SYSTEM, user_prompt, max_tokens=300)
    log.info("[synthesizer] answer length: %d chars", len(answer))
    return {"answer": answer}
