from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.modeling.build_tables import DB_PATH, connect

# ── DB helper ─────────────────────────────────────────────────────────────────


@st.cache_data(ttl=300, show_spinner=False)
def qdb(sql: str) -> pd.DataFrame:
    """Execute a read-only SQL query against DuckDB and return a DataFrame."""
    try:
        con = connect(DB_PATH, read_only=True)
        df = con.execute(sql).df()
        con.close()
        return df
    except Exception as exc:
        st.error(f"Query error: {exc}")
        return pd.DataFrame()


# ── Page layout helpers ───────────────────────────────────────────────────────


def page_header(title: str, subtitle: str = "") -> None:
    st.markdown(f"## {title}")
    if subtitle:
        st.caption(subtitle)
    st.divider()


def kpi_row(metrics: dict[str, str | int | float]) -> None:
    """Render a row of st.metric KPI cards."""
    cols = st.columns(len(metrics))
    for col, (label, value) in zip(cols, metrics.items()):
        col.metric(label, value)


def empty_state(message: str = "No data available.") -> None:
    st.info(message, icon="ℹ️")


def db_path_ok() -> bool:
    """Return True if the DuckDB file exists; show error otherwise."""
    if not DB_PATH.exists():
        st.error(
            f"Database not found at `{DB_PATH}`. Run `make db` first.",
            icon="🚨",
        )
        return False
    return True
