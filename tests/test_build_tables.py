from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from src.modeling.build_tables import build, connect

# Real DB built from actual parquet data — used for integration assertions
REAL_DB = Path("data/processed/placelytics.duckdb")

EXPECTED_TABLES = [
    "fact_offers",
    "bridge_offer_branches",
    "dim_role",
    "dim_branch",
    "dim_company",
]

EXPECTED_VIEWS = [
    "vw_high_package_offers",
    "vw_role_summary",
    "vw_branch_summary",
    "vw_company_summary",
    "vw_internship_summary",
    "vw_no_cgpa_offers",
    "vw_compensation_unknown",
]


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def db_path() -> Path:
    """Build a fresh DB in a temp file; yield its path; clean up after."""
    fd, path = tempfile.mkstemp(suffix=".duckdb")
    os.close(fd)
    p = Path(path)
    p.unlink()          # duckdb will create the file; pre-existence causes issues
    build(p)
    yield p
    p.unlink(missing_ok=True)
    Path(str(p) + ".wal").unlink(missing_ok=True)


@pytest.fixture(scope="module")
def con(db_path: Path):
    c = connect(db_path, read_only=True)
    yield c
    c.close()


# ── DB structure ──────────────────────────────────────────────────────────────


def test_all_tables_exist(con) -> None:
    names = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
    for t in EXPECTED_TABLES:
        assert t in names, f"Missing table: {t}"


def test_all_views_exist(con) -> None:
    names = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
    for v in EXPECTED_VIEWS:
        assert v in names, f"Missing view: {v}"


# ── Row counts ────────────────────────────────────────────────────────────────


def test_fact_offers_row_count(con) -> None:
    n = con.execute("SELECT COUNT(*) FROM fact_offers").fetchone()[0]
    assert n == 654


def test_bridge_row_count(con) -> None:
    n = con.execute("SELECT COUNT(*) FROM bridge_offer_branches").fetchone()[0]
    assert n == 3639


def test_dim_company_row_count(con) -> None:
    n = con.execute("SELECT COUNT(*) FROM dim_company").fetchone()[0]
    assert n == 386


def test_dim_branch_no_unknown(con) -> None:
    n = con.execute(
        "SELECT COUNT(*) FROM dim_branch WHERE branch_standardized IN ('UNKNOWN', 'NOT_APPLICABLE')"
    ).fetchone()[0]
    assert n == 0


# ── View correctness ──────────────────────────────────────────────────────────


def test_high_package_all_above_10_lpa(con) -> None:
    df = con.execute("SELECT ctc_lpa_normalized FROM vw_high_package_offers").df()
    assert (df["ctc_lpa_normalized"] >= 10.0).all()


def test_high_package_only_known_status(con) -> None:
    statuses = set(
        con.execute("SELECT DISTINCT ctc_status FROM vw_high_package_offers").df()["ctc_status"]
    )
    assert statuses.issubset({"KNOWN", "RANGE"})


def test_role_summary_has_all_families(con) -> None:
    families = set(
        con.execute("SELECT job_family FROM vw_role_summary").df()["job_family"]
    )
    assert "Software Engineering" in families
    assert "Engineering Trainee" in families


def test_branch_summary_no_unknown_codes(con) -> None:
    codes = set(
        con.execute("SELECT DISTINCT branch_standardized FROM vw_branch_summary").df()[
            "branch_standardized"
        ]
    )
    assert "UNKNOWN" not in codes
    assert "NOT_APPLICABLE" not in codes


def test_internship_summary_has_five_types(con) -> None:
    n = con.execute("SELECT COUNT(*) FROM vw_internship_summary").fetchone()[0]
    assert n == 5


def test_internship_pct_sums_to_100(con) -> None:
    total = con.execute("SELECT SUM(pct_of_total) FROM vw_internship_summary").fetchone()[0]
    assert abs(total - 100.0) < 0.2   # floating-point tolerance


def test_no_cgpa_offers_all_flagged(con) -> None:
    # Every row in the view must have no_cgpa_criteria = TRUE in fact_offers
    n = con.execute("""
        SELECT COUNT(*) FROM vw_no_cgpa_offers v
        JOIN fact_offers f USING (offer_id)
        WHERE f.no_cgpa_criteria = FALSE
    """).fetchone()[0]
    assert n == 0


def test_compensation_unknown_only_bad_statuses(con) -> None:
    statuses = set(
        con.execute("SELECT DISTINCT ctc_status FROM vw_compensation_unknown").df()["ctc_status"]
    )
    assert statuses.issubset({"PENDING", "MISSING", "UNKNOWN"})


def test_company_summary_row_count_matches_fact(con) -> None:
    n_summary = con.execute("SELECT COUNT(*) FROM vw_company_summary").fetchone()[0]
    n_distinct = con.execute(
        "SELECT COUNT(DISTINCT company_name) FROM fact_offers"
    ).fetchone()[0]
    assert n_summary == n_distinct


# ── KPI sanity checks ─────────────────────────────────────────────────────────


def test_avg_ctc_known_above_8_lpa(con) -> None:
    avg = con.execute("""
        SELECT AVG(ctc_lpa_normalized) FROM fact_offers
        WHERE ctc_status IN ('KNOWN', 'RANGE')
    """).fetchone()[0]
    assert avg > 8.0


def test_ppo_highest_avg_ctc(con) -> None:
    df = con.execute("SELECT * FROM vw_internship_summary").df()
    ppo_ctc = df.loc[df["offer_type_standardized"] == "PPO", "avg_ctc_lpa"].values[0]
    max_ctc = df["avg_ctc_lpa"].max()
    assert ppo_ctc == max_ctc


# ── Idempotency ───────────────────────────────────────────────────────────────


def test_rebuild_is_idempotent() -> None:
    # Use a completely isolated temp DB so no other connection conflicts
    fd, path = tempfile.mkstemp(suffix=".duckdb")
    os.close(fd)
    p = Path(path)
    p.unlink()
    try:
        build(p)
        build(p)   # second build must not raise
        con2 = connect(p, read_only=True)
        n = con2.execute("SELECT COUNT(*) FROM fact_offers").fetchone()[0]
        con2.close()
        assert n == 654
    finally:
        p.unlink(missing_ok=True)
        Path(str(p) + ".wal").unlink(missing_ok=True)


# ── connect() helper ──────────────────────────────────────────────────────────


def test_connect_read_only_raises_on_write(db_path: Path) -> None:
    import duckdb

    con_ro = connect(db_path, read_only=True)
    with pytest.raises(duckdb.InvalidInputException):
        con_ro.execute("CREATE TABLE _test_rw (x INT)")
    con_ro.close()
