from __future__ import annotations

import json

import pytest

from src.ingestion.flatten_offers import _make_offer_id, flatten_offers
from src.ingestion.load_json import RAW_PATH, load_placements


# ---------------------------------------------------------------------------
# _make_offer_id
# ---------------------------------------------------------------------------


def test_offer_id_is_deterministic() -> None:
    assert _make_offer_id("abc", 0) == _make_offer_id("abc", 0)


def test_offer_id_differs_by_index() -> None:
    assert _make_offer_id("abc", 0) != _make_offer_id("abc", 1)


def test_offer_id_differs_by_record() -> None:
    assert _make_offer_id("abc", 0) != _make_offer_id("xyz", 0)


def test_offer_id_is_16_chars() -> None:
    assert len(_make_offer_id("x", 0)) == 16


# ---------------------------------------------------------------------------
# flatten_offers — shape and volume
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def flat_df():
    records = load_placements(RAW_PATH)
    return flatten_offers(records)


def test_flat_row_count(flat_df) -> None:
    assert len(flat_df) == 654


def test_offer_ids_are_unique(flat_df) -> None:
    assert flat_df["offer_id"].nunique() == 654


def test_required_columns_present(flat_df) -> None:
    required = {
        "offer_id",
        "record_id",
        "company_name",
        "notice_date_raw",
        "created_at_seconds",
        "offer_type_raw",
        "job_role_raw",
        "ctc_raw",
        "has_ctc",
        "stipend_raw",
        "has_stipend",
        "students_selected_raw",
        "eligibility_cgpa_raw",
        "branches_allowed_raw",
        "branches_from_parent",
        "cgpa_from_parent",
    }
    assert required.issubset(set(flat_df.columns))


# ---------------------------------------------------------------------------
# flatten_offers — provenance flags
# ---------------------------------------------------------------------------


def test_branches_from_parent_flag_count(flat_df) -> None:
    # 98 parent records have spillover branchesAllowed.
    # Offers within those records that have no offer-level branches inherit it.
    assert flat_df["branches_from_parent"].sum() > 0


def test_cgpa_from_parent_flag_is_always_bool(flat_df) -> None:
    # cgpa_from_parent is False for all real offers (offer-level value always
    # present in the 98 parent-spillover records), but the column must exist.
    assert flat_df["cgpa_from_parent"].dtype == bool


# ---------------------------------------------------------------------------
# flatten_offers — raw values preserved
# ---------------------------------------------------------------------------


def test_branches_allowed_raw_is_always_list(flat_df) -> None:
    assert flat_df["branches_allowed_raw"].apply(lambda x: isinstance(x, list)).all()


def test_branchwise_breakup_is_valid_json_or_null(flat_df) -> None:
    for val in flat_df["branchwise_breakup_raw"].dropna():
        parsed = json.loads(val)
        assert isinstance(parsed, dict)


def test_ctc_raw_preserves_original_strings(flat_df) -> None:
    # Spot-check: known integer values from real data
    known_integers = {"411000", "920000", "600000"}
    found = set(flat_df["ctc_raw"].dropna().astype(str))
    assert known_integers & found, "Expected at least one known CTC integer string"


# ---------------------------------------------------------------------------
# flatten_offers — edge cases
# ---------------------------------------------------------------------------


def test_flatten_empty_records() -> None:
    df = flatten_offers([])
    assert len(df) == 0


def test_flatten_record_with_no_offers() -> None:
    records = [{"id": "x", "companyName": "Acme", "noticeDate": "01/01/2026",
                "_createdAt": {"seconds": 0, "nanoseconds": 0}, "offers": []}]
    df = flatten_offers(records)
    assert len(df) == 0


def test_flatten_single_offer_produces_one_row() -> None:
    records = [
        {
            "id": "r1",
            "companyName": "TestCo",
            "noticeDate": "15/04/2026",
            "_createdAt": {"seconds": 1000, "nanoseconds": 0},
            "offers": [
                {
                    "type": "FTE",
                    "jobRole": "Engineer",
                    "ctc": "1000000",
                    "hasCTC": True,
                    "ctcNote": "",
                    "stipend": "",
                    "hasStipend": False,
                    "stipendNote": "",
                    "studentsSelected": "5",
                    "eligibilityCgpa": "7.0",
                    "eligibilityNote": "",
                    "branchesAllowed": ["COE", "COPC"],
                    "branchesNote": "",
                    "branchwiseBreakup": None,
                }
            ],
        }
    ]
    df = flatten_offers(records)
    assert len(df) == 1
    assert df.iloc[0]["company_name"] == "TestCo"
    assert df.iloc[0]["ctc_raw"] == "1000000"
    assert df.iloc[0]["branches_allowed_raw"] == ["COE", "COPC"]
    assert df.iloc[0]["branches_from_parent"] == False  # noqa: E712


def test_parent_spillover_is_inherited() -> None:
    records = [
        {
            "id": "r2",
            "companyName": "SpillCo",
            "noticeDate": "01/01/2026",
            "_createdAt": {"seconds": 0, "nanoseconds": 0},
            # Parent-level spillover
            "branchesAllowed": ["ECE"],
            "eligibilityCgpa": "7.5",
            "offers": [
                {
                    "type": "Intern",
                    "jobRole": "Analyst",
                    "ctc": "",
                    "hasCTC": False,
                    "ctcNote": "",
                    "stipend": "15000",
                    "hasStipend": True,
                    "stipendNote": "",
                    "studentsSelected": "3",
                    # No offer-level branches or CGPA
                    "branchesAllowed": [],
                    "branchesNote": "",
                    "branchwiseBreakup": None,
                }
            ],
        }
    ]
    df = flatten_offers(records)
    assert df.iloc[0]["branches_allowed_raw"] == ["ECE"]
    assert df.iloc[0]["branches_from_parent"] == True  # noqa: E712
    assert df.iloc[0]["eligibility_cgpa_raw"] == "7.5"
    assert df.iloc[0]["cgpa_from_parent"] == True  # noqa: E712
