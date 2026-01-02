from __future__ import annotations

from typing import Any

import pandas as pd

# Canonical mapping: raw branch code → (standardized, group)
# All 23 observed unique codes are listed explicitly.
BRANCH_MAP: dict[str, tuple[str, str]] = {
    # Computer Science family
    "COPC": ("COPC", "CS"),
    "COE": ("COE", "CS"),
    "COBS": ("COBS", "CS"),
    # Electronics / Electrical family
    "ENC": ("ENC", "ECE"),
    "ECE": ("ECE", "ECE"),
    "EEC": ("EEC", "ECE"),
    "EIC": ("EIC", "ECE"),
    "ELE": ("ELE", "ECE"),
    "EE": ("EE", "ECE"),
    # Mechanical family
    "MEC": ("MEC", "MECH"),
    "MEE": ("MEE", "MECH"),
    "ME": ("ME", "MECH"),
    # Civil
    "CIE": ("CIE", "CIVIL"),
    # Chemical
    "CHE": ("CHE", "CHEM"),
    # Bio / Medical
    "BME": ("BME", "BIO"),
    "BT": ("BT", "BIO"),
    # Postgraduate
    "M.E./MTech": ("ME_MTECH", "PG"),
    "M.E.": ("ME_PG", "PG"),
    "MCA": ("MCA", "PG"),
    "M.Sc.": ("MSC", "PG"),
    # Catch-all
    "B.E. All Branches": ("ALL", "ALL"),
    # Null / unknown
    "Not Applicable": ("NOT_APPLICABLE", "NA"),
    "Not Known": ("UNKNOWN", "UNKNOWN"),
}

_STANDARDIZED = {raw: std for raw, (std, _) in BRANCH_MAP.items()}
_GROUP = {raw: grp for raw, (_, grp) in BRANCH_MAP.items()}


def normalize_branch(raw: str) -> dict[str, str]:
    """Return standardized code and group for a single raw branch string."""
    std = _STANDARDIZED.get(raw, "UNKNOWN")
    grp = _GROUP.get(raw, "UNKNOWN")
    return {"branch_standardized": std, "branch_group": grp}


def build_bridge(df: pd.DataFrame) -> pd.DataFrame:
    """Explode branches_allowed_raw into one row per offer-branch pair.

    Output columns: offer_id, branch_raw, branch_standardized, branch_group
    """
    rows: list[dict[str, Any]] = []
    for _, row in df[["offer_id", "branches_allowed_raw"]].iterrows():
        raw_val = row["branches_allowed_raw"]
        branches: list[str] = list(raw_val) if raw_val is not None else []
        if len(branches) == 0:
            rows.append(
                {
                    "offer_id": row["offer_id"],
                    "branch_raw": None,
                    "branch_standardized": "UNKNOWN",
                    "branch_group": "UNKNOWN",
                }
            )
        else:
            for b in branches:
                norm = normalize_branch(b)
                rows.append(
                    {
                        "offer_id": row["offer_id"],
                        "branch_raw": b,
                        "branch_standardized": norm["branch_standardized"],
                        "branch_group": norm["branch_group"],
                    }
                )
    return pd.DataFrame(rows)
