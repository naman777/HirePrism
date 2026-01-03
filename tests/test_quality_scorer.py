from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from src.quality.checks import (
    ALL_CHECKS,
    check_branch_coverage,
    check_cgpa_numeric_rate,
    check_ctc_parseability,
    check_date_validity,
    check_role_standardization_rate,
    check_stipend_parseability,
)
from src.quality.report import load_history, save_report
from src.quality.scorer import FLAG_THRESHOLD, run_quality_checks

CLEAN_PATH = Path("data/processed/fact_offers_clean.parquet")


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def clean_df() -> pd.DataFrame:
    return pd.read_parquet(CLEAN_PATH)


@pytest.fixture()
def minimal_df() -> pd.DataFrame:
    """Minimal DataFrame with all columns the checks need."""
    import numpy as np

    return pd.DataFrame(
        {
            "ctc_status": ["KNOWN", "RANGE", "MISSING", "UNKNOWN", "PENDING"],
            "stipend_status": ["KNOWN", "MISSING", "RANGE", "UNKNOWN", "MISSING"],
            "branches_allowed_raw": [
                ["ECE", "COE"],
                ["Not Known"],
                [],
                ["COPC"],
                ["MEE"],
            ],
            "job_family": [
                "Software Engineering",
                "Unknown",
                "Data / Analytics",
                "Engineering Trainee",
                "Other",
            ],
            "notice_date": pd.to_datetime(
                ["2026-04-01", "2026-04-02", None, "2026-04-04", "2026-04-05"]
            ),
            "eligibility_status": ["KNOWN", "UNKNOWN", "NO_CRITERIA", "MISSING", "KNOWN"],
        }
    )


# ── Individual checks on minimal data ────────────────────────────────────────


def test_ctc_parseability_known_and_range(minimal_df) -> None:
    # 2 out of 5 are KNOWN or RANGE
    assert abs(check_ctc_parseability(minimal_df) - 2 / 5) < 1e-6


def test_stipend_parseability(minimal_df) -> None:
    # KNOWN + RANGE = 2 out of 5
    assert abs(check_stipend_parseability(minimal_df) - 2 / 5) < 1e-6


def test_branch_coverage_known_branches(minimal_df) -> None:
    # Row 0 (ECE, COE) = known; Row 1 (Not Known) = not known;
    # Row 2 (empty) = not known; Row 3 (COPC) = known; Row 4 (MEE) = known
    assert abs(check_branch_coverage(minimal_df) - 3 / 5) < 1e-6


def test_role_standardization_excludes_unknown(minimal_df) -> None:
    # 4 out of 5 are not "Unknown"
    assert abs(check_role_standardization_rate(minimal_df) - 4 / 5) < 1e-6


def test_date_validity_counts_non_null(minimal_df) -> None:
    # 4 out of 5 parsed correctly
    assert abs(check_date_validity(minimal_df) - 4 / 5) < 1e-6


def test_cgpa_numeric_rate(minimal_df) -> None:
    # Only "KNOWN" status rows (2 rows) count
    assert abs(check_cgpa_numeric_rate(minimal_df) - 2 / 5) < 1e-6


def test_all_checks_return_float_between_0_and_1(minimal_df) -> None:
    for name, fn in ALL_CHECKS.items():
        score = fn(minimal_df)
        assert isinstance(score, float), f"{name} did not return float"
        assert 0.0 <= score <= 1.0, f"{name} score {score} out of [0,1]"


# ── run_quality_checks on minimal data ───────────────────────────────────────


def test_report_has_required_keys(minimal_df) -> None:
    report = run_quality_checks(minimal_df)
    assert "run_timestamp" in report
    assert "total_offers" in report
    assert "scores" in report
    assert "overall_score" in report
    assert "flagged_issues" in report


def test_total_offers_matches_df_length(minimal_df) -> None:
    report = run_quality_checks(minimal_df)
    assert report["total_offers"] == len(minimal_df)


def test_scores_keys_match_all_checks(minimal_df) -> None:
    report = run_quality_checks(minimal_df)
    assert set(report["scores"].keys()) == set(ALL_CHECKS.keys())


def test_all_scores_in_range(minimal_df) -> None:
    report = run_quality_checks(minimal_df)
    for name, score in report["scores"].items():
        assert 0.0 <= score <= 1.0, f"{name}: {score}"


def test_overall_score_is_mean_of_scores(minimal_df) -> None:
    report = run_quality_checks(minimal_df)
    expected = sum(report["scores"].values()) / len(report["scores"])
    assert abs(report["overall_score"] - round(expected, 4)) < 1e-6


def test_flagged_issues_below_threshold(minimal_df) -> None:
    report = run_quality_checks(minimal_df)
    for issue in report["flagged_issues"]:
        assert issue["score"] < FLAG_THRESHOLD
        assert "check" in issue
        assert "severity" in issue
        assert "message" in issue


def test_timestamp_format(minimal_df) -> None:
    from datetime import datetime

    report = run_quality_checks(minimal_df)
    # Should parse without error
    datetime.strptime(report["run_timestamp"], "%Y-%m-%dT%H:%M:%S")


# ── Perfect and zero data edge cases ─────────────────────────────────────────


def test_perfect_data_no_flagged_issues() -> None:
    df = pd.DataFrame(
        {
            "ctc_status": ["KNOWN"] * 10,
            "stipend_status": ["KNOWN"] * 10,
            "branches_allowed_raw": [["ECE"]] * 10,
            "job_family": ["Software Engineering"] * 10,
            "notice_date": pd.to_datetime(["2026-04-01"] * 10),
            "eligibility_status": ["KNOWN"] * 10,
        }
    )
    report = run_quality_checks(df)
    assert report["overall_score"] == 1.0
    assert report["flagged_issues"] == []


def test_zero_data_all_flagged() -> None:
    df = pd.DataFrame(
        {
            "ctc_status": ["MISSING"] * 5,
            "stipend_status": ["MISSING"] * 5,
            "branches_allowed_raw": [[]] * 5,
            "job_family": ["Unknown"] * 5,
            "notice_date": [None] * 5,
            "eligibility_status": ["MISSING"] * 5,
        }
    )
    report = run_quality_checks(df)
    assert report["overall_score"] == 0.0
    assert len(report["flagged_issues"]) == len(ALL_CHECKS)


# ── Report persistence ────────────────────────────────────────────────────────


def test_save_report_creates_files(minimal_df) -> None:
    report = run_quality_checks(minimal_df)

    fd_r, report_path = tempfile.mkstemp(suffix=".json")
    fd_h, history_path = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd_r)
    os.close(fd_h)
    try:
        with (
            patch("src.quality.report.REPORT_PATH", Path(report_path)),
            patch("src.quality.report.HISTORY_PATH", Path(history_path)),
        ):
            save_report(report)

        saved = json.loads(Path(report_path).read_text())
        assert saved["total_offers"] == len(minimal_df)

        history = Path(history_path).read_text().strip().splitlines()
        assert len(history) == 1
        line = json.loads(history[0])
        assert "overall_score" in line
        assert "scores" in line
    finally:
        Path(report_path).unlink(missing_ok=True)
        Path(history_path).unlink(missing_ok=True)


def test_history_appends_across_runs(minimal_df) -> None:
    report = run_quality_checks(minimal_df)

    fd, history_path = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    try:
        with patch("src.quality.report.HISTORY_PATH", Path(history_path)):
            with patch("src.quality.report.REPORT_PATH", Path(history_path).with_suffix(".json")):
                save_report(report)
                save_report(report)

        lines = Path(history_path).read_text().strip().splitlines()
        assert len(lines) == 2
    finally:
        Path(history_path).unlink(missing_ok=True)
        Path(history_path).with_suffix(".json").unlink(missing_ok=True)


def test_load_history_returns_list(minimal_df) -> None:
    report = run_quality_checks(minimal_df)

    fd, history_path = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    try:
        with patch("src.quality.report.HISTORY_PATH", Path(history_path)):
            with patch("src.quality.report.REPORT_PATH", Path(history_path).with_suffix(".json")):
                save_report(report)

            history = load_history()

        assert isinstance(history, list)
        assert len(history) == 1
        assert history[0]["overall_score"] == report["overall_score"]
    finally:
        Path(history_path).unlink(missing_ok=True)
        Path(history_path).with_suffix(".json").unlink(missing_ok=True)


# ── Integration: run against real clean data ──────────────────────────────────


def test_real_data_ctc_parseability_above_80pct(clean_df) -> None:
    assert check_ctc_parseability(clean_df) > 0.80


def test_real_data_date_validity_is_perfect(clean_df) -> None:
    assert check_date_validity(clean_df) == 1.0


def test_real_data_role_standardization_above_90pct(clean_df) -> None:
    assert check_role_standardization_rate(clean_df) > 0.90


def test_real_data_branch_coverage_above_95pct(clean_df) -> None:
    assert check_branch_coverage(clean_df) > 0.95


def test_real_data_overall_score_in_range(clean_df) -> None:
    report = run_quality_checks(clean_df)
    assert 0.70 < report["overall_score"] < 1.0
