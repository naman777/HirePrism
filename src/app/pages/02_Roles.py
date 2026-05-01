"""Role Intelligence — job family analysis, CTC by role, CGPA patterns."""
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="Roles · HirePrism", page_icon="🎯", layout="wide")

from src.app.components import db_path_ok, page_header, qdb, empty_state

page_header("Role Intelligence", "Job family distribution, compensation, and eligibility patterns")
if not db_path_ok():
    st.stop()

# ── Role family distribution ──────────────────────────────────────────────────

col1, col2 = st.columns(2)

with col1:
    st.subheader("Offer Count by Job Family")
    rf = qdb("SELECT * FROM vw_role_summary ORDER BY offer_count DESC")
    if not rf.empty:
        fig = px.bar(rf, x="offer_count", y="job_family", orientation="h",
                     color="avg_ctc_lpa", color_continuous_scale="Blues",
                     labels={"offer_count": "Offers", "job_family": "Family",
                             "avg_ctc_lpa": "Avg CTC"},
                     text="offer_count")
        fig.update_traces(textposition="outside")
        fig.update_layout(height=400, yaxis=dict(categoryorder="total ascending"),
                          coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Average CTC by Job Family (LPA)")
    if not rf.empty:
        rf_ctc = rf[rf["avg_ctc_lpa"].notna()].sort_values("avg_ctc_lpa", ascending=False)
        fig2 = px.bar(rf_ctc, x="job_family", y="avg_ctc_lpa",
                      error_y=None,
                      color="avg_ctc_lpa", color_continuous_scale="RdYlGn",
                      labels={"avg_ctc_lpa": "Avg CTC (LPA)", "job_family": "Family"},
                      text_auto=".1f")
        fig2.update_layout(height=400, showlegend=False, coloraxis_showscale=False)
        st.plotly_chart(fig2, use_container_width=True)

# ── CTC variance ──────────────────────────────────────────────────────────────

st.divider()
st.subheader("CTC Variance by Role Family")
st.caption("Coefficient of Variation (std/mean) — higher = more spread between high and low paying roles in the same family")

variance = qdb("""
    SELECT job_family,
           ROUND(AVG(ctc_lpa_normalized),2) AS avg_ctc,
           ROUND(STDDEV(ctc_lpa_normalized),2) AS std_ctc,
           ROUND(MIN(ctc_lpa_normalized),2) AS min_ctc,
           ROUND(MAX(ctc_lpa_normalized),2) AS max_ctc,
           ROUND(STDDEV(ctc_lpa_normalized)/NULLIF(AVG(ctc_lpa_normalized),0),3) AS cv,
           COUNT(*) AS n
    FROM fact_offers
    WHERE ctc_status IN ('KNOWN','RANGE') AND job_family != 'Unknown'
    GROUP BY job_family HAVING COUNT(*)>=5
    ORDER BY cv DESC
""")

if not variance.empty:
    fig3 = px.scatter(variance, x="avg_ctc", y="cv", size="n",
                      color="job_family", text="job_family",
                      labels={"avg_ctc": "Avg CTC (LPA)", "cv": "Coefficient of Variation",
                               "n": "Offer count"},
                      title="CTC Variance vs Mean — bubble size = offer count")
    fig3.update_traces(textposition="top center")
    fig3.update_layout(height=400, showlegend=False)
    st.plotly_chart(fig3, use_container_width=True)

# ── Top raw roles ─────────────────────────────────────────────────────────────

st.divider()
col3, col4 = st.columns(2)

with col3:
    st.subheader("Top 20 Roles by Frequency")
    top_roles = qdb("""
        SELECT job_role_raw, role_standardized, job_family, COUNT(*) AS n
        FROM fact_offers
        WHERE job_role_raw NOT IN ('','Not Known','Not Declared','-')
          AND job_role_raw IS NOT NULL
        GROUP BY job_role_raw, role_standardized, job_family
        ORDER BY n DESC LIMIT 20
    """)
    if not top_roles.empty:
        st.dataframe(top_roles.rename(columns={
            "job_role_raw": "Raw Role", "role_standardized": "Standardized",
            "job_family": "Family", "n": "Count",
        }), hide_index=True, use_container_width=True)

with col4:
    st.subheader("No-CGPA Rate by Role Family")
    if not rf.empty:
        rf_cgpa = rf.copy()
        rf_cgpa["no_cgpa_pct"] = (rf_cgpa["no_cgpa_count"] / rf_cgpa["offer_count"] * 100).round(1)
        fig4 = px.bar(rf_cgpa.sort_values("no_cgpa_pct", ascending=True),
                      x="no_cgpa_pct", y="job_family", orientation="h",
                      labels={"no_cgpa_pct": "% with No CGPA Filter", "job_family": "Family"},
                      color="no_cgpa_pct", color_continuous_scale="Greens",
                      text_auto=".0f")
        fig4.update_layout(height=400, coloraxis_showscale=False,
                           yaxis=dict(categoryorder="total ascending"))
        st.plotly_chart(fig4, use_container_width=True)
