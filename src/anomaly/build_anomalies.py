from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from src.anomaly.detector import detect_all
from src.anomaly.explainer import summary_by_severity, summary_by_type
from src.modeling.build_tables import DB_PATH, connect

CLEAN_PATH = Path("data/processed/fact_offers_clean.parquet")
SUMMARY_PATH = Path("data/quality/anomaly_summary.json")
VIEW_SQL = """
CREATE OR REPLACE VIEW vw_anomalies AS
SELECT
    a.offer_id,
    a.anomaly_type,
    a.anomaly_detail,
    a.severity,
    f.company_name,
    f.job_role_raw,
    f.offer_type_standardized,
    f.ctc_lpa_normalized,
    f.ctc_status,
    f.stipend_monthly_normalized,
    f.stipend_status,
    f.notice_date_raw
FROM anomaly_flags a
JOIN fact_offers f ON a.offer_id = f.offer_id
ORDER BY
    CASE a.severity WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END,
    a.anomaly_type
"""

log = logging.getLogger(__name__)


def build_anomalies(
    clean_path: Path = CLEAN_PATH,
    db_path: Path = DB_PATH,
) -> pd.DataFrame:
    """Detect anomalies, persist to DuckDB, save summary JSON, return DataFrame."""
    df = pd.read_parquet(clean_path)
    log.info("Loaded %d offers", len(df))

    anomalies = detect_all(df)
    log.info("Detected %d anomaly flags across %d offers",
             len(anomalies), anomalies["offer_id"].nunique() if not anomalies.empty else 0)

    _persist_to_db(anomalies, db_path)
    _save_summary(anomalies)

    return anomalies


def _persist_to_db(anomalies: pd.DataFrame, db_path: Path) -> None:
    con = connect(db_path)
    try:
        # Register the DataFrame as a temporary view so DuckDB can SELECT from it
        con.register("_anomalies_tmp", anomalies)
        con.execute("CREATE OR REPLACE TABLE anomaly_flags AS SELECT * FROM _anomalies_tmp")
        con.unregister("_anomalies_tmp")
        con.execute(VIEW_SQL)
        n = con.execute("SELECT COUNT(*) FROM vw_anomalies").fetchone()[0]
        log.info("vw_anomalies created with %d rows", n)
    finally:
        con.close()


def _save_summary(anomalies: pd.DataFrame) -> None:
    summary = {
        "total_flags": int(len(anomalies)),
        "flagged_offers": int(anomalies["offer_id"].nunique()) if not anomalies.empty else 0,
        "by_type": {k: int(v) for k, v in summary_by_type(anomalies).items()},
        "by_severity": {k: int(v) for k, v in summary_by_severity(anomalies).items()},
    }
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log.info("Anomaly summary saved → %s", SUMMARY_PATH)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    anomalies = build_anomalies()

    if anomalies.empty:
        log.info("No anomalies detected.")
        return

    print(f"\nTotal flags  : {len(anomalies)}")
    print(f"Flagged offers: {anomalies['offer_id'].nunique()}")
    print("\nBy type:")
    for t, n in summary_by_type(anomalies).items():
        print(f"  {t:<35} {n}")
    print("\nBy severity:")
    for s, n in summary_by_severity(anomalies).items():
        print(f"  {s:<10} {n}")


if __name__ == "__main__":
    main()
