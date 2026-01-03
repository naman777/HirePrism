from __future__ import annotations

import pandas as pd

# Branch codes that convey no useful information
_BRANCH_UNKNOWN = {"Not Known", ""}


def check_ctc_parseability(df: pd.DataFrame) -> float:
    """% of offers where CTC resolved to a numeric value (KNOWN or RANGE)."""
    return df["ctc_status"].isin(["KNOWN", "RANGE"]).mean()


def check_stipend_parseability(df: pd.DataFrame) -> float:
    """% of offers where stipend resolved to a numeric value (KNOWN or RANGE)."""
    return df["stipend_status"].isin(["KNOWN", "RANGE"]).mean()


def check_branch_coverage(df: pd.DataFrame) -> float:
    """% of offers with at least one recognized (non-unknown) branch code."""

    def _has_known(branches) -> bool:
        items = list(branches) if branches is not None else []
        return bool(items) and any(b not in _BRANCH_UNKNOWN for b in items)

    return df["branches_allowed_raw"].apply(_has_known).mean()


def check_role_standardization_rate(df: pd.DataFrame) -> float:
    """% of offers whose job_family resolved to a recognized family (not Unknown)."""
    return (df["job_family"] != "Unknown").mean()


def check_date_validity(df: pd.DataFrame) -> float:
    """% of notice_date values that parsed to a valid timestamp."""
    return df["notice_date"].notna().mean()


def check_cgpa_numeric_rate(df: pd.DataFrame) -> float:
    """% of offers where a numeric CGPA threshold was extracted."""
    return (df["eligibility_status"] == "KNOWN").mean()


# Registry used by the scorer — order determines report output order
ALL_CHECKS: dict[str, callable] = {
    "ctc_parseability": check_ctc_parseability,
    "stipend_parseability": check_stipend_parseability,
    "branch_coverage": check_branch_coverage,
    "role_standardization": check_role_standardization_rate,
    "date_validity": check_date_validity,
    "cgpa_numeric_rate": check_cgpa_numeric_rate,
}
