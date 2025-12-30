from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from src.ingestion.load_json import load_placements

RAW_PATH = Path("data/raw/placements.json")
OUTPUT_PATH = Path("data/processed/raw_flat_offers.parquet")

log = logging.getLogger(__name__)


def _make_offer_id(record_id: str, offer_index: int) -> str:
    """Deterministic 16-char hex ID reproducible across pipeline runs."""
    return hashlib.sha256(f"{record_id}:{offer_index}".encode()).hexdigest()[:16]


def _to_str(value: Any) -> str | None:
    """Coerce a JSON scalar to str, preserving None."""
    if value is None:
        return None
    return str(value)


def flatten_offers(records: list[dict[str, Any]]) -> pd.DataFrame:
    """Explode nested placement records into one row per offer.

    Raw values are never modified. Two provenance flags track whether
    branchesAllowed / eligibilityCgpa were inherited from the parent record
    (the 98-record spillover documented in docs/assumptions.md).
    """
    rows: list[dict[str, Any]] = []

    for record in records:
        record_id: str = record.get("id", "")
        company_name: str = record.get("companyName", "")
        notice_date_raw: str = record.get("noticeDate", "")

        created_at = record.get("_createdAt") or {}
        created_at_seconds = created_at.get("seconds")
        created_at_nanoseconds = created_at.get("nanoseconds")

        # Spillover fields present at the parent level on ~98 records
        parent_branches: list[str] | None = record.get("branchesAllowed")
        parent_cgpa: str | None = record.get("eligibilityCgpa")

        for offer_index, offer in enumerate(record.get("offers") or []):
            if not isinstance(offer, dict):
                continue

            # Offer-level value takes precedence; fall back to parent spillover
            branches_raw: list[str] = offer.get("branchesAllowed") or []
            branches_from_parent = False
            if not branches_raw and parent_branches:
                branches_raw = parent_branches
                branches_from_parent = True

            cgpa_raw: str | None = offer.get("eligibilityCgpa")
            cgpa_from_parent = False
            if cgpa_raw is None and parent_cgpa is not None:
                cgpa_raw = parent_cgpa
                cgpa_from_parent = True

            branchwise = offer.get("branchwiseBreakup")

            rows.append(
                {
                    "offer_id": _make_offer_id(record_id, offer_index),
                    "record_id": record_id,
                    "company_name": company_name,
                    "notice_date_raw": notice_date_raw,
                    "created_at_seconds": created_at_seconds,
                    "created_at_nanoseconds": created_at_nanoseconds,
                    # Offer classification
                    "offer_type_raw": offer.get("type"),
                    "job_role_raw": offer.get("jobRole"),
                    # Compensation — raw only, cleaning happens in Phase 3
                    "ctc_raw": offer.get("ctc"),
                    "has_ctc": offer.get("hasCTC"),
                    "ctc_note_raw": offer.get("ctcNote"),
                    "stipend_raw": offer.get("stipend"),
                    "has_stipend": offer.get("hasStipend"),
                    "stipend_note_raw": offer.get("stipendNote"),
                    # Eligibility — cast to str because JSON sometimes stores
                    # studentsSelected as an integer (e.g. 5 not "5")
                    "students_selected_raw": _to_str(offer.get("studentsSelected")),
                    "eligibility_cgpa_raw": cgpa_raw,
                    "eligibility_note_raw": offer.get("eligibilityNote"),
                    # Branches — kept as list; bridge table built in Phase 3
                    "branches_allowed_raw": branches_raw,
                    "branches_note_raw": offer.get("branchesNote"),
                    # Optional per-branch count breakdown stored as JSON string
                    "branchwise_breakup_raw": json.dumps(branchwise) if branchwise else None,
                    # Provenance flags
                    "branches_from_parent": branches_from_parent,
                    "cgpa_from_parent": cgpa_from_parent,
                }
            )

    return pd.DataFrame(rows)


def save_parquet(df: pd.DataFrame, path: Path = OUTPUT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    log.info("Saved %d rows → %s", len(df), path)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    records = load_placements(RAW_PATH)
    log.info("Loaded %d records", len(records))

    df = flatten_offers(records)
    log.info("Flattened to %d offer rows across %d columns", len(df), len(df.columns))

    save_parquet(df)


if __name__ == "__main__":
    main()
