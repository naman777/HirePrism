from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

REPORT_PATH = Path("data/quality/quality_report.json")
HISTORY_PATH = Path("data/quality/quality_history.jsonl")

log = logging.getLogger(__name__)


def save_report(report: dict[str, Any]) -> None:
    """Persist the quality report and append a summary line to the history log.

    quality_report.json    — full report, overwritten each run
    quality_history.jsonl  — one JSON line per run (timestamp + scores), append-only
    """
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    log.info("Report saved → %s", REPORT_PATH)

    history_line = {
        "run_timestamp": report["run_timestamp"],
        "total_offers": report["total_offers"],
        "overall_score": report["overall_score"],
        "scores": report["scores"],
    }
    with HISTORY_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(history_line) + "\n")
    log.info("History appended → %s", HISTORY_PATH)


def load_history() -> list[dict[str, Any]]:
    """Return all historical quality runs as a list of dicts (oldest first)."""
    if not HISTORY_PATH.exists():
        return []
    records = []
    with HISTORY_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records
