from __future__ import annotations

import logging
from pathlib import Path

import duckdb

DB_PATH = Path("data/processed/HirePrism.duckdb")
FACT_PATH = Path("data/processed/fact_offers_clean.parquet")
BRIDGE_PATH = Path("data/processed/bridge_offer_branches.parquet")
VIEWS_DIR = Path("sql/views")

log = logging.getLogger(__name__)


def connect(db_path: Path = DB_PATH, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Return a connection to the persisted DuckDB database."""
    return duckdb.connect(str(db_path), read_only=read_only)


def build(db_path: Path = DB_PATH) -> None:
    """Build the full analytical model from processed parquet files.

    Idempotent — safe to re-run after any pipeline update.
    Step order:
      1. Load fact and bridge tables from parquet
      2. Derive dimension tables from the fact/bridge tables
      3. Execute all view SQL files from sql/views/
    """
    fact = FACT_PATH.as_posix()
    bridge = BRIDGE_PATH.as_posix()

    con = duckdb.connect(str(db_path))
    try:
        _load_base_tables(con, fact, bridge)
        _build_dim_tables(con)
        _create_views(con)
        row_counts = _verify(con)
        for table, count in row_counts.items():
            log.info("  %-30s %d rows", table, count)
    finally:
        con.close()


def _load_base_tables(con: duckdb.DuckDBPyConnection, fact: str, bridge: str) -> None:
    log.info("Loading base tables from parquet…")
    con.execute(f"""
        CREATE OR REPLACE TABLE fact_offers AS
        SELECT * FROM read_parquet('{fact}')
    """)
    log.info("  fact_offers loaded")

    con.execute(f"""
        CREATE OR REPLACE TABLE bridge_offer_branches AS
        SELECT * FROM read_parquet('{bridge}')
    """)
    log.info("  bridge_offer_branches loaded")


def _build_dim_tables(con: duckdb.DuckDBPyConnection) -> None:
    log.info("Building dimension tables…")

    con.execute("""
        CREATE OR REPLACE TABLE dim_role AS
        SELECT DISTINCT role_standardized, job_family
        FROM fact_offers
        WHERE role_standardized IS NOT NULL
        ORDER BY job_family, role_standardized
    """)

    con.execute("""
        CREATE OR REPLACE TABLE dim_branch AS
        SELECT DISTINCT branch_standardized, branch_group
        FROM bridge_offer_branches
        WHERE branch_standardized NOT IN ('UNKNOWN', 'NOT_APPLICABLE')
        ORDER BY branch_group, branch_standardized
    """)

    con.execute("""
        CREATE OR REPLACE TABLE dim_company AS
        SELECT
            company_name,
            COUNT(*)                                              AS total_offers,
            MIN(notice_date)                                      AS first_seen,
            MAX(notice_date)                                      AS last_seen,
            COUNT(DISTINCT offer_type_standardized)               AS distinct_offer_types
        FROM fact_offers
        GROUP BY company_name
        ORDER BY total_offers DESC
    """)

    log.info("  dim_role / dim_branch / dim_company created")


def _create_views(con: duckdb.DuckDBPyConnection) -> None:
    log.info("Creating analytical views…")
    view_files = sorted(VIEWS_DIR.glob("*.sql"))
    if not view_files:
        log.warning("No SQL files found in %s", VIEWS_DIR)
        return
    for sql_file in view_files:
        sql = sql_file.read_text(encoding="utf-8")
        con.execute(sql)
        log.info("  %s ✓", sql_file.name)


def _verify(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    tables = [
        "fact_offers",
        "bridge_offer_branches",
        "dim_role",
        "dim_branch",
        "dim_company",
        "vw_high_package_offers",
        "vw_role_summary",
        "vw_branch_summary",
        "vw_company_summary",
        "vw_internship_summary",
        "vw_no_cgpa_offers",
        "vw_compensation_unknown",
    ]
    counts = {}
    for t in tables:
        counts[t] = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    return counts


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log.info("Building DuckDB analytical model → %s", DB_PATH)
    build()
    log.info("Done.")


if __name__ == "__main__":
    main()
