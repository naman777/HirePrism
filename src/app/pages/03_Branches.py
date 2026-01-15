"""Branch Intelligence — eligibility, opportunities, and FTE vs intern split."""
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="Branches · Placelytics", page_icon="🌿", layout="wide")

from src.app.components import db_path_ok, page_header, qdb, empty_state

page_header("Branch Intelligence", "Opportunity count, average CTC, and FTE vs intern breakdown by branch")
if not db_path_ok():
    st.stop()

# ── Branch group summary ──────────────────────────────────────────────────────

st.subheader("Opportunities by Branch Group")

bg = qdb("""
    SELECT branch_group,
           SUM(offer_count) AS total_offers,
           ROUND(AVG(avg_ctc_lpa),2) AS avg_ctc,
           SUM(fte_count) AS fte,
           SUM(intern_count) AS intern,
           ROUND(SUM(fte_count)*100.0/NULLIF(SUM(offer_count),0),1) AS fte_pct
    FROM vw_branch_summary
    WHERE branch_group NOT IN ('ALL','NA','UNKNOWN')
    GROUP BY branch_group ORDER BY total_offers DESC
""")

if not bg.empty:
    col1, col2 = st.columns(2)
    with col1:
        fig = px.bar(bg, x="branch_group", y="total_offers",
                     color="avg_ctc", color_continuous_scale="Viridis",
                     labels={"branch_group": "Group", "total_offers": "Offers",
                             "avg_ctc": "Avg CTC (LPA)"},
                     text_auto=True, title="Offer Count by Branch Group")
        fig.update_layout(height=380, coloraxis_colorbar_title="Avg CTC")
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        fig2 = px.bar(bg, x="branch_group", y=["fte", "intern"],
                      labels={"branch_group": "Group", "value": "Offers", "variable": "Type"},
                      barmode="group", title="FTE vs Intern Count by Branch Group",
                      color_discrete_map={"fte": "#2196F3", "intern": "#FF9800"})
        fig2.update_layout(height=380)
        st.plotly_chart(fig2, use_container_width=True)

# ── Per-branch table ──────────────────────────────────────────────────────────

st.divider()
st.subheader("Per-Branch Breakdown")

branch_df = qdb("""
    SELECT branch_standardized, branch_group,
           offer_count, avg_ctc_lpa,
           fte_count, intern_count,
           ROUND(fte_count*1.0/NULLIF(intern_count,0),2) AS fte_intern_ratio,
           no_cgpa_count
    FROM vw_branch_summary
    ORDER BY offer_count DESC
""")

if not branch_df.empty:
    # Sidebar filter for group
    with st.sidebar:
        st.header("Filter")
        groups = ["All"] + sorted(branch_df["branch_group"].dropna().unique().tolist())
        selected_group = st.selectbox("Branch group", groups)

    if selected_group != "All":
        branch_df = branch_df[branch_df["branch_group"] == selected_group]

    st.dataframe(branch_df.rename(columns={
        "branch_standardized": "Branch",
        "branch_group": "Group",
        "offer_count": "Offers",
        "avg_ctc_lpa": "Avg CTC (LPA)",
        "fte_count": "FTE",
        "intern_count": "Intern",
        "fte_intern_ratio": "FTE/Intern Ratio",
        "no_cgpa_count": "No-CGPA",
    }), hide_index=True, use_container_width=True)

# ── Avg CTC heatmap ───────────────────────────────────────────────────────────

st.divider()
st.subheader("Average CTC by Branch (Known CTC Only)")

avg_ctc = qdb("""
    SELECT branch_standardized, branch_group, avg_ctc_lpa, offer_count
    FROM vw_branch_summary
    WHERE avg_ctc_lpa IS NOT NULL
      AND branch_standardized NOT IN ('UNKNOWN','NOT_APPLICABLE')
    ORDER BY avg_ctc_lpa DESC
""")

if not avg_ctc.empty:
    fig3 = px.bar(avg_ctc, x="branch_standardized", y="avg_ctc_lpa",
                  color="branch_group",
                  labels={"branch_standardized": "Branch", "avg_ctc_lpa": "Avg CTC (LPA)",
                          "branch_group": "Group"},
                  text_auto=".1f", title="Avg CTC by Branch Code")
    fig3.update_layout(height=400, xaxis_tickangle=-45)
    st.plotly_chart(fig3, use_container_width=True)
