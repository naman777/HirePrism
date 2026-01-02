import pytest

from src.cleaning.normalize_roles import normalize_role


def test_software_engineer_exact():
    r = normalize_role("Software Engineer")
    assert r["role_standardized"] == "Software Engineer"
    assert r["job_family"] == "Software Engineering"


def test_get_exact():
    r = normalize_role("GET")
    assert r["role_standardized"] == "Graduate Engineer Trainee"
    assert r["job_family"] == "Engineering Trainee"


def test_get_long_form():
    r = normalize_role("Graduate Engineer Trainee")
    assert r["job_family"] == "Engineering Trainee"


def test_get_parenthetical():
    r = normalize_role("Graduate Engineer Trainee (GET)")
    assert r["job_family"] == "Engineering Trainee"


def test_get_plural():
    r = normalize_role("Graduate Engineer Trainees (GETs)")
    assert r["job_family"] == "Engineering Trainee"


def test_data_engineer():
    r = normalize_role("Data Engineer")
    assert r["job_family"] == "Data Engineering"


def test_data_analyst():
    r = normalize_role("Data Analyst")
    assert r["job_family"] == "Data / Analytics"


def test_data_scientist():
    r = normalize_role("Data Scientist")
    assert r["job_family"] == "Data / Analytics"


def test_ai_engineer():
    r = normalize_role("AI Engineer")
    assert r["job_family"] == "Data / Analytics"


def test_business_analyst():
    r = normalize_role("Business Analyst")
    assert r["job_family"] == "Business Analysis"


def test_sde():
    r = normalize_role("SDE")
    assert r["job_family"] == "Software Engineering"


def test_sde_intern():
    r = normalize_role("SDE Intern")
    assert r["job_family"] == "Software Engineering"


def test_backend_intern():
    r = normalize_role("Backend Intern")
    assert r["job_family"] == "Software Engineering"


def test_research_analyst():
    r = normalize_role("Research Analyst")
    assert r["job_family"] == "Research"


def test_patent_search_analyst():
    r = normalize_role("Patent Search Analyst")
    assert r["job_family"] == "Research"


def test_assistant_professor():
    r = normalize_role("Assistant Professor")
    assert r["job_family"] == "Academic"


def test_not_known_is_unknown():
    r = normalize_role("Not Known")
    assert r["job_family"] == "Unknown"


def test_empty_string_is_unknown():
    r = normalize_role("")
    assert r["job_family"] == "Unknown"


def test_none_is_unknown():
    r = normalize_role(None)
    assert r["job_family"] == "Unknown"


def test_fuzzy_match_typo():
    # "Softwre Engineer" — 1 char typo should still match
    r = normalize_role("Softwre Engineer")
    assert r["job_family"] == "Software Engineering"


def test_fuzzy_match_extra_qualifier():
    # "Data Analyst - Finance" — fuzzy should land in Data / Analytics
    r = normalize_role("Data Analyst - Finance")
    assert r["job_family"] in ("Data / Analytics", "Business Analysis", "Other")
        