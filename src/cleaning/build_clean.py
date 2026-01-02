from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from src.cleaning.extract_notes import (
    extract_duration_months,
    extract_gross_ctc_signal,
    extract_location,
    extract_work_mode,
)
from src.cleaning.normalize_branches import build_bridge
from src.cleaning.normalize_roles import normalize_role
from src.cleaning.parse_ctc import parse_ctc
from src.cleaning.parse_dates import parse_created_at, parse_notice_date
from src.cleaning.parse_stipend import parse_stipend

FLAT_PATH = Path("data/processed/raw_flat_offers.parquet")
CLEAN_PATH = Path("data/processed/fact_offers_clean.parquet")
BRIDGE_PATH = Path("data/processed/bridge_offer_branches.parquet")

OFFER_TYPE_MAP = {
    "Intern+Performance Based Chance of FTE": "INTERN_POSSIBLE_FTE",
    "FTE": "FTE",
    "Intern+FTE": "INTERN_FTE",
    "Intern": "INTERN",
    "PPO (Summer Intern/Competition)": "PPO",
    "PPO from Summer Intern": "PPO",
}

log = logging.getLogger(__name__)


def build_clean(df: pd.DataFrame) -> pd.DataFrame:
    """Apply all cleaning modules to the flat offers DataFrame.

    Raw columns are preserved. Cleaned columns are added in parallel.
    """
    out = df.copy()

    # ── Dates ────────────────────────────────────────────────────────────────
    out["notice_date"] = out["notice_date_raw"].apply(parse_notice_date)
    out["created_at"] = out.apply(
        lambda r: parse_created_at(r["created_at_seconds"], r["created_at_nanoseconds"]),
        axis=1,
    )

    # ── Offer type ───────────────────────────────────────────────────────────
    out["offer_type_standardized"] = out["offer_type_raw"].map(OFFER_TYPE_MAP).fillna("OTHER")

    # ── CTC ──────────────────────────────────────────────────────────────────
    ctc_results = out["ctc_raw"].apply(parse_ctc)
    out["ctc_lpa_min"] = [r.min_lpa for r in ctc_results]
    out["ctc_lpa_max"] = [r.max_lpa for r in ctc_results]
    out["ctc_lpa_normalized"] = [r.normalized_lpa for r in ctc_results]
    out["ctc_status"] = [r.status for r in ctc_results]

    # ── Stipend ──────────────────────────────────────────────────────────────
    stip_results = out["stipend_raw"].apply(parse_stipend)
    out["stipend_monthly_min"] = [r.min_monthly for r in stip_results]
    out["stipend_monthly_max"] = [r.max_monthly for r in stip_results]
    out["stipend_monthly_normalized"] = [r.normalized_monthly for r in stip_results]
    out["stipend_status"] = [r.status for r in stip_results]

    # ── CGPA / eligibility ───────────────────────────────────────────────────
    out["no_cgpa_criteria"] = out["eligibility_cgpa_raw"].apply(_is_no_cgpa)
    out["eligibility_cgpa_num"] = out["eligibility_cgpa_raw"].apply(_parse_cgpa)
    out["eligibility_status"] = out.apply(_cgpa_status, axis=1)

    # ── Students selected ────────────────────────────────────────────────────
    out["students_selected_num"] = out["students_selected_raw"].apply(_parse_students)
    out["students_status"] = out["students_selected_raw"].apply(_students_status)

    # ── Roles ────────────────────────────────────────────────────────────────
    role_results = out["job_role_raw"].apply(normalize_role)
    out["role_standardized"] = [r["role_standardized"] for r in role_results]
    out["job_family"] = [r["job_family"] for r in role_results]

    # ── Notes extraction ─────────────────────────────────────────────────────
    # Parquet may load missing note values as NaN (float); normalize to str first
    ctc_notes = out["ctc_note_raw"].fillna("").astype(str)
    stipend_notes = out["stipend_note_raw"].fillna("").astype(str)
    combined_notes = ctc_notes + " " + stipend_notes
    out["location_extracted"] = combined_notes.apply(extract_location)
    out["work_mode_extracted"] = combined_notes.apply(extract_work_mode)
    out["duration_months_extracted"] = stipend_notes.apply(extract_duration_months)
    out["gross_ctc_signal"] = ctc_notes.apply(extract_gross_ctc_signal)

    return out


# ── Eligibility helpers ──────────────────────────────────────────────────────

_NO_CGPA_STRINGS = {"no cgpa criteria", "no cgpa bar", "no criteria", "no cgpa"}
_UNKNOWN_STRINGS = {"not known", "not declared", "not applicable", ""}


def _is_no_cgpa(raw: str | None) -> bool:
    if raw is None:
        return False
    return raw.strip().lower() in _NO_CGPA_STRINGS


def _parse_cgpa(raw: str | None) -> float | None:
    if raw is None or raw.strip() == "":
        return None
    try:
        val = float(raw.strip())
        if 0.0 <= val <= 10.0:
            return val
    except ValueError:
        pass
    return None


def _cgpa_status(row: pd.Series) -> str:
    raw = row["eligibility_cgpa_raw"]
    if raw is None or str(raw).strip() == "":
        return "MISSING"
    lower = str(raw).strip().lower()
    if lower in _NO_CGPA_STRINGS:
        return "NO_CRITERIA"
    if lower in _UNKNOWN_STRINGS:
        return "UNKNOWN"
    if row["eligibility_cgpa_num"] is not None:
        return "KNOWN"
    return "UNKNOWN"


# ── Students selected helpers ────────────────────────────────────────────────

_PENDING_STUDENT_TOKENS = ("process pending", "pending", "to be", "tbd", "not yet")
_UNKNOWN_STUDENT_TOKENS = ("not known", "not declared", "not disclosed", "not announced")


def _parse_students(raw: str | None) -> float | None:
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return float(str(raw).strip())
    except ValueError:
        return None


def _students_status(raw: str | None) -> str:
    if raw is None or str(raw).strip() == "":
        return "MISSING"
    lower = str(raw).strip().lower()
    for t in _PENDING_STUDENT_TOKENS:
        if t in lower:
            return "PENDING"
    for t in _UNKNOWN_STUDENT_TOKENS:
        if t in lower:
            return "UNKNOWN"
    try:
        float(raw.strip())
        return "KNOWN"
    except ValueError:
        return "UNKNOWN"


# ── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    flat = pd.read_parquet(FLAT_PATH)
    log.info("Loaded flat offers: %d rows", len(flat))

    clean = build_clean(flat)
    log.info("Cleaning complete: %d rows, %d columns", len(clean), len(clean.columns))

    # CTC summary
    ctc_counts = clean["ctc_status"].value_counts().to_dict()
    log.info("CTC status distribution: %s", ctc_counts)

    clean.to_parquet(CLEAN_PATH, index=False)
    log.info("Saved → %s", CLEAN_PATH)

    bridge = build_bridge(flat)
    bridge.to_parquet(BRIDGE_PATH, index=False)
    log.info("Bridge table: %d rows → %s", len(bridge), BRIDGE_PATH)


if __name__ == "__main__":
    main()
