from __future__ import annotations

import signal
import threading
from pathlib import Path
from typing import Any

from src.modeling.build_tables import DB_PATH, connect
from src.metrics.loader import load_registry

QUERY_TIMEOUT_SECONDS = 10

ALLOWED_TABLES = frozenset(
    [
        "fact_offers",
        "bridge_offer_branches",
        "dim_role",
        "dim_branch",
        "dim_company",
        "anomaly_flags",
        "vw_high_package_offers",
        "vw_role_summary",
        "vw_branch_summary",
        "vw_company_summary",
        "vw_internship_summary",
        "vw_no_cgpa_offers",
        "vw_compensation_unknown",
        "vw_anomalies",
    ]
)

_WRITE_KEYWORDS = frozenset(
    ["insert", "update", "delete", "drop", "create", "alter", "truncate", "replace"]
)


def validate_sql(sql: str) -> str | None:
    """Return an error string if the SQL is not safe, else None."""
    lower = sql.lower().strip()
    for kw in _WRITE_KEYWORDS:
        if f" {kw} " in f" {lower} " or lower.startswith(kw):
            return f"Write operation '{kw}' is not allowed."
    return None


def execute_sql(
    sql: str,
    db_path: Path = DB_PATH,
    timeout: int = QUERY_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Execute a read-only SQL query with timeout. Returns a result dict.

    Result schema:
      sql        str          the executed SQL
      data       list[dict]   rows as list of dicts (empty on error)
      columns    list[str]    column names
      row_count  int          number of rows returned
      error      str | None   error message if query failed
    """
    safety_error = validate_sql(sql)
    if safety_error:
        return {"sql": sql, "data": [], "columns": [], "row_count": 0, "error": safety_error}

    result: dict[str, Any] = {"sql": sql, "data": [], "columns": [], "row_count": 0, "error": None}
    exc_holder: list[Exception] = []

    def _run() -> None:
        try:
            con = connect(db_path, read_only=True)
            try:
                rel = con.execute(sql)
                df = rel.df()
                result["columns"] = list(df.columns)
                result["data"] = df.to_dict(orient="records")
                result["row_count"] = len(df)
            finally:
                con.close()
        except Exception as exc:
            exc_holder.append(exc)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    if thread.is_alive():
        result["error"] = f"Query timed out after {timeout}s."
        return result

    if exc_holder:
        result["error"] = str(exc_holder[0])

    return result


def lookup_metrics(tag: str | None = None) -> list[dict[str, str]]:
    """Return metric definitions from the registry, optionally filtered by tag."""
    registry = load_registry()
    metrics = registry.by_tag(tag) if tag else registry.all()
    return [
        {"name": m.name, "label": m.label, "description": m.description, "sql": m.sql}
        for m in metrics
    ]


def get_table_names() -> list[str]:
    return sorted(ALLOWED_TABLES)
