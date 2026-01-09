from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

# ── Constants ─────────────────────────────────────────────────────────────────

CTC_Z_THRESHOLD = 2.5          # standard deviations from family mean
CTC_MIN_FAMILY_SIZE = 5        # skip families with too few samples for z-score
STUDENT_IQR_MULTIPLIER = 3.0   # upper fence = Q3 + k*IQR
RARE_ROLE_FREQUENCY = 1        # raw role appearances threshold

INTERN_TYPES = {"INTERN", "INTERN_FTE", "INTERN_POSSIBLE_FTE"}
KNOWN_CTC = {"KNOWN", "RANGE"}
KNOWN_STIPEND = {"KNOWN", "RANGE"}
MISSING_STATUS = {"MISSING", "UNKNOWN"}

SEVERITY_HIGH = "HIGH"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_LOW = "LOW"


# ── Individual detectors ──────────────────────────────────────────────────────


def detect_ctc_outliers(df: pd.DataFrame) -> pd.DataFrame:
    """Z-score outliers on CTC per job family (>2.5 std devs from the mean).

    Groups are built from offers with a parseable CTC. Families with fewer
    than CTC_MIN_FAMILY_SIZE parsed offers are skipped.
    """
    known = df[df["ctc_status"].isin(KNOWN_CTC)].copy()
    rows: list[dict[str, Any]] = []

    for family, group in known.groupby("job_family"):
        if len(group) < CTC_MIN_FAMILY_SIZE:
            continue
        z = np.abs(stats.zscore(group["ctc_lpa_normalized"].astype(float)))
        for idx, z_val in zip(group.index, z):
            if z_val > CTC_Z_THRESHOLD:
                row = group.loc[idx]
                rows.append(
                    _record(
                        offer_id=row["offer_id"],
                        anomaly_type="CTC_OUTLIER",
                        detail=(
                            f"CTC {row['ctc_lpa_normalized']:.2f} LPA is "
                            f"{z_val:.1f}σ from {family} mean "
                            f"(company: {row['company_name']})"
                        ),
                        severity=SEVERITY_HIGH if z_val > 3.5 else SEVERITY_MEDIUM,
                    )
                )

    return pd.DataFrame(rows)


def detect_stipend_exceeds_ctc(df: pd.DataFrame) -> pd.DataFrame:
    """Flags intern offers where annualised stipend exceeds an FTE CTC from
    the same company — a likely data-entry error or unit mismatch.

    Comparison: stipend_monthly * 12 / 100000 > fte_ctc_lpa_normalized
    """
    intern = df[
        df["offer_type_standardized"].isin(INTERN_TYPES)
        & df["stipend_status"].isin(KNOWN_STIPEND)
        & df["stipend_monthly_normalized"].notna()
    ].copy()
    intern["stipend_annual_lpa"] = intern["stipend_monthly_normalized"] * 12 / 100_000

    fte = df[
        (df["offer_type_standardized"] == "FTE")
        & df["ctc_status"].isin(KNOWN_CTC)
        & df["ctc_lpa_normalized"].notna()
    ][["company_name", "ctc_lpa_normalized"]].copy()

    merged = intern.merge(
        fte.rename(columns={"ctc_lpa_normalized": "fte_ctc_lpa"}),
        on="company_name",
        how="inner",
    )

    flagged = merged[merged["stipend_annual_lpa"] > merged["fte_ctc_lpa"]]
    rows = []
    for _, r in flagged.iterrows():
        rows.append(
            _record(
                offer_id=r["offer_id"],
                anomaly_type="STIPEND_EXCEEDS_CTC",
                detail=(
                    f"Intern stipend ₹{r['stipend_monthly_normalized']:,.0f}/mo "
                    f"(≈{r['stipend_annual_lpa']:.2f} LPA annual) exceeds "
                    f"FTE CTC {r['fte_ctc_lpa']:.2f} LPA at {r['company_name']}"
                ),
                severity=SEVERITY_HIGH,
            )
        )
    return pd.DataFrame(rows)


def detect_implausible_student_count(df: pd.DataFrame) -> pd.DataFrame:
    """IQR-based outlier on students_selected_num (upper fence = Q3 + 3*IQR).

    Very high student counts are suspicious unless the company is a large
    mass-recruiter, which is rare in this dataset.
    """
    known = df[df["students_status"] == "KNOWN"].copy()
    known = known[known["students_selected_num"].notna()]

    if len(known) < 4:
        return pd.DataFrame()

    q1 = known["students_selected_num"].quantile(0.25)
    q3 = known["students_selected_num"].quantile(0.75)
    iqr = q3 - q1
    upper_fence = q3 + STUDENT_IQR_MULTIPLIER * iqr

    outliers = known[known["students_selected_num"] > upper_fence]
    rows = []
    for _, r in outliers.iterrows():
        rows.append(
            _record(
                offer_id=r["offer_id"],
                anomaly_type="IMPLAUSIBLE_STUDENT_COUNT",
                detail=(
                    f"{int(r['students_selected_num'])} students selected "
                    f"(upper fence: {upper_fence:.0f}) "
                    f"at {r['company_name']} for {r['job_role_raw']}"
                ),
                severity=SEVERITY_MEDIUM,
            )
        )
    return pd.DataFrame(rows)


def detect_no_compensation(df: pd.DataFrame) -> pd.DataFrame:
    """Offers where both CTC and stipend are missing or unknown, and neither
    hasCTC nor hasStipend is True — no compensation signal at all.
    """
    flagged = df[
        df["ctc_status"].isin(MISSING_STATUS)
        & df["stipend_status"].isin(MISSING_STATUS)
        & (df["has_ctc"] == False)  # noqa: E712
        & (df["has_stipend"] == False)  # noqa: E712
    ]
    rows = []
    for _, r in flagged.iterrows():
        rows.append(
            _record(
                offer_id=r["offer_id"],
                anomaly_type="NO_COMPENSATION",
                detail=(
                    f"No CTC and no stipend for {r['offer_type_standardized']} "
                    f"offer at {r['company_name']} ({r['job_role_raw']})"
                ),
                severity=SEVERITY_HIGH,
            )
        )
    return pd.DataFrame(rows)


def detect_rare_roles(df: pd.DataFrame) -> pd.DataFrame:
    """Role names that appear exactly once AND fall into the 'Other' family —
    the strongest signal for a possible typo or non-standard entry.
    """
    role_counts = df["job_role_raw"].value_counts()
    rare = set(role_counts[role_counts <= RARE_ROLE_FREQUENCY].index)

    flagged = df[
        df["job_role_raw"].isin(rare)
        & (df["job_family"] == "Other")
        & df["job_role_raw"].notna()
        & (df["job_role_raw"] != "")
    ]
    rows = []
    for _, r in flagged.iterrows():
        rows.append(
            _record(
                offer_id=r["offer_id"],
                anomaly_type="RARE_ROLE",
                detail=(
                    f"Role '{r['job_role_raw']}' appears once and was not "
                    f"mapped to a known family (company: {r['company_name']})"
                ),
                severity=SEVERITY_LOW,
            )
        )
    return pd.DataFrame(rows)


# ── Orchestrator ──────────────────────────────────────────────────────────────

_DETECTORS = [
    detect_ctc_outliers,
    detect_stipend_exceeds_ctc,
    detect_implausible_student_count,
    detect_no_compensation,
    detect_rare_roles,
]

_ANOMALY_COLUMNS = ["offer_id", "anomaly_type", "anomaly_detail", "severity"]


def detect_all(df: pd.DataFrame) -> pd.DataFrame:
    """Run every detector and return a deduplicated anomaly DataFrame.

    Columns: offer_id, anomaly_type, anomaly_detail, severity
    One row per (offer_id, anomaly_type) pair.
    """
    parts = [fn(df) for fn in _DETECTORS]
    parts = [p for p in parts if not p.empty]

    if not parts:
        return pd.DataFrame(columns=_ANOMALY_COLUMNS)

    combined = pd.concat(parts, ignore_index=True)
    combined = combined.drop_duplicates(subset=["offer_id", "anomaly_type"])
    return combined[_ANOMALY_COLUMNS].reset_index(drop=True)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _record(offer_id: str, anomaly_type: str, detail: str, severity: str) -> dict[str, str]:
    return {
        "offer_id": offer_id,
        "anomaly_type": anomaly_type,
        "anomaly_detail": detail,
        "severity": severity,
    }
