"""Compensation Explorer — CTC and stipend analysis."""
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="Compensation · HirePrism", page_icon="💰", layout="wide")

from src.app.components import db_path_ok, page_header, qdb, empty_state

page_header("Compensation Explorer", "CTC distribution, stipend ranges, and high-package offers")
if not db_path_ok():
    st.stop()

# ── Sidebar filters ───────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Filters")
    ctc_filter = st.selectbox("CTC status", ["KNOWN + RANGE", "KNOWN only", "All"])
    min_ctc = st.slider("Min CTC (LPA)", 0.0, 50.0, 0.0, 0.5)
    offer_types = st.multiselect(
        "Offer types",
        ["FTE", "INTERN", "INTERN_FTE", "INTERN_POSSIBLE_FTE", "PPO"],
        default=["FTE", "INTERN", "INTERN_FTE", "INTERN_POSSIBLE_FTE", "PPO"],
    )

ctc_where = (
    "ctc_status IN ('KNOWN','RANGE')" if ctc_filter != "All"
    else "ctc_status IS NOT NULL"
)
if ctc_filter == "KNOWN only":
    ctc_where = "ctc_status = 'KNOWN'"

type_list = ", ".join(f"'{t}'" for t in offer_types) if offer_types else "'FTE'"

# ── CTC Distribution ──────────────────────────────────────────────────────────

st.subheader("CTC Distribution")

ctc_data = qdb(f"""
    SELECT ctc_lpa_normalized, offer_type_standardized, job_family, company_name
    FROM fact_offers
    WHERE {ctc_where}
      AND ctc_lpa_normalized >= {min_ctc}
      AND offer_type_standardized IN ({type_list})
""")

if not ctc_data.empty:
    col1, col2 = st.columns(2)
    with col1:
        fig = px.histogram(
            ctc_data, x="ctc_lpa_normalized", nbins=40, color="offer_type_standardized",
            labels={"ctc_lpa_normalized": "CTC (LPA)", "offer_type_standardized": "Type"},
            title="CTC Distribution",
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        fig.update_layout(height=350, bargap=0.05)
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        fig2 = px.box(
            ctc_data, x="offer_type_standardized", y="ctc_lpa_normalized",
            color="offer_type_standardized",
            labels={"ctc_lpa_normalized": "CTC (LPA)", "offer_type_standardized": "Type"},
            title="CTC Spread by Offer Type",
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        fig2.update_layout(height=350, showlegend=False)
        st.plotly_chart(fig2, use_container_width=True)
else:
    empty_state("No CTC data matches the current filters.")

# ── High-package companies ─────────────────────────────────────────────────────

st.divider()
st.subheader("High-Package Companies (≥10 LPA)")

hp = qdb("""
    SELECT company_name, COUNT(*) AS high_pkg_offers,
           ROUND(AVG(ctc_lpa_normalized),2) AS avg_ctc,
           ROUND(MAX(ctc_lpa_normalized),2) AS max_ctc,
           STRING_AGG(DISTINCT offer_type_standardized, ', ') AS types
    FROM vw_high_package_offers
    GROUP BY company_name
    ORDER BY avg_ctc DESC
    LIMIT 25
""")

if not hp.empty:
    st.dataframe(hp.rename(columns={
        "company_name": "Company", "high_pkg_offers": "Offers",
        "avg_ctc": "Avg CTC (LPA)", "max_ctc": "Max CTC (LPA)", "types": "Types",
    }), hide_index=True, use_container_width=True)

# ── Stipend explorer ──────────────────────────────────────────────────────────

st.divider()
st.subheader("Stipend Distribution (Monthly, INR)")

stip = qdb("""
    SELECT stipend_monthly_normalized, offer_type_standardized, company_name
    FROM fact_offers
    WHERE stipend_status IN ('KNOWN','RANGE')
      AND stipend_monthly_normalized IS NOT NULL
      AND stipend_monthly_normalized > 0
""")

if not stip.empty:
    col3, col4 = st.columns(2)
    with col3:
        fig3 = px.histogram(
            stip, x="stipend_monthly_normalized", nbins=35,
            color="offer_type_standardized",
            labels={"stipend_monthly_normalized": "Monthly Stipend (₹)"},
            title="Stipend Distribution",
            color_discrete_sequence=px.colors.qualitative.Pastel,
        )
        fig3.update_layout(height=350)
        st.plotly_chart(fig3, use_container_width=True)
    with col4:
        stip_summary = qdb("""
            SELECT offer_type_standardized AS Type,
                   COUNT(*) AS Offers,
                   ROUND(AVG(stipend_monthly_normalized),0) AS "Avg (₹/mo)",
                   ROUND(MIN(stipend_monthly_normalized),0) AS "Min (₹/mo)",
                   ROUND(MAX(stipend_monthly_normalized),0) AS "Max (₹/mo)"
            FROM fact_offers
            WHERE stipend_status IN ('KNOWN','RANGE') AND stipend_monthly_normalized > 0
            GROUP BY offer_type_standardized ORDER BY "Avg (₹/mo)" DESC
        """)
        st.dataframe(stip_summary, hide_index=True, use_container_width=True)
else:
    empty_state("No stipend data available.")

# ── CTC over time ─────────────────────────────────────────────────────────────

st.divider()
st.subheader("CTC Trend Across Placement Season")

trend = qdb("""
    SELECT STRFTIME(notice_date,'%Y-%m') AS month,
           COUNT(*) AS offers,
           ROUND(AVG(ctc_lpa_normalized),2) AS avg_ctc
    FROM fact_offers
    WHERE ctc_status IN ('KNOWN','RANGE') AND notice_date IS NOT NULL
    GROUP BY 1 ORDER BY 1
""")

if not trend.empty:
    fig4 = px.line(trend, x="month", y="avg_ctc", markers=True,
                   labels={"month": "Month", "avg_ctc": "Avg CTC (LPA)"},
                   title="Average CTC by Month (known/range only)")
    fig4.update_traces(line_color="#2196F3", marker_size=8)
    fig4.update_layout(height=350)
    st.plotly_chart(fig4, use_container_width=True)
    st.caption(
        f"Peak: {trend.loc[trend['avg_ctc'].idxmax(),'month']} "
        f"({trend['avg_ctc'].max()} LPA) → "
        f"Trough: {trend.loc[trend['avg_ctc'].idxmin(),'month']} "
        f"({trend['avg_ctc'].min()} LPA)"
    )
