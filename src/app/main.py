"""Overview — KPIs, quality scorecard, and top insights."""
import sys
import os
# Ensure project root is on sys.path for both local (python -m) and Streamlit Cloud
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import json
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()  # Load .env into os.environ before anything else

import streamlit as st

st.set_page_config(
    page_title="Placelytics",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

from src.app.components import db_path_ok, kpi_row, page_header, qdb

page_header(
    "Placelytics — Placement Intelligence Platform",
    "654 placement offers · 386 companies · academic year 2025–26",
)

if not db_path_ok():
    st.stop()

# ── KPI row ───────────────────────────────────────────────────────────────────

kpis = qdb("""
    SELECT
        COUNT(DISTINCT company_name)                                         AS companies,
        COUNT(*)                                                             AS offers,
        ROUND(AVG(CASE WHEN ctc_status IN ('KNOWN','RANGE')
                       THEN ctc_lpa_normalized END), 2)                     AS avg_ctc,
        COUNT(CASE WHEN ctc_status IN ('KNOWN','RANGE')
                        AND ctc_lpa_normalized >= 10 THEN 1 END)            AS high_pkg,
        ROUND(COUNT(CASE WHEN ctc_status IN ('PENDING','MISSING','UNKNOWN')
                         THEN 1 END)*100.0/COUNT(*), 1)                     AS unknown_ctc_pct,
        COUNT(CASE WHEN no_cgpa_criteria THEN 1 END)                        AS no_cgpa
    FROM fact_offers
""")

if not kpis.empty:
    r = kpis.iloc[0]
    kpi_row({
        "Companies": int(r["companies"]),
        "Total Offers": int(r["offers"]),
        "Avg CTC (known)": f"{r['avg_ctc']} LPA",
        "High Package (≥10 LPA)": int(r["high_pkg"]),
        "Unknown CTC": f"{r['unknown_ctc_pct']}%",
        "No-CGPA Offers": int(r["no_cgpa"]),
    })

st.divider()

# ── Quality scorecard ─────────────────────────────────────────────────────────

col_q, col_i = st.columns([1, 2])

with col_q:
    st.subheader("Data Quality Score")
    qr_path = Path("data/quality/quality_report.json")
    if qr_path.exists():
        report = json.loads(qr_path.read_text())
        overall = report.get("overall_score", 0)
        color = "green" if overall >= 0.85 else "orange" if overall >= 0.70 else "red"
        st.markdown(
            f"<h1 style='color:{color};text-align:center'>{overall:.1%}</h1>",
            unsafe_allow_html=True,
        )
        scores = report.get("scores", {})
        score_df = (
            {"Check": k.replace("_", " ").title(), "Score": f"{v:.1%}"}
            for k, v in scores.items()
        )
        st.dataframe(list(score_df), use_container_width=True, hide_index=True)
        flagged = report.get("flagged_issues", [])
        if flagged:
            with st.expander(f"⚠️ {len(flagged)} flagged issue(s)"):
                for issue in flagged:
                    st.warning(f"**[{issue['severity']}]** {issue['message']}")
    else:
        st.info("Run `make quality` to generate quality report.")

# ── Top insights ──────────────────────────────────────────────────────────────

with col_i:
    st.subheader("Top Insights")
    insight_path = Path("data/insights/insight_report.json")
    if insight_path.exists():
        insights = json.loads(insight_path.read_text())
        for card in insights[:3]:
            confidence_color = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🔴"}.get(
                card["confidence"], ""
            )
            with st.container(border=True):
                st.markdown(f"**{card['insight_id']}** {confidence_color} — {card['title']}")
                st.caption(card["finding"][:200] + "…")
        st.page_link("pages/05_Insights.py", label="View all 8 insights →")
    else:
        st.info("Run `make insights` to generate insight report.")

# ── Offer type breakdown ──────────────────────────────────────────────────────

st.divider()
st.subheader("Offer Type Breakdown")

import plotly.express as px

otype = qdb("SELECT * FROM vw_internship_summary ORDER BY offer_count DESC")
if not otype.empty:
    col1, col2 = st.columns(2)
    with col1:
        fig = px.pie(otype, names="offer_type_standardized", values="offer_count",
                     color_discrete_sequence=px.colors.qualitative.Set2,
                     hole=0.45)
        fig.update_layout(margin=dict(t=20, b=20), height=300, showlegend=True)
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        st.dataframe(
            otype[["offer_type_standardized", "offer_count", "pct_of_total",
                   "avg_ctc_lpa", "avg_stipend_monthly"]].rename(columns={
                "offer_type_standardized": "Type",
                "offer_count": "Offers",
                "pct_of_total": "%",
                "avg_ctc_lpa": "Avg CTC (LPA)",
                "avg_stipend_monthly": "Avg Stipend (₹/mo)",
            }),
            hide_index=True, use_container_width=True,
        )
