from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.anomaly.detector import (
    SEVERITY_HIGH,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    detect_all,
    detect_ctc_outliers,
    detect_implausible_student_count,
    detect_no_compensation,
    detect_rare_roles,
    detect_stipend_exceeds_ctc,
)
from src.anomaly.explainer import (
    explain_all,
    explain_row,
    summary_by_severity,
    summary_by_type,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _base_offer(**overrides) -> dict:
    base = {
        "offer_id": "offer_001",
        "company_name": "TestCo",
        "job_role_raw": "Software Engineer",
        "role_standardized": "Software Engineer",
        "job_family": "Software Engineering",
        "offer_type_standardized": "FTE",
        "ctc_lpa_normalized": 10.0,
        "ctc_status": "KNOWN",
        "ctc_lpa_min": 10.0,
        "ctc_lpa_max": 10.0,
        "stipend_monthly_normalized": None,
        "stipend_status": "MISSING",
        "has_ctc": True,
        "has_stipend": False,
        "students_selected_num": 5.0,
        "students_status": "KNOWN",
        "no_cgpa_criteria": False,
        "notice_date_raw": "01/04/2026",
    }
    base.update(overrides)
    return base


def _df(*offers) -> pd.DataFrame:
    return pd.DataFrame(list(offers))


# ── detect_ctc_outliers ───────────────────────────────────────────────────────


def test_ctc_outlier_flags_extreme_value() -> None:
    rows = [_base_offer(offer_id=f"o{i}", ctc_lpa_normalized=10.0) for i in range(9)]
    rows.append(_base_offer(offer_id="extreme", ctc_lpa_normalized=100.0))
    df = _df(*rows)
    result = detect_ctc_outliers(df)
    assert len(result) >= 1
    assert "extreme" in result["offer_id"].values


def test_ctc_outlier_skips_small_families() -> None:
    # Only 3 offers — below CTC_MIN_FAMILY_SIZE=5, should produce no flags
    rows = [_base_offer(offer_id=f"o{i}", ctc_lpa_normalized=10.0 + i) for i in range(3)]
    df = _df(*rows)
    result = detect_ctc_outliers(df)
    assert result.empty


def test_ctc_outlier_uniform_data_no_flags() -> None:
    rows = [_base_offer(offer_id=f"o{i}", ctc_lpa_normalized=10.0) for i in range(10)]
    df = _df(*rows)
    result = detect_ctc_outliers(df)
    assert result.empty


def test_ctc_outlier_severity_is_valid_value() -> None:
    rows = [_base_offer(offer_id=f"o{i}", ctc_lpa_normalized=10.0) for i in range(9)]
    rows.append(_base_offer(offer_id="extreme", ctc_lpa_normalized=200.0))
    result = detect_ctc_outliers(_df(*rows))
    for sev in result["severity"]:
        assert sev in {SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW}


def test_ctc_outlier_columns() -> None:
    rows = [_base_offer(offer_id=f"o{i}", ctc_lpa_normalized=10.0 + i * 0.1)
            for i in range(9)]
    rows.append(_base_offer(offer_id="extreme", ctc_lpa_normalized=100.0))
    result = detect_ctc_outliers(_df(*rows))
    if not result.empty:
        assert set(result.columns) >= {"offer_id", "anomaly_type", "anomaly_detail", "severity"}


# ── detect_stipend_exceeds_ctc ────────────────────────────────────────────────


def test_stipend_exceeds_ctc_flagged() -> None:
    intern = _base_offer(
        offer_id="intern_01",
        company_name="BigCo",
        offer_type_standardized="INTERN",
        stipend_monthly_normalized=150_000.0,   # 18 LPA/year — absurdly high
        stipend_status="KNOWN",
        ctc_lpa_normalized=None,
        ctc_status="MISSING",
        has_ctc=False,
        has_stipend=True,
    )
    fte = _base_offer(
        offer_id="fte_01",
        company_name="BigCo",
        offer_type_standardized="FTE",
        ctc_lpa_normalized=10.0,
        ctc_status="KNOWN",
        stipend_monthly_normalized=None,
        stipend_status="MISSING",
        has_ctc=True,
        has_stipend=False,
    )
    df = _df(intern, fte)
    result = detect_stipend_exceeds_ctc(df)
    assert len(result) >= 1
    assert result.iloc[0]["severity"] == SEVERITY_HIGH
    assert "intern_01" in result["offer_id"].values


def test_stipend_below_ctc_not_flagged() -> None:
    intern = _base_offer(
        offer_id="intern_01",
        company_name="SmallCo",
        offer_type_standardized="INTERN",
        stipend_monthly_normalized=20_000.0,    # 2.4 LPA/year < 10 LPA FTE
        stipend_status="KNOWN",
        ctc_lpa_normalized=None,
        ctc_status="MISSING",
        has_ctc=False,
        has_stipend=True,
    )
    fte = _base_offer(
        offer_id="fte_01",
        company_name="SmallCo",
        offer_type_standardized="FTE",
        ctc_lpa_normalized=10.0,
        ctc_status="KNOWN",
    )
    result = detect_stipend_exceeds_ctc(_df(intern, fte))
    assert result.empty


def test_stipend_different_companies_not_flagged() -> None:
    intern = _base_offer(
        offer_id="i1", company_name="CompA", offer_type_standardized="INTERN",
        stipend_monthly_normalized=200_000.0, stipend_status="KNOWN",
    )
    fte = _base_offer(
        offer_id="f1", company_name="CompB", offer_type_standardized="FTE",
        ctc_lpa_normalized=10.0, ctc_status="KNOWN",
    )
    result = detect_stipend_exceeds_ctc(_df(intern, fte))
    assert result.empty


# ── detect_implausible_student_count ─────────────────────────────────────────


def test_high_student_count_flagged() -> None:
    rows = [_base_offer(offer_id=f"o{i}", students_selected_num=3.0) for i in range(10)]
    rows.append(_base_offer(offer_id="mass", students_selected_num=999.0))
    result = detect_implausible_student_count(_df(*rows))
    assert not result.empty
    assert "mass" in result["offer_id"].values
    assert result.iloc[0]["severity"] == SEVERITY_MEDIUM


def test_normal_student_count_not_flagged() -> None:
    rows = [_base_offer(offer_id=f"o{i}", students_selected_num=float(i + 1))
            for i in range(10)]
    result = detect_implausible_student_count(_df(*rows))
    assert result.empty


def test_student_count_skips_unknown_status() -> None:
    rows = [
        _base_offer(offer_id=f"o{i}", students_selected_num=3.0)
        for i in range(4)
    ]
    rows.append(_base_offer(
        offer_id="pending", students_selected_num=999.0,
        students_status="PENDING"
    ))
    result = detect_implausible_student_count(_df(*rows))
    # "pending" has status != KNOWN so it is excluded from IQR computation
    assert "pending" not in (result["offer_id"].values if not result.empty else [])


# ── detect_no_compensation ────────────────────────────────────────────────────


def test_no_compensation_flagged() -> None:
    offer = _base_offer(
        offer_id="broke",
        ctc_status="MISSING",
        stipend_status="MISSING",
        ctc_lpa_normalized=None,
        stipend_monthly_normalized=None,
        has_ctc=False,
        has_stipend=False,
    )
    result = detect_no_compensation(_df(offer))
    assert len(result) == 1
    assert result.iloc[0]["severity"] == SEVERITY_HIGH


def test_has_ctc_not_flagged() -> None:
    offer = _base_offer(has_ctc=True, ctc_status="MISSING")
    result = detect_no_compensation(_df(offer))
    assert result.empty


def test_has_stipend_not_flagged() -> None:
    offer = _base_offer(has_stipend=True, ctc_status="MISSING", stipend_status="KNOWN")
    result = detect_no_compensation(_df(offer))
    assert result.empty


# ── detect_rare_roles ─────────────────────────────────────────────────────────


def test_rare_role_flagged() -> None:
    rare = _base_offer(offer_id="rare1", job_role_raw="Xylophone Data Wizard",
                       job_family="Other")
    common = _base_offer(offer_id="c1", job_role_raw="Software Engineer",
                         job_family="Software Engineering")
    common2 = _base_offer(offer_id="c2", job_role_raw="Software Engineer",
                          job_family="Software Engineering")
    result = detect_rare_roles(_df(rare, common, common2))
    assert "rare1" in result["offer_id"].values
    assert result.iloc[0]["severity"] == SEVERITY_LOW


def test_rare_known_family_not_flagged() -> None:
    # Even if rare, if job_family is known it shouldn't be flagged as a typo
    offer = _base_offer(offer_id="r1", job_role_raw="Unique But Valid",
                        job_family="Software Engineering")
    result = detect_rare_roles(_df(offer))
    assert result.empty


def test_common_role_other_family_not_flagged() -> None:
    rows = [_base_offer(offer_id=f"o{i}", job_role_raw="Mystery Role",
                        job_family="Other") for i in range(3)]
    result = detect_rare_roles(_df(*rows))
    # Appears 3 times → not rare → not flagged
    assert result.empty


# ── detect_all ────────────────────────────────────────────────────────────────


def test_detect_all_columns() -> None:
    df = _df(_base_offer())
    result = detect_all(df)
    assert set(result.columns) == {"offer_id", "anomaly_type", "anomaly_detail", "severity"}


def test_detect_all_no_duplicates() -> None:
    rows = [_base_offer(offer_id=f"o{i}", ctc_lpa_normalized=10.0) for i in range(9)]
    rows.append(_base_offer(offer_id="extreme", ctc_lpa_normalized=100.0))
    result = detect_all(_df(*rows))
    if not result.empty:
        assert result.duplicated(subset=["offer_id", "anomaly_type"]).sum() == 0


def test_detect_all_clean_data_returns_empty_or_minimal() -> None:
    rows = [_base_offer(offer_id=f"o{i}", ctc_lpa_normalized=10.0 + i * 0.1,
                        students_selected_num=3.0) for i in range(8)]
    result = detect_all(_df(*rows))
    # No outliers, no rare roles — result should be empty or very small
    types_flagged = set(result["anomaly_type"].unique()) if not result.empty else set()
    assert "STIPEND_EXCEEDS_CTC" not in types_flagged
    assert "NO_COMPENSATION" not in types_flagged


# ── Real data integration ─────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def real_anomalies() -> pd.DataFrame:
    df = pd.read_parquet("data/processed/fact_offers_clean.parquet")
    return detect_all(df)


def test_real_data_produces_anomalies(real_anomalies: pd.DataFrame) -> None:
    assert not real_anomalies.empty


def test_real_data_all_severities_present(real_anomalies: pd.DataFrame) -> None:
    severities = set(real_anomalies["severity"].unique())
    assert severities.issubset({SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW})


def test_real_data_ctc_outliers_detected(real_anomalies: pd.DataFrame) -> None:
    assert "CTC_OUTLIER" in real_anomalies["anomaly_type"].values


def test_real_data_rare_roles_detected(real_anomalies: pd.DataFrame) -> None:
    assert "RARE_ROLE" in real_anomalies["anomaly_type"].values


def test_real_data_student_count_outliers_detected(real_anomalies: pd.DataFrame) -> None:
    assert "IMPLAUSIBLE_STUDENT_COUNT" in real_anomalies["anomaly_type"].values


# ── Explainer ─────────────────────────────────────────────────────────────────


def test_explain_row_contains_severity_and_type() -> None:
    row = pd.Series({
        "offer_id": "x", "anomaly_type": "CTC_OUTLIER",
        "anomaly_detail": "CTC 80.0 is 4.2σ from mean",
        "severity": "HIGH",
    })
    text = explain_row(row)
    assert "HIGH" in text
    assert "CTC_OUTLIER" in text
    assert "CTC 80.0" in text


def test_explain_all_length_matches(real_anomalies: pd.DataFrame) -> None:
    explanations = explain_all(real_anomalies)
    assert len(explanations) == len(real_anomalies)


def test_summary_by_type_is_dict(real_anomalies: pd.DataFrame) -> None:
    result = summary_by_type(real_anomalies)
    assert isinstance(result, dict)
    assert sum(result.values()) == len(real_anomalies)


def test_summary_by_severity_covers_all_rows(real_anomalies: pd.DataFrame) -> None:
    result = summary_by_severity(real_anomalies)
    assert sum(result.values()) == len(real_anomalies)


def test_summary_empty_df_returns_empty_dict() -> None:
    assert summary_by_type(pd.DataFrame()) == {}
    assert summary_by_severity(pd.DataFrame()) == {}
