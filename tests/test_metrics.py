from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.metrics.loader import MetricRegistry, load_registry
from src.metrics.executor import MetricExecutor

DEFINITIONS_DIR = Path("metrics/definitions")


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def registry() -> MetricRegistry:
    return load_registry(DEFINITIONS_DIR)


@pytest.fixture(scope="module")
def executor(registry: MetricRegistry) -> MetricExecutor:
    return MetricExecutor(registry=registry)


# ── Registry loading ──────────────────────────────────────────────────────────


def test_registry_loads_all_four_categories(registry: MetricRegistry) -> None:
    categories = {m.category for m in registry.all()}
    assert categories == {"compensation", "roles", "branches", "eligibility"}


def test_registry_has_at_least_20_metrics(registry: MetricRegistry) -> None:
    assert len(registry) >= 20


def test_all_metrics_have_required_fields(registry: MetricRegistry) -> None:
    for m in registry.all():
        assert m.name, f"Empty name in {m}"
        assert m.label, f"Empty label for {m.name}"
        assert m.description, f"Empty description for {m.name}"
        assert m.sql, f"Empty SQL for {m.name}"
        assert m.version, f"Empty version for {m.name}"


def test_no_duplicate_metric_names(registry: MetricRegistry) -> None:
    names = [m.name for m in registry.all()]
    assert len(names) == len(set(names))


def test_get_returns_correct_metric(registry: MetricRegistry) -> None:
    m = registry.get("high_package_rate")
    assert m.name == "high_package_rate"
    assert m.category == "compensation"
    assert "compensation" in m.tags or "kpi" in m.tags


def test_get_unknown_raises_key_error(registry: MetricRegistry) -> None:
    with pytest.raises(KeyError):
        registry.get("nonexistent_metric_xyz")


def test_by_tag_filters_correctly(registry: MetricRegistry) -> None:
    comp_metrics = registry.by_tag("compensation")
    assert len(comp_metrics) > 0
    for m in comp_metrics:
        assert "compensation" in m.tags


def test_by_category_returns_correct_subset(registry: MetricRegistry) -> None:
    branch_metrics = registry.by_category("branches")
    assert len(branch_metrics) >= 4
    for m in branch_metrics:
        assert m.category == "branches"


def test_contains_operator(registry: MetricRegistry) -> None:
    assert "avg_ctc_by_branch" in registry
    assert "fake_metric_xyz" not in registry


def test_names_returns_sorted_list(registry: MetricRegistry) -> None:
    names = registry.names()
    assert names == sorted(names)


# ── Executor: every metric runs and returns non-empty DataFrame ───────────────


@pytest.mark.parametrize("metric_name", [
    "avg_ctc_by_job_family",
    "avg_ctc_by_branch",
    "high_package_rate",
    "ctc_status_breakdown",
    "stipend_by_offer_type",
    "top_paying_companies",
    "ctc_over_time",
    "role_family_distribution",
    "top_roles_by_frequency",
    "avg_ctc_by_role_family",
    "role_ctc_variance",
    "no_cgpa_by_role_family",
    "offer_type_by_role_family",
    "branch_opportunity_count",
    "branch_group_distribution",
    "fte_vs_intern_by_branch",
    "branch_avg_ctc",
    "top_companies_by_branch",
    "no_cgpa_offer_rate",
    "cgpa_threshold_distribution",
    "eligibility_status_breakdown",
    "no_cgpa_by_company",
    "high_package_no_cgpa",
    "avg_cgpa_by_job_family",
])
def test_metric_returns_nonempty_dataframe(metric_name: str, executor: MetricExecutor) -> None:
    df = executor.run(metric_name)
    assert isinstance(df, pd.DataFrame), f"{metric_name} did not return DataFrame"
    assert len(df) > 0, f"{metric_name} returned empty DataFrame"


# ── Specific metric correctness ───────────────────────────────────────────────


def test_high_package_rate_columns(executor: MetricExecutor) -> None:
    df = executor.run("high_package_rate")
    assert "high_package_pct" in df.columns
    assert "high_package_count" in df.columns
    assert df.iloc[0]["high_package_pct"] > 0


def test_high_package_rate_above_40pct(executor: MetricExecutor) -> None:
    df = executor.run("high_package_rate")
    assert df.iloc[0]["high_package_pct"] > 40.0


def test_ctc_status_breakdown_has_all_statuses(executor: MetricExecutor) -> None:
    df = executor.run("ctc_status_breakdown")
    statuses = set(df["ctc_status"])
    assert {"KNOWN", "RANGE", "MISSING"}.issubset(statuses)


def test_ctc_status_pct_sums_to_100(executor: MetricExecutor) -> None:
    df = executor.run("ctc_status_breakdown")
    total = df["pct_of_total"].sum()
    assert abs(total - 100.0) < 0.2


def test_role_family_distribution_has_software_family(executor: MetricExecutor) -> None:
    df = executor.run("role_family_distribution")
    families = set(df["job_family"])
    assert "Software Engineering" in families


def test_branch_opportunity_no_unknown_codes(executor: MetricExecutor) -> None:
    df = executor.run("branch_opportunity_count")
    assert "UNKNOWN" not in set(df["branch_standardized"])
    assert "NOT_APPLICABLE" not in set(df["branch_standardized"])


def test_no_cgpa_offer_rate_between_0_and_100(executor: MetricExecutor) -> None:
    df = executor.run("no_cgpa_offer_rate")
    pct = df.iloc[0]["no_cgpa_pct"]
    assert 0 < pct < 100


def test_high_package_no_cgpa_all_above_10_lpa(executor: MetricExecutor) -> None:
    df = executor.run("high_package_no_cgpa")
    assert (df["ctc_lpa_normalized"] >= 10.0).all()


def test_avg_ctc_by_branch_ctc_positive(executor: MetricExecutor) -> None:
    df = executor.run("avg_ctc_by_branch")
    assert (df["avg_ctc_lpa"] > 0).all()


def test_run_all_returns_all_metrics(executor: MetricExecutor) -> None:
    results = executor.run_all()
    assert set(results.keys()) == set(executor.registry.names())


def test_run_by_tag_kpi(executor: MetricExecutor) -> None:
    results = executor.run_by_tag("kpi")
    assert len(results) >= 2
    for name, df in results.items():
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0
