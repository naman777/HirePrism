from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from src.agent.tools import execute_sql, get_table_names, validate_sql


# ── tools: validate_sql ───────────────────────────────────────────────────────


def test_validate_sql_allows_select() -> None:
    assert validate_sql("SELECT * FROM fact_offers LIMIT 5") is None


def test_validate_sql_blocks_insert() -> None:
    assert validate_sql("INSERT INTO fact_offers VALUES (1)") is not None


def test_validate_sql_blocks_drop() -> None:
    assert validate_sql("DROP TABLE fact_offers") is not None


def test_validate_sql_blocks_update() -> None:
    assert validate_sql("UPDATE fact_offers SET ctc_raw = '10'") is not None


def test_validate_sql_blocks_create() -> None:
    assert validate_sql("CREATE TABLE foo (x INT)") is not None


# ── tools: execute_sql ────────────────────────────────────────────────────────


def test_execute_sql_valid_query() -> None:
    result = execute_sql("SELECT COUNT(*) AS n FROM fact_offers")
    assert result["error"] is None
    assert result["row_count"] == 1
    assert result["data"][0]["n"] == 654


def test_execute_sql_returns_correct_columns() -> None:
    result = execute_sql("SELECT company_name, ctc_lpa_normalized FROM fact_offers LIMIT 3")
    assert "company_name" in result["columns"]
    assert "ctc_lpa_normalized" in result["columns"]


def test_execute_sql_captures_error() -> None:
    result = execute_sql("SELECT * FROM nonexistent_table_xyz")
    assert result["error"] is not None
    assert result["row_count"] == 0
    assert result["data"] == []


def test_execute_sql_blocks_write_query() -> None:
    result = execute_sql("DROP TABLE fact_offers")
    assert result["error"] is not None
    assert "not allowed" in result["error"].lower()


def test_execute_sql_timeout() -> None:
    # Very short timeout; a real query might still finish but we test the path
    result = execute_sql("SELECT COUNT(*) FROM fact_offers", timeout=0)
    # Either completes fast or times out — either way returns a dict
    assert "error" in result
    assert "row_count" in result


def test_execute_sql_high_package_view() -> None:
    result = execute_sql("SELECT COUNT(*) AS n FROM vw_high_package_offers")
    assert result["error"] is None
    assert result["data"][0]["n"] == 247


def test_get_table_names_returns_list() -> None:
    names = get_table_names()
    assert isinstance(names, list)
    assert "fact_offers" in names
    assert "vw_role_summary" in names


# ── nodes: planner (mocked Claude) ────────────────────────────────────────────


def _mock_response(text: str) -> MagicMock:
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


@patch("src.agent.nodes._client")
def test_planner_node_returns_sub_questions(mock_client_fn) -> None:
    mock_client = MagicMock()
    mock_client_fn.return_value = mock_client
    mock_client.messages.create.return_value = _mock_response(
        '["What is the avg CTC by branch?", "Which branches have most offers?"]'
    )

    from src.agent.nodes import planner_node

    state = {"question": "Which branches pay the most?", "replanned": False}
    result = planner_node(state)
    assert "sub_questions" in result
    assert len(result["sub_questions"]) == 2


@patch("src.agent.nodes._client")
def test_planner_node_falls_back_on_bad_json(mock_client_fn) -> None:
    mock_client = MagicMock()
    mock_client_fn.return_value = mock_client
    mock_client.messages.create.return_value = _mock_response("not valid json at all")

    from src.agent.nodes import planner_node

    state = {"question": "What is the avg CTC?", "replanned": False}
    result = planner_node(state)
    assert len(result["sub_questions"]) == 1
    assert result["sub_questions"][0] == "What is the avg CTC?"


# ── nodes: sql_generator (mocked Claude) ──────────────────────────────────────


@patch("src.agent.nodes._client")
def test_sql_generator_produces_sql_per_sub_question(mock_client_fn) -> None:
    mock_client = MagicMock()
    mock_client_fn.return_value = mock_client
    mock_client.messages.create.return_value = _mock_response(
        "SELECT job_family, ROUND(AVG(ctc_lpa_normalized),2) AS avg_ctc FROM fact_offers GROUP BY job_family"
    )

    from src.agent.nodes import sql_generator_node

    state = {"sub_questions": ["What is avg CTC by job family?"]}
    result = sql_generator_node(state)
    assert len(result["generated_sqls"]) == 1
    assert "SELECT" in result["generated_sqls"][0].upper()


# ── nodes: executor ───────────────────────────────────────────────────────────


def test_executor_node_runs_valid_sql() -> None:
    from src.agent.nodes import executor_node

    state = {
        "generated_sqls": ["SELECT COUNT(*) AS n FROM fact_offers"]
    }
    result = executor_node(state)
    assert len(result["results"]) == 1
    assert result["results"][0]["row_count"] == 1
    assert result["results"][0]["error"] is None


def test_executor_node_captures_sql_error() -> None:
    from src.agent.nodes import executor_node

    state = {"generated_sqls": ["SELECT * FROM table_that_does_not_exist"]}
    result = executor_node(state)
    assert result["results"][0]["error"] is not None


# ── nodes: validator ──────────────────────────────────────────────────────────


def test_validator_routes_to_replan_on_empty(monkeypatch) -> None:
    from src.agent.nodes import validator_node

    state = {
        "results": [{"row_count": 0, "data": [], "error": None}],
        "replanned": False,
    }
    result = validator_node(state)
    assert result["routing"] == "replan"
    assert result["replanned"] is True


def test_validator_routes_to_synthesize_on_data(monkeypatch) -> None:
    from src.agent.nodes import validator_node

    state = {
        "results": [{"row_count": 5, "data": [{"n": 5}], "error": None}],
        "replanned": False,
    }
    result = validator_node(state)
    assert result["routing"] == "synthesize"


def test_validator_routes_to_synthesize_after_replan(monkeypatch) -> None:
    from src.agent.nodes import validator_node

    state = {
        "results": [{"row_count": 0, "data": [], "error": None}],
        "replanned": True,  # already replanned once
    }
    result = validator_node(state)
    assert result["routing"] == "synthesize"


# ── nodes: synthesizer (mocked Claude) ───────────────────────────────────────


@patch("src.agent.nodes._client")
def test_synthesizer_node_returns_answer(mock_client_fn) -> None:
    mock_client = MagicMock()
    mock_client_fn.return_value = mock_client
    mock_client.messages.create.return_value = _mock_response(
        "Software Engineering averages 13.4 LPA across 261 offers."
    )

    from src.agent.nodes import synthesizer_node

    state = {
        "question": "What is avg CTC for Software Engineering?",
        "sub_questions": ["What is avg CTC for Software Engineering?"],
        "results": [{"row_count": 1, "data": [{"avg_ctc": 13.4}], "error": None}],
    }
    result = synthesizer_node(state)
    assert "answer" in result
    assert len(result["answer"]) > 0


# ── graph: AgentResult ────────────────────────────────────────────────────────


def test_agent_result_fields() -> None:
    from src.agent.graph import AgentResult

    r = AgentResult(
        question="test?",
        answer="42 LPA",
        sub_questions=["sub q"],
        sql_trace=["SELECT 1"],
        results=[],
        success=True,
    )
    assert r.question == "test?"
    assert r.success is True
    assert r.error is None


# ── graph: full pipeline (mocked) ─────────────────────────────────────────────


@patch("src.agent.nodes._client")
def test_run_returns_agent_result(mock_client_fn) -> None:
    mock_client = MagicMock()
    mock_client_fn.return_value = mock_client

    # planner → sql_generator → synthesizer each get one call
    mock_client.messages.create.side_effect = [
        _mock_response('["How many offers are there?"]'),          # planner
        _mock_response("SELECT COUNT(*) AS n FROM fact_offers"),   # sql_gen
        _mock_response("There are 654 offers in the dataset."),    # synthesizer
    ]

    from src.agent.graph import run

    result = run("How many offers are in the dataset?")
    assert result.success is True
    assert result.answer == "There are 654 offers in the dataset."
    assert len(result.sql_trace) == 1


@patch("src.agent.nodes._client")
def test_run_returns_error_result_on_exception(mock_client_fn) -> None:
    mock_client_fn.side_effect = EnvironmentError("OPENAI_API_KEY is not set.")

    from src.agent.graph import run

    result = run("anything")
    assert result.success is False
    assert result.error is not None


# ── integration: real Claude (skip if no API key) ─────────────────────────────


@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set — skipping live agent test",
)
def test_run_live_simple_question() -> None:
    from src.agent.graph import run

    result = run("How many companies are in the dataset?")
    assert result.success is True
    assert len(result.answer) > 10
    assert len(result.sql_trace) >= 1
    assert "386" in result.answer or "company" in result.answer.lower()
