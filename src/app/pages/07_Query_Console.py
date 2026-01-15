"""Query Console — predefined metric queries and NL agent interface."""
import os
import time

import streamlit as st
import plotly.express as px

st.set_page_config(page_title="Query Console · Placelytics", page_icon="🔎", layout="wide")

from src.app.components import db_path_ok, page_header, qdb

page_header("Query Console", "Run predefined metrics or ask questions in natural language")
if not db_path_ok():
    st.stop()

tab_sql, tab_nl = st.tabs(["📋 Metric Queries", "🤖 NL Agent"])

# ── Tab 1: Predefined metric queries ─────────────────────────────────────────

with tab_sql:
    st.subheader("Run a Named Metric")
    st.caption("Metrics are defined in `metrics/definitions/` YAML files.")

    from src.metrics.loader import load_registry
    from src.metrics.executor import MetricExecutor

    @st.cache_resource
    def _get_executor():
        return MetricExecutor()

    executor = _get_executor()
    registry = executor.registry

    col_sel, col_info = st.columns([2, 3])

    with col_sel:
        category = st.selectbox(
            "Category",
            ["All"] + sorted({m.category for m in registry.all()}),
        )
        metrics_list = (
            registry.all() if category == "All"
            else registry.by_category(category)
        )
        metric_name = st.selectbox(
            "Metric",
            [m.name for m in metrics_list],
            format_func=lambda n: registry.get(n).label,
        )

    with col_info:
        if metric_name:
            m = registry.get(metric_name)
            st.markdown(f"**{m.label}**")
            st.caption(m.description)
            with st.expander("SQL"):
                st.code(m.sql, language="sql")

    if st.button("▶ Run", type="primary"):
        with st.spinner("Running…"):
            df = executor.run(metric_name)
        st.success(f"{len(df)} rows returned")
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Auto-chart for numeric results
        num_cols = [c for c in df.columns if df[c].dtype in ("float64", "int64")]
        cat_cols = [c for c in df.columns if df[c].dtype == "object"]
        if cat_cols and num_cols:
            fig = px.bar(df.head(20), x=cat_cols[0], y=num_cols[0],
                         title=f"{registry.get(metric_name).label}",
                         color=num_cols[0], color_continuous_scale="Blues",
                         text_auto=".2f")
            fig.update_layout(height=380, coloraxis_showscale=False)
            st.plotly_chart(fig, use_container_width=True)

# ── Tab 2: NL Agent ───────────────────────────────────────────────────────────

with tab_nl:
    st.subheader("Ask a Question in Plain English")

    api_key_set = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if not api_key_set:
        st.warning(
            "**ANTHROPIC_API_KEY not set.** Add it to your `.env` file and restart the app "
            "to enable the NL agent.",
            icon="⚠️",
        )

    EXAMPLE_QUESTIONS = [
        "Which branches have the highest average CTC?",
        "How many companies offer PPO and what do they pay on average?",
        "Which role families have the most no-CGPA offers?",
        "What is the trend of CTC across the placement season?",
        "Which companies offer the most intern-to-FTE positions?",
    ]

    example = st.selectbox("Try an example question (or type your own below):", [""] + EXAMPLE_QUESTIONS)
    question = st.text_input("Your question:", value=example, placeholder="e.g. What is the avg CTC for software roles?")

    if st.button("Ask", type="primary", disabled=not api_key_set or not question):
        from src.agent.graph import run as agent_run

        with st.spinner("Thinking…"):
            start = time.time()
            result = agent_run(question)
            elapsed = round(time.time() - start, 1)

        if result.success:
            st.success("Answer")
            st.markdown(result.answer)

            st.caption(f"Completed in {elapsed}s · {'Replanned once' if result.replanned else 'No replan needed'}")

            with st.expander("🔍 Agent reasoning trace", expanded=False):
                st.markdown("**Sub-questions decomposed by planner:**")
                for i, sq in enumerate(result.sub_questions, 1):
                    st.markdown(f"{i}. {sq}")

                st.markdown("**SQL queries executed:**")
                for i, (sql, res) in enumerate(zip(result.sql_trace, result.results), 1):
                    st.markdown(f"*Query {i}* — {res.get('row_count',0)} rows")
                    st.code(sql, language="sql")
                    if res.get("error"):
                        st.error(f"Error: {res['error']}")
                    elif res.get("data"):
                        import pandas as pd
                        st.dataframe(pd.DataFrame(res["data"]).head(10),
                                     hide_index=True, use_container_width=True)
        else:
            st.error(f"Agent error: {result.error}")

    if not api_key_set:
        st.divider()
        st.markdown("**Without an API key, you can still run predefined metrics in the Metric Queries tab.**")
