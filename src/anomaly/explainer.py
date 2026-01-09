from __future__ import annotations

import pandas as pd

_TEMPLATES: dict[str, str] = {
    "CTC_OUTLIER": (
        "This offer's CTC is a statistical outlier relative to other offers in "
        "the same job family. Z-score analysis (scipy.stats.zscore per family) "
        "flagged it as more than 2.5 standard deviations from the group mean. "
        "Possible causes: genuinely exceptional package, data-entry error, or "
        "unit mismatch (e.g. monthly entered instead of annual)."
    ),
    "STIPEND_EXCEEDS_CTC": (
        "The intern stipend for this offer, when annualised, exceeds the full-time "
        "CTC offered by the same company. This is almost certainly a data-entry "
        "error — stipend may have been entered as a lump sum rather than monthly, "
        "or the CTC figure may be understated."
    ),
    "IMPLAUSIBLE_STUDENT_COUNT": (
        "The number of students selected is unusually high compared to the rest of "
        "the dataset. IQR-based analysis (Q3 + 3×IQR upper fence) flagged it. "
        "This could indicate a bulk/campus-wide drive that was entered per-offer "
        "rather than per-batch, or a data-entry error."
    ),
    "NO_COMPENSATION": (
        "This offer has neither a CTC nor a stipend — both hasCTC and hasStipend "
        "are False, and both fields are empty or unknown. The record may be "
        "incomplete or represent a non-compensated opportunity (e.g. an unpaid "
        "internship or an exploratory campus visit)."
    ),
    "RARE_ROLE": (
        "This job role title appears only once across the entire dataset and was "
        "not matched to any recognised role family. It may be a legitimate niche "
        "role, a typo, or a non-standard entry. Review the raw string for "
        "consistency with similar roles from the same company."
    ),
}

_SEVERITY_CONTEXT: dict[str, str] = {
    "HIGH": "Action recommended — likely a real data issue.",
    "MEDIUM": "Worth reviewing — may be a legitimate edge case or a data error.",
    "LOW": "Low priority — informational flag for awareness.",
}


def explain_row(row: pd.Series) -> str:
    """Return a human-readable explanation for a single anomaly row."""
    template = _TEMPLATES.get(row["anomaly_type"], "No explanation template available.")
    context = _SEVERITY_CONTEXT.get(row["severity"], "")
    return (
        f"[{row['severity']}] {row['anomaly_type']}\n"
        f"Detail: {row['anomaly_detail']}\n"
        f"Why flagged: {template}\n"
        f"Guidance: {context}"
    )


def explain_all(anomaly_df: pd.DataFrame) -> list[str]:
    """Return a list of explanation strings, one per anomaly row."""
    return [explain_row(row) for _, row in anomaly_df.iterrows()]


def summary_by_type(anomaly_df: pd.DataFrame) -> dict[str, int]:
    """Return a count of anomalies grouped by anomaly_type."""
    if anomaly_df.empty:
        return {}
    return anomaly_df["anomaly_type"].value_counts().to_dict()


def summary_by_severity(anomaly_df: pd.DataFrame) -> dict[str, int]:
    """Return a count of anomalies grouped by severity."""
    if anomaly_df.empty:
        return {}
    return anomaly_df["severity"].value_counts().to_dict()
