import json
import tempfile
from pathlib import Path

import pytest

from src.ingestion.load_json import RAW_PATH, load_placements, profile_placements


def _write_payload(payload: dict) -> Path:
    with tempfile.NamedTemporaryFile(
        "w", suffix=".json", delete=False, dir=Path.cwd(), encoding="utf-8"
    ) as file:
        file.write(json.dumps(payload))
        return Path(file.name)


def test_load_placements_rejects_missing_top_level_key() -> None:
    raw_path = _write_payload({"records": []})

    with pytest.raises(ValueError, match="top-level key 'placements'"):
        load_placements(raw_path)


def test_load_placements_rejects_non_list_placements() -> None:
    raw_path = _write_payload({"placements": {}})

    with pytest.raises(ValueError, match="'placements' to be a list"):
        load_placements(raw_path)


def test_load_placements_accepts_current_dataset() -> None:
    records = load_placements(RAW_PATH)
    assert len(records) == 461


def test_profile_placements_reports_current_raw_shape() -> None:
    records = load_placements(RAW_PATH)
    profile = profile_placements(records)

    assert profile["volume"]["record_count"] == 461
    assert profile["volume"]["offer_count"] == 654
    assert {
        "_createdAt",
        "companyName",
        "id",
        "noticeDate",
        "offers",
    }.issubset(profile["schema"]["record_keys"])
    assert {
        "branchesAllowed",
        "branchesNote",
        "branchwiseBreakup",
        "ctc",
        "ctcNote",
        "eligibilityCgpa",
        "eligibilityNote",
        "hasCTC",
        "hasStipend",
        "jobRole",
        "stipend",
        "stipendNote",
        "studentsSelected",
        "type",
    }.issubset(profile["schema"]["offer_keys"])
    assert profile["integrity_checks"]["notice_date_formats"] == {"DD/MM/YYYY": 461}
    assert profile["integrity_checks"]["created_at_shapes"] == {
        "dict(nanoseconds,seconds)": 461
    }
