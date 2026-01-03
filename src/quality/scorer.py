from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.quality.checks import ALL_CHECKS

CLEAN_PATH = Path("data/processed/fact_offers_clean.parquet")

# Checks whose score falls below this threshold are surfaced as flagged issues
FLAG_THRESHOLD = 0.75

log = logging.getLogger(__name__)


def run_quality_checks(df: pd.DataFrame) -> dict[str, Any]:
    """Run all registered quality checks and return a structured report.

    Report schema::

        {
          "run_timestamp": "2026-04-24T10:00:00",
          "total_offers": 654,
          "scores": {
            "ctc_parseability": 0.8272,
            ...
          },
          "overall_score": 0.8571,
          "flagged_issues": [
            {"check": "stipend_parseability", "score": 0.6987,
             "severity": "MEDIUM", "message": "..."}
          ]
        }
    """
    scores: dict[str, float] = {}
    for name, fn in ALL_CHECKS.items():
        scores[name] = round(float(fn(df)), 4)

    overall = round(sum(scores.values()) / len(scores), 4)

    flagged: list[dict[str, Any]] = []
    for name, score in scores.items():
        if score < FLAG_THRESHOLD:
            flagged.append(
                {
                    "check": name,
                    "score": score,
                    "severity": _severity(score),
                    "message": _flag_message(name, score),
                }
            )

    return {
        "run_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "total_offers": int(len(df)),
        "scores": scores,
        "overall_score": overall,
        "flagged_issues": flagged,
    }


def _severity(score: float) -> str:
    if score < 0.50:
        return "HIGH"
    if score < 0.65:
        return "MEDIUM"
    return "LOW"


def _flag_message(check: str, score: float) -> str:
    pct = f"{score:.1%}"
    messages = {
        "ctc_parseability": f"Only {pct} of CTC values could be parsed to a numeric figure.",
        "stipend_parseability": f"Only {pct} of stipend values could be parsed — expected for FTE-only offers.",
        "branch_coverage": f"Only {pct} of offers have at least one recognized branch code.",
        "role_standardization": f"Only {pct} of roles mapped to a recognized job family.",
        "date_validity": f"Only {pct} of notice dates parsed successfully.",
        "cgpa_numeric_rate": f"Only {pct} of offers have a numeric CGPA threshold — rest use 'No Criteria' or are unknown.",
    }
    return messages.get(check, f"{check} scored {pct}, below threshold {FLAG_THRESHOLD:.0%}.")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    from src.quality.report import save_report

    df = pd.read_parquet(CLEAN_PATH)
    log.info("Loaded %d clean offers", len(df))

    report = run_quality_checks(df)
    save_report(report)

    log.info("Overall quality score: %.4f", report["overall_score"])
    if report["flagged_issues"]:
        log.info("Flagged issues:")
        for issue in report["flagged_issues"]:
            log.info("  [%s] %s", issue["severity"], issue["message"])
    else:
        log.info("No issues flagged.")

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
