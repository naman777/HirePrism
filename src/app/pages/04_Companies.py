"""Company Explorer — search, filter, and drill into individual companies."""
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="Companies · HirePrism", page_icon="🏢", layout="wide")

from src.app.components import db_path_ok, page_header, qdb, empty_state

page_header("Company Explorer", "Search and drill into individual company offer profiles")
if not db_path_ok():
    st.stop()

# ── Search and filters ────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Filters")
    search = st.text_input("Search company name", placeholder="e.g. Google")
    min_offers = st.slider("Min offers", 1, 10, 1)
    only_high_pkg = st.checkbox("High-package companies only (avg ≥ 10 LPA)")
    only_no_cgpa = st.checkbox("Companies with no-CGPA offers")

where_clauses = [f"total_offers >= {min_offers}"]
if only_high_pkg:
    where_clauses.append("avg_ctc_lpa >= 10")
if only_no_cgpa:
    where_clauses.append("no_cgpa_count > 0")
where_sql = " AND ".join(where_clauses)

summary = qdb(f"SELECT * FROM vw_company_summary WHERE {where_sql} ORDER BY total_offers DESC")

if search:
    summary = summary[summary["company_name"].str.contains(search, case=False, na=False)]

# ── Summary table ─────────────────────────────────────────────────────────────

st.subheader(f"{len(summary)} companies matching filters")

if not summary.empty:
    st.dataframe(summary.rename(columns={
        "company_name": "Company",
        "total_offers": "Offers",
        "distinct_offer_types": "Offer Types",
        "avg_ctc_lpa": "Avg CTC (LPA)",
        "max_ctc_lpa": "Max CTC (LPA)",
        "high_package_count": "High-Pkg Offers",
        "no_cgpa_count": "No-CGPA",
        "unknown_ctc_count": "Unknown CTC",
    }), hide_index=True, use_container_width=True)
else:
    empty_state("No companies match the current filters.")

# ── Top charts ────────────────────────────────────────────────────────────────

st.divider()
col1, col2 = st.columns(2)

with col1:
    st.subheader("Top 20 by Avg CTC")
    top_ctc = summary[summary["avg_ctc_lpa"].notna()].nlargest(20, "avg_ctc_lpa")
    if not top_ctc.empty:
        fig = px.bar(top_ctc, x="avg_ctc_lpa", y="company_name", orientation="h",
                     color="total_offers", color_continuous_scale="Blues",
                     labels={"avg_ctc_lpa": "Avg CTC (LPA)", "company_name": "Company",
                             "total_offers": "Offers"},
                     text_auto=".1f")
        fig.update_layout(height=500, yaxis=dict(categoryorder="total ascending"),
                          coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Top 20 by Offer Volume")
    top_vol = summary.nlargest(20, "total_offers")
    if not top_vol.empty:
        fig2 = px.bar(top_vol, x="total_offers", y="company_name", orientation="h",
                      color="avg_ctc_lpa", color_continuous_scale="RdYlGn",
                      labels={"total_offers": "Total Offers", "company_name": "Company",
                              "avg_ctc_lpa": "Avg CTC (LPA)"},
                      text_auto=True)
        fig2.update_layout(height=500, yaxis=dict(categoryorder="total ascending"),
                           coloraxis_colorbar_title="Avg CTC")
        st.plotly_chart(fig2, use_container_width=True)

# ── Single company drill-down ─────────────────────────────────────────────────

st.divider()
st.subheader("Single Company Drill-Down")

all_companies = qdb("SELECT DISTINCT company_name FROM fact_offers ORDER BY company_name")
selected_co = st.selectbox("Select company", all_companies["company_name"].tolist())

if selected_co:
    co_offers = qdb(f"""
        SELECT offer_type_standardized, job_role_raw, ctc_lpa_normalized, ctc_status,
               stipend_monthly_normalized, stipend_status, no_cgpa_criteria,
               eligibility_cgpa_num, location_extracted, notice_date_raw
        FROM fact_offers WHERE company_name = '{selected_co.replace("'","''")}'
        ORDER BY ctc_lpa_normalized DESC NULLS LAST
    """)
    if not co_offers.empty:
        st.caption(f"**{len(co_offers)} offer(s)** from {selected_co}")
        st.dataframe(co_offers.rename(columns={
            "offer_type_standardized": "Type",
            "job_role_raw": "Role",
            "ctc_lpa_normalized": "CTC (LPA)",
            "ctc_status": "CTC Status",
            "stipend_monthly_normalized": "Stipend (₹/mo)",
            "stipend_status": "Stip. Status",
            "no_cgpa_criteria": "No CGPA",
            "eligibility_cgpa_num": "CGPA Min",
            "location_extracted": "Location",
            "notice_date_raw": "Notice Date",
        }), hide_index=True, use_container_width=True)
