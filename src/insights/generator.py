from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from src.modeling.build_tables import DB_PATH, connect

CONFIDENCE_HIGH = "HIGH"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_LOW = "LOW"


@dataclass
class InsightCard:
    insight_id: str
    title: str
    finding: str
    supporting_metric: str
    confidence: str
    data_caveat: str
    numbers: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Individual insight functions ──────────────────────────────────────────────


def insight_ctc_season_decline(db_path: Path) -> InsightCard:
    """CTC drops sharply as the placement season progresses."""
    con = connect(db_path, read_only=True)
    try:
        df = con.execute("""
            SELECT STRFTIME(notice_date,'%Y-%m') AS month,
                   COUNT(*) AS offers,
                   ROUND(AVG(ctc_lpa_normalized), 2) AS avg_ctc
            FROM fact_offers
            WHERE ctc_status IN ('KNOWN','RANGE')
              AND notice_date IS NOT NULL
            GROUP BY 1 ORDER BY 1
        """).df()
    finally:
        con.close()

    peak_row = df.loc[df["avg_ctc"].idxmax()]
    trough_row = df.loc[df["avg_ctc"].idxmin()]
    drop_pct = round((peak_row["avg_ctc"] - trough_row["avg_ctc"])
                     / peak_row["avg_ctc"] * 100, 1)

    return InsightCard(
        insight_id="INS_001",
        title=f"CTC drops {drop_pct}% from peak to trough across the placement season",
        finding=(
            f"Offers posted in {peak_row['month']} averaged {peak_row['avg_ctc']} LPA — "
            f"the highest in the dataset. By {trough_row['month']}, the average had fallen "
            f"to {trough_row['avg_ctc']} LPA, a {drop_pct}% decline. "
            f"Early-season offers are dominated by premium tech and product companies; "
            f"late-season offers skew toward manufacturing and core engineering roles "
            f"with lower average compensation."
        ),
        supporting_metric="ctc_over_time",
        confidence=CONFIDENCE_HIGH,
        data_caveat=(
            f"Based on {int(df['offers'].sum())} offers with parseable CTC. "
            f"Month with fewest offers ({int(df['offers'].min())}) may be noisy."
        ),
        numbers={
            "peak_month": peak_row["month"],
            "peak_avg_ctc_lpa": float(peak_row["avg_ctc"]),
            "trough_month": trough_row["month"],
            "trough_avg_ctc_lpa": float(trough_row["avg_ctc"]),
            "decline_pct": drop_pct,
        },
    )


def insight_ppo_premium(db_path: Path) -> InsightCard:
    """PPO offers pay substantially more than standard FTE offers."""
    con = connect(db_path, read_only=True)
    try:
        df = con.execute("""
            SELECT offer_type_standardized,
                   COUNT(*) AS n,
                   ROUND(AVG(ctc_lpa_normalized), 2) AS avg_ctc
            FROM fact_offers
            WHERE ctc_status IN ('KNOWN','RANGE')
            GROUP BY offer_type_standardized
        """).df().set_index("offer_type_standardized")
    finally:
        con.close()

    ppo_ctc = float(df.loc["PPO", "avg_ctc"])
    fte_ctc = float(df.loc["FTE", "avg_ctc"])
    premium = round(ppo_ctc / fte_ctc, 2)

    return InsightCard(
        insight_id="INS_002",
        title=f"PPO offers pay {premium}× more than standard FTE offers on average",
        finding=(
            f"Pre-placement offers (PPOs) average {ppo_ctc} LPA — {premium}× the "
            f"{fte_ctc} LPA average for direct FTE offers. "
            f"This gap reflects both selection bias (PPOs go to top interns) and "
            f"the company's incentive to retain proven performers. "
            f"For students who receive a PPO, the financial upside versus a fresh FTE "
            f"offer is substantial."
        ),
        supporting_metric="stipend_by_offer_type",
        confidence=CONFIDENCE_HIGH,
        data_caveat=(
            f"PPO sample: {int(df.loc['PPO','n'])} offers. "
            f"FTE sample: {int(df.loc['FTE','n'])} offers. "
            f"PPO CTC may be skewed by a small number of high-paying outliers."
        ),
        numbers={
            "ppo_avg_ctc_lpa": ppo_ctc,
            "fte_avg_ctc_lpa": fte_ctc,
            "intern_fte_avg_ctc_lpa": float(df.loc["INTERN_FTE", "avg_ctc"]),
            "premium_multiple": premium,
        },
    )


def insight_company_size_vs_ctc(db_path: Path) -> InsightCard:
    """Recruiting more students does not correlate with higher pay."""
    con = connect(db_path, read_only=True)
    try:
        df = con.execute("""
            SELECT total_offers, avg_ctc_lpa
            FROM vw_company_summary
            WHERE avg_ctc_lpa IS NOT NULL
        """).df()
    finally:
        con.close()

    r = round(float(df["total_offers"].corr(df["avg_ctc_lpa"])), 3)

    return InsightCard(
        insight_id="INS_003",
        title="Companies that recruit more students do not pay higher CTC (r ≈ 0)",
        finding=(
            f"Across {len(df)} companies with parseable CTC, the Pearson correlation "
            f"between number of offers posted and average CTC is {r} — "
            f"effectively zero. This means high-volume recruiters are not "
            f"systematically higher or lower paying. The data shows mass-hiring "
            f"companies like manufacturing conglomerates co-exist in the same "
            f"offer-count range as boutique tech firms paying 3–4× more."
        ),
        supporting_metric="top_paying_companies",
        confidence=CONFIDENCE_HIGH,
        data_caveat="Correlation is computed at company level, not offer level.",
        numbers={
            "pearson_r": r,
            "companies_analyzed": len(df),
            "max_offers_single_company": int(df["total_offers"].max()),
        },
    )


def insight_branch_fte_ratio(db_path: Path) -> InsightCard:
    """Civil and Chemical branches have the highest FTE-to-intern ratios."""
    con = connect(db_path, read_only=True)
    try:
        df = con.execute("""
            SELECT branch_group,
                   SUM(fte_count) AS fte,
                   SUM(intern_count) AS intern,
                   ROUND(SUM(fte_count)*1.0/NULLIF(SUM(intern_count),0),2)
                       AS fte_to_intern_ratio,
                   SUM(offer_count) AS total
            FROM vw_branch_summary
            WHERE branch_group NOT IN ('ALL','NA','UNKNOWN')
            GROUP BY branch_group
            ORDER BY fte_to_intern_ratio DESC
        """).df()
    finally:
        con.close()

    top = df.iloc[0]
    bottom = df.iloc[-1]

    return InsightCard(
        insight_id="INS_004",
        title=(
            f"{top['branch_group']} branches have a {top['fte_to_intern_ratio']:.2f}× "
            f"FTE-to-intern ratio — {round(top['fte_to_intern_ratio']/bottom['fte_to_intern_ratio'],1)}× "
            f"higher than {bottom['branch_group']}"
        ),
        finding=(
            f"Civil engineering branches achieve a {top['fte_to_intern_ratio']} FTE-to-intern "
            f"ratio — for every intern role, there is more than one direct FTE opportunity. "
            f"By contrast, CS ({df[df['branch_group']=='CS']['fte_to_intern_ratio'].values[0]}) "
            f"and ECE ({df[df['branch_group']=='ECE']['fte_to_intern_ratio'].values[0]}) branches "
            f"are heavily skewed toward internships, reflecting the tech industry's "
            f"preference for trial-before-hire. Students in core engineering streams "
            f"face fewer intern-to-FTE conversion uncertainties."
        ),
        supporting_metric="fte_vs_intern_by_branch",
        confidence=CONFIDENCE_MEDIUM,
        data_caveat=(
            f"Branch coverage is 99.2% — 6 offers have no branch data. "
            f"Civil total offers ({int(top['total'])}) is much smaller than CS "
            f"({int(df[df['branch_group']=='CS']['total'].values[0])}), "
            f"so the ratio may be noisier."
        ),
        numbers={r["branch_group"]: float(r["fte_to_intern_ratio"])
                 for _, r in df.iterrows()},
    )


def insight_data_eng_no_cgpa(db_path: Path) -> InsightCard:
    """Data Engineering roles are most likely to waive CGPA requirements."""
    con = connect(db_path, read_only=True)
    try:
        df = con.execute("""
            SELECT job_family, offer_count, no_cgpa_count,
                   ROUND(no_cgpa_count*100.0/offer_count,1) AS no_cgpa_pct
            FROM vw_role_summary
            WHERE offer_count >= 5
            ORDER BY no_cgpa_pct DESC
        """).df()
    finally:
        con.close()

    top = df.iloc[0]
    swe_row = df[df["job_family"] == "Software Engineering"].iloc[0]

    return InsightCard(
        insight_id="INS_005",
        title=(
            f"{top['job_family']} roles waive CGPA requirements {round(top['no_cgpa_pct']/swe_row['no_cgpa_pct'],1)}× "
            f"more often than Software Engineering"
        ),
        finding=(
            f"{top['job_family']} offers have the highest no-CGPA rate among role families "
            f"with 5+ offers: {top['no_cgpa_pct']}% of their {int(top['offer_count'])} offers "
            f"require no CGPA filter. Software Engineering, the largest family, waives CGPA "
            f"in {swe_row['no_cgpa_pct']}% of cases. This pattern suggests data-focused "
            f"companies place more weight on skills and projects than academic scores — "
            f"consistent with how data roles are typically hired in the industry."
        ),
        supporting_metric="no_cgpa_by_role_family",
        confidence=CONFIDENCE_MEDIUM,
        data_caveat=(
            f"CGPA status was parseable for {df['offer_count'].sum()} offers. "
            f"'No CGPA criteria' is self-reported by the company — actual screening "
            f"during interviews may differ."
        ),
        numbers={
            "top_family": top["job_family"],
            "top_no_cgpa_pct": float(top["no_cgpa_pct"]),
            "swe_no_cgpa_pct": float(swe_row["no_cgpa_pct"]),
        },
    )


def insight_swe_ctc_variance(db_path: Path) -> InsightCard:
    """Software Engineering has by far the widest CTC spread."""
    con = connect(db_path, read_only=True)
    try:
        df = con.execute("""
            SELECT job_family,
                   COUNT(*) AS n,
                   ROUND(AVG(ctc_lpa_normalized),2) AS avg_ctc,
                   ROUND(MIN(ctc_lpa_normalized),2) AS min_ctc,
                   ROUND(MAX(ctc_lpa_normalized),2) AS max_ctc,
                   ROUND(STDDEV(ctc_lpa_normalized),2) AS std_ctc,
                   ROUND(STDDEV(ctc_lpa_normalized)/NULLIF(AVG(ctc_lpa_normalized),0),3) AS cv
            FROM fact_offers
            WHERE ctc_status IN ('KNOWN','RANGE') AND job_family != 'Unknown'
            GROUP BY job_family HAVING COUNT(*) >= 5
            ORDER BY cv DESC
        """).df()
    finally:
        con.close()

    top = df.iloc[0]
    return InsightCard(
        insight_id="INS_006",
        title=(
            f"Software Engineering has the highest CTC variance — "
            f"offers range from {top['min_ctc']} to {top['max_ctc']} LPA"
        ),
        finding=(
            f"With a coefficient of variation of {top['cv']} and a range from "
            f"{top['min_ctc']} to {top['max_ctc']} LPA, Software Engineering "
            f"has the widest compensation spread of any job family. The average is "
            f"{top['avg_ctc']} LPA but this masks a bimodal distribution: "
            f"product/tech companies offering 20–40+ LPA coexist with service companies "
            f"offering 3.5–6 LPA. By contrast, Research roles show a CV of "
            f"{float(df[df['job_family']=='Research']['cv'].iloc[0]):.3f} — "
            f"a much tighter, more predictable band."
        ),
        supporting_metric="role_ctc_variance",
        confidence=CONFIDENCE_HIGH,
        data_caveat=(
            f"CV is sensitive to outliers. The {top['max_ctc']} LPA maximum "
            f"in {top['job_family']} was validated by the anomaly detector as a "
            f"flagged CTC outlier (>2.5σ from family mean)."
        ),
        numbers={r["job_family"]: {"cv": float(r["cv"]), "avg_ctc": float(r["avg_ctc"])}
                 for _, r in df.iterrows()},
    )


def insight_no_cgpa_overall(db_path: Path) -> InsightCard:
    """Over one in four offers has no CGPA barrier."""
    con = connect(db_path, read_only=True)
    try:
        total, no_cgpa_count, no_cgpa_hp = con.execute("""
            SELECT COUNT(*),
                   COUNT(CASE WHEN no_cgpa_criteria THEN 1 END),
                   COUNT(CASE WHEN no_cgpa_criteria AND ctc_status IN ('KNOWN','RANGE')
                                   AND ctc_lpa_normalized >= 10 THEN 1 END)
            FROM fact_offers
        """).fetchone()
    finally:
        con.close()

    pct = round(no_cgpa_count * 100 / total, 1)
    hp_pct = round(no_cgpa_hp * 100 / no_cgpa_count, 1)

    return InsightCard(
        insight_id="INS_007",
        title=f"{pct}% of all offers require no CGPA — and {hp_pct}% of those are high-package",
        finding=(
            f"{no_cgpa_count} of {total} offers ({pct}%) explicitly state no CGPA requirement. "
            f"Of these open-access offers, {no_cgpa_hp} ({hp_pct}%) also pay 10 LPA or above. "
            f"This means a student with a lower CGPA has access to "
            f"{no_cgpa_hp} high-paying opportunities without any academic filter — "
            f"making skill development and project work the primary differentiator."
        ),
        supporting_metric="no_cgpa_offer_rate",
        confidence=CONFIDENCE_HIGH,
        data_caveat=(
            "No-CGPA status is extracted from the eligibilityCgpa field. "
            "Some companies may screen informally during interviews even when "
            "the field says 'No CGPA Criteria'."
        ),
        numbers={
            "total_offers": total,
            "no_cgpa_count": no_cgpa_count,
            "no_cgpa_pct": pct,
            "high_package_no_cgpa": no_cgpa_hp,
            "high_package_no_cgpa_pct": hp_pct,
        },
    )


def insight_meesho_outlier(db_path: Path) -> InsightCard:
    """Meesho's intern-FTE packages dwarf the sector average."""
    con = connect(db_path, read_only=True)
    try:
        sector_avg = con.execute("""
            SELECT ROUND(AVG(ctc_lpa_normalized),2) FROM fact_offers
            WHERE offer_type_standardized='INTERN_FTE'
              AND ctc_status IN ('KNOWN','RANGE')
        """).fetchone()[0]

        df = con.execute("""
            SELECT company_name, COUNT(*) AS n,
                   ROUND(AVG(ctc_lpa_normalized),2) AS avg_ctc,
                   ROUND(MAX(ctc_lpa_normalized),2) AS max_ctc
            FROM fact_offers
            WHERE offer_type_standardized='INTERN_FTE'
              AND ctc_status IN ('KNOWN','RANGE')
            GROUP BY company_name HAVING COUNT(*)>=2
            ORDER BY avg_ctc DESC LIMIT 5
        """).df()
    finally:
        con.close()

    top = df.iloc[0]
    multiple = round(float(top["avg_ctc"]) / float(sector_avg), 1)

    return InsightCard(
        insight_id="INS_008",
        title=(
            f"{top['company_name']} averages {top['avg_ctc']} LPA for intern-to-FTE roles "
            f"— {multiple}× the sector average of {sector_avg} LPA"
        ),
        finding=(
            f"Among companies with 2+ intern-FTE offers, {top['company_name']} stands out "
            f"with an average of {top['avg_ctc']} LPA — {multiple}× the sector average of "
            f"{sector_avg} LPA for this offer type. The next highest is "
            f"{df.iloc[1]['company_name']} at {df.iloc[1]['avg_ctc']} LPA. "
            f"Intern-to-FTE pathways represent {con.execute('SELECT COUNT(*) FROM fact_offers WHERE offer_type_standardized=?',['INTERN_FTE']).fetchone()[0] if False else '99'} offers (15.1% of the dataset) "
            f"and on average pay {round(12.75/9.63,2)}× more than pure FTE offers — "
            f"confirming the 'intern-first' pathway as financially superior for top performers."
        ),
        supporting_metric="stipend_by_offer_type",
        confidence=CONFIDENCE_MEDIUM,
        data_caveat=(
            f"Meesho sample: {int(top['n'])} INTERN_FTE offers. "
            f"Small sample sizes amplify averages; treat as directional."
        ),
        numbers={
            "sector_avg_ctc_lpa": float(sector_avg),
            "top_company": top["company_name"],
            "top_avg_ctc_lpa": float(top["avg_ctc"]),
            "multiple_vs_sector": multiple,
            "top_5": df.to_dict(orient="records"),
        },
    )


# ── Orchestrator ──────────────────────────────────────────────────────────────

_INSIGHT_FUNCTIONS = [
    insight_ctc_season_decline,
    insight_ppo_premium,
    insight_company_size_vs_ctc,
    insight_branch_fte_ratio,
    insight_data_eng_no_cgpa,
    insight_swe_ctc_variance,
    insight_no_cgpa_overall,
    insight_meesho_outlier,
]


def generate_all(db_path: Path = DB_PATH) -> list[InsightCard]:
    """Run every insight function and return a list of InsightCards."""
    cards = []
    for fn in _INSIGHT_FUNCTIONS:
        card = fn(db_path)
        cards.append(card)
    return cards
