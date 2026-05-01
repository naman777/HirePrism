"""Data Quality — scorecard, history trend, and anomaly records."""
import json
from pathlib import Path

import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Quality · HirePrism", page_icon="🔍", layout="wide")

from src.app.components import db_path_ok, page_header, qdb

page_header("Data Quality", "Quality scorecard, pipeline history, and flagged anomalies")

REPORT_PATH = Path("data/quality/quality_report.json")
HISTORY_PATH = Path("data/quality/quality_history.jsonl")
ANOMALY_PATH = Path("data/quality/anomaly_summary.json")

# ── Scorecard ─────────────────────────────────────────────────────────────────

st.subheader("Latest Quality Scorecard")

if REPORT_PATH.exists():
    report = json.loads(REPORT_PATH.read_text())
    scores = report.get("scores", {})
    overall = report.get("overall_score", 0)
    flagged = report.get("flagged_issues", [])
    ts = report.get("run_timestamp", "unknown")

    col_gauge, col_table = st.columns([1, 2])
    with col_gauge:
        color = "#2ecc71" if overall >= 0.85 else "#f39c12" if overall >= 0.70 else "#e74c3c"
        st.markdown(
            f"<div style='text-align:center'>"
            f"<div style='font-size:4rem;font-weight:bold;color:{color}'>{overall:.1%}</div>"
            f"<div style='color:gray'>Overall Quality Score</div>"
            f"<div style='color:gray;font-size:0.8em'>as of {ts}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        st.caption(f"Based on {report.get('total_offers',0)} offers")

    with col_table:
        import pandas as pd
        df_scores = pd.DataFrame([
            {"Check": k.replace("_", " ").title(), "Score": v,
             "Status": "✅" if v >= 0.75 else "⚠️"}
            for k, v in scores.items()
        ])
        df_scores["Score %"] = df_scores["Score"].map(lambda x: f"{x:.1%}")
        st.dataframe(df_scores[["Check", "Score %", "Status"]],
                     hide_index=True, use_container_width=True)

    if flagged:
        st.warning(f"**{len(flagged)} check(s) below 75% threshold:**")
        for issue in flagged:
            st.markdown(f"- **[{issue['severity']}]** {issue['message']}")
else:
    st.info("Run `make quality` to generate the scorecard.")

# ── History trend ─────────────────────────────────────────────────────────────

st.divider()
st.subheader("Quality Score History")

if HISTORY_PATH.exists():
    import pandas as pd

    lines = HISTORY_PATH.read_text().strip().splitlines()
    history = [json.loads(l) for l in lines if l.strip()]
    if len(history) >= 2:
        hist_df = pd.DataFrame([
            {"run": h["run_timestamp"], "overall": h["overall_score"]}
            for h in history
        ])
        fig = px.line(hist_df, x="run", y="overall", markers=True,
                      labels={"run": "Pipeline Run", "overall": "Overall Score"},
                      title="Quality Score Across Pipeline Runs")
        fig.add_hline(y=0.75, line_dash="dash", line_color="orange",
                      annotation_text="75% threshold")
        fig.update_layout(height=300, yaxis_tickformat=".0%")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Run the pipeline at least twice to see trend history.")
else:
    st.info("Quality history not yet available.")

# ── Anomaly summary ───────────────────────────────────────────────────────────

st.divider()
st.subheader("Anomaly Summary")

if ANOMALY_PATH.exists():
    asum = json.loads(ANOMALY_PATH.read_text())
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Flags", asum.get("total_flags", 0))
    col2.metric("Flagged Offers", asum.get("flagged_offers", 0))
    col3.metric("HIGH severity", asum.get("by_severity", {}).get("HIGH", 0))

    import pandas as pd
    col_t, col_s = st.columns(2)
    with col_t:
        by_type = pd.DataFrame(asum.get("by_type", {}).items(),
                               columns=["Anomaly Type", "Count"])
        fig2 = px.bar(by_type, x="Count", y="Anomaly Type", orientation="h",
                      color="Count", color_continuous_scale="Reds",
                      text_auto=True, title="Flags by Type")
        fig2.update_layout(height=300, coloraxis_showscale=False)
        st.plotly_chart(fig2, use_container_width=True)
    with col_s:
        by_sev = pd.DataFrame(asum.get("by_severity", {}).items(),
                              columns=["Severity", "Count"])
        fig3 = px.pie(by_sev, names="Severity", values="Count",
                      color="Severity",
                      color_discrete_map={"HIGH": "#e74c3c", "MEDIUM": "#f39c12", "LOW": "#95a5a6"},
                      title="Flags by Severity")
        fig3.update_layout(height=300)
        st.plotly_chart(fig3, use_container_width=True)

# ── Anomaly records table ─────────────────────────────────────────────────────

st.divider()
st.subheader("Flagged Records")

if db_path_ok():
    with st.sidebar:
        st.header("Filter")
        sev_filter = st.multiselect("Severity", ["HIGH", "MEDIUM", "LOW"],
                                    default=["HIGH", "MEDIUM", "LOW"])
        type_filter = st.multiselect(
            "Anomaly type",
            ["CTC_OUTLIER", "STIPEND_EXCEEDS_CTC",
             "IMPLAUSIBLE_STUDENT_COUNT", "NO_COMPENSATION", "RARE_ROLE"],
            default=["CTC_OUTLIER", "STIPEND_EXCEEDS_CTC",
                     "IMPLAUSIBLE_STUDENT_COUNT", "NO_COMPENSATION", "RARE_ROLE"],
        )

    sev_sql = ", ".join(f"'{s}'" for s in sev_filter) if sev_filter else "'HIGH'"
    type_sql = ", ".join(f"'{t}'" for t in type_filter) if type_filter else "'CTC_OUTLIER'"

    anomalies = qdb(f"""
        SELECT severity, anomaly_type, company_name, job_role_raw,
               offer_type_standardized, ctc_lpa_normalized, anomaly_detail
        FROM vw_anomalies
        WHERE severity IN ({sev_sql})
          AND anomaly_type IN ({type_sql})
        ORDER BY CASE severity WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END,
                 anomaly_type
    """)

    if not anomalies.empty:
        st.dataframe(anomalies.rename(columns={
            "severity": "Severity", "anomaly_type": "Type",
            "company_name": "Company", "job_role_raw": "Role",
            "offer_type_standardized": "Offer Type",
            "ctc_lpa_normalized": "CTC (LPA)",
            "anomaly_detail": "Detail",
        }), hide_index=True, use_container_width=True)
    else:
        st.info("No anomalies match the current filters.")
