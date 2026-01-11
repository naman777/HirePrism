from __future__ import annotations

import json
import logging
from pathlib import Path

from src.insights.generator import generate_all
from src.insights.templates import render_report_markdown
from src.modeling.build_tables import DB_PATH

REPORT_JSON = Path("data/insights/insight_report.json")
REPORT_MD = Path("data/insights/insight_report.md")

log = logging.getLogger(__name__)


def build_insights(db_path: Path = DB_PATH) -> None:
    log.info("Generating insight cards…")
    cards = generate_all(db_path)
    log.info("Generated %d insight cards", len(cards))

    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)

    payload = [c.to_dict() for c in cards]
    REPORT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    log.info("Saved → %s", REPORT_JSON)

    md = render_report_markdown(cards)
    REPORT_MD.write_text(md, encoding="utf-8")
    log.info("Saved → %s", REPORT_MD)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    build_insights()
    log.info("Done.")


if __name__ == "__main__":
    main()
