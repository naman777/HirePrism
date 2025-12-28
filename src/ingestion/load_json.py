from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

RAW_PATH = Path("data/raw/placements.json")
TOP_LEVEL_KEY = "placements"

RECORD_FIELDS = ["id", "companyName", "noticeDate", "_createdAt", "offers"]
OFFER_FIELDS = [
    "stipend",
    "eligibilityCgpa",
    "studentsSelected",
    "branchesAllowed",
    "branchwiseBreakup",
    "ctcNote",
    "hasStipend",
    "type",
    "branchesNote",
    "stipendNote",
    "ctc",
    "hasCTC",
    "jobRole",
    "eligibilityNote",
]
VARIANT_FIELDS = [
    "jobRole",
    "ctc",
    "stipend",
    "studentsSelected",
    "eligibilityCgpa",
    "type",
]
NOTE_FIELDS = ["ctcNote", "stipendNote", "branchesNote", "eligibilityNote"]


def load_placements(path: Path | str = RAW_PATH) -> list[dict[str, Any]]:
    raw_path = Path(path)
    with raw_path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    if not isinstance(payload, dict):
        raise ValueError(
            f"Expected top-level JSON object, found {type(payload).__name__}."
        )

    if TOP_LEVEL_KEY not in payload:
        raise ValueError(f"Expected top-level key '{TOP_LEVEL_KEY}'.")

    records = payload[TOP_LEVEL_KEY]
    if not isinstance(records, list):
        raise ValueError(
            f"Expected '{TOP_LEVEL_KEY}' to be a list, found {type(records).__name__}."
        )

    if not all(isinstance(record, dict) for record in records):
        raise ValueError(f"Expected every item in '{TOP_LEVEL_KEY}' to be an object.")

    return records


def profile_placements(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(records, list):
        raise TypeError("records must be a list of placement objects")

    record_key_counter: Counter[str] = Counter()
    offer_key_counter: Counter[str] = Counter()
    record_field_missing: Counter[str] = Counter()
    offer_field_missing: Counter[str] = Counter()
    nested_shapes: dict[str, Counter[str]] = {
        "_createdAt": Counter(),
        "offers": Counter(),
        "branchesAllowed": Counter(),
    }
    value_counters: dict[str, Counter[str]] = {
        field: Counter() for field in [*VARIANT_FIELDS, "branchesAllowed"]
    }
    note_examples: dict[str, list[str]] = {field: [] for field in NOTE_FIELDS}
    note_non_empty_counts: Counter[str] = Counter()
    notice_date_formats: Counter[str] = Counter()
    created_at_shapes: Counter[str] = Counter()
    offers_per_record: list[int] = []
    branch_lengths: Counter[int] = Counter()
    offer_count = 0

    for record in records:
        record_key_counter.update(record.keys())
        offers = record.get("offers")
        nested_shapes["offers"][type(offers).__name__] += 1

        notice_date_formats[_classify_notice_date(record.get("noticeDate"))] += 1
        created_at_shapes[_describe_mapping(record.get("_createdAt"))] += 1

        current_offers = offers if isinstance(offers, list) else []
        offers_per_record.append(len(current_offers))

        for offer in current_offers:
            if not isinstance(offer, dict):
                continue

            offer_count += 1
            offer_key_counter.update(offer.keys())

            branches = offer.get("branchesAllowed")
            nested_shapes["branchesAllowed"][type(branches).__name__] += 1
            branch_lengths[len(branches or [])] += 1

            for field in VARIANT_FIELDS:
                value_counters[field][_stringify_value(offer.get(field))] += 1

            for branch in branches or []:
                value_counters["branchesAllowed"][_stringify_value(branch)] += 1

            for field in NOTE_FIELDS:
                value = offer.get(field)
                if _is_missing(value):
                    continue
                note_non_empty_counts[field] += 1
                note_examples[field] = _append_unique(note_examples[field], str(value))

    all_record_fields = sorted(record_key_counter)
    all_offer_fields = sorted(offer_key_counter)
    record_field_missing = _count_record_missingness(records, all_record_fields)
    offer_field_missing = _count_offer_missingness(records, all_offer_fields)

    profile = {
        "schema": {
            "record_keys": all_record_fields,
            "offer_keys": all_offer_fields,
            "record_key_frequency": dict(sorted(record_key_counter.items())),
            "offer_key_frequency": dict(sorted(offer_key_counter.items())),
            "nested_field_shapes": {
                field: dict(counter) for field, counter in sorted(nested_shapes.items())
            },
        },
        "volume": {
            "record_count": len(records),
            "offer_count": offer_count,
            "offers_per_record": {
                "min": min(offers_per_record) if offers_per_record else 0,
                "max": max(offers_per_record) if offers_per_record else 0,
                "mean": (
                    round(sum(offers_per_record) / len(offers_per_record), 3)
                    if offers_per_record
                    else 0.0
                ),
                "distribution": {
                    str(key): value
                    for key, value in sorted(Counter(offers_per_record).items())
                },
            },
        },
        "missingness": {
            "record_level": _summarize_missingness(
                all_record_fields, record_field_missing, len(records)
            ),
            "offer_level": _summarize_missingness(
                all_offer_fields, offer_field_missing, offer_count
            ),
        },
        "variants": {
            field: _summarize_counter(counter)
            for field, counter in sorted(value_counters.items())
        },
        "format_variants": {
            field: _summarize_patterns(value_counters[field])
            for field in ("ctc", "stipend")
        },
        "notes": {
            field: {
                "non_empty_count": note_non_empty_counts[field],
                "non_empty_pct": (
                    round((note_non_empty_counts[field] / offer_count) * 100, 2)
                    if offer_count
                    else 0.0
                ),
                "example_values": note_examples[field],
            }
            for field in NOTE_FIELDS
        },
        "integrity_checks": {
            "notice_date_formats": dict(notice_date_formats),
            "created_at_shapes": dict(created_at_shapes),
        },
    }
    branches = profile["variants"]["branchesAllowed"]
    branches["list_length_distribution"] = {
        str(key): value for key, value in sorted(branch_lengths.items())
    }
    return profile


def _is_missing(value: Any) -> bool:
    return value in (None, "", [], {})


def _stringify_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    return str(value)


def _classify_notice_date(value: Any) -> str:
    if not value:
        return "EMPTY"
    if isinstance(value, str) and re.fullmatch(r"\d{2}/\d{2}/\d{4}", value):
        return "DD/MM/YYYY"
    return "OTHER"


def _describe_mapping(value: Any) -> str:
    if isinstance(value, dict):
        keys = ",".join(sorted(value.keys()))
        return f"dict({keys})"
    return type(value).__name__


def _append_unique(values: list[str], candidate: str, limit: int = 5) -> list[str]:
    if candidate not in values and len(values) < limit:
        values.append(candidate)
    return values


def _summarize_missingness(
    fields: list[str], missing_counter: Counter[str], total_count: int
) -> dict[str, dict[str, float]]:
    summary: dict[str, dict[str, float]] = {}
    for field in fields:
        missing_count = missing_counter.get(field, 0)
        summary[field] = {
            "missing_count": missing_count,
            "missing_pct": (
                round((missing_count / total_count) * 100, 2) if total_count else 0.0
            ),
        }
    return summary


def _count_record_missingness(
    records: list[dict[str, Any]], fields: list[str]
) -> Counter[str]:
    missing_counter: Counter[str] = Counter()
    for record in records:
        for field in fields:
            if _is_missing(record.get(field)):
                missing_counter[field] += 1
    return missing_counter


def _count_offer_missingness(
    records: list[dict[str, Any]], fields: list[str]
) -> Counter[str]:
    missing_counter: Counter[str] = Counter()
    for record in records:
        for offer in record.get("offers") or []:
            if not isinstance(offer, dict):
                continue
            for field in fields:
                if _is_missing(offer.get(field)):
                    missing_counter[field] += 1
    return missing_counter


def _summarize_counter(counter: Counter[str], limit: int = 15) -> dict[str, Any]:
    return {
        "unique_count": len(counter),
        "top_values": [
            {"value": value, "count": count}
            for value, count in counter.most_common(limit)
        ],
    }


def _classify_pattern(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return "EMPTY"

    lower = stripped.lower()
    if any(token in lower for token in ("not known", "not disclosed", "not declared")):
        return "UNKNOWN_TEXT"
    if any(
        token in lower
        for token in (
            "to be notified",
            "process pending",
            "pending",
            "negotiable",
            "to be discussed",
        )
    ):
        return "PENDING_TEXT"
    normalized = stripped.replace(",", "")
    if re.fullmatch(r"\d+", normalized):
        return "INTEGER"
    if "-" in stripped and re.search(r"\d", stripped):
        return "RANGE"
    if "lpa" in lower or "l.p.a" in lower:
        return "LPA_TEXT"
    return "OTHER"


def _summarize_patterns(
    counter: Counter[str], example_limit: int = 3
) -> dict[str, Any]:
    pattern_counts: Counter[str] = Counter()
    pattern_examples: dict[str, list[str]] = {}

    for raw_value, count in counter.items():
        pattern = _classify_pattern(raw_value)
        pattern_counts[pattern] += count
        pattern_examples.setdefault(pattern, [])
        if raw_value and raw_value not in pattern_examples[pattern]:
            if len(pattern_examples[pattern]) < example_limit:
                pattern_examples[pattern].append(raw_value)

    return {
        "pattern_counts": dict(pattern_counts),
        "pattern_examples": pattern_examples,
    }


def _build_smoke_summary(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_count": profile["volume"]["record_count"],
        "offer_count": profile["volume"]["offer_count"],
        "record_keys": profile["schema"]["record_keys"],
        "offer_keys": profile["schema"]["offer_keys"],
        "notice_date_formats": profile["integrity_checks"]["notice_date_formats"],
        "created_at_shapes": profile["integrity_checks"]["created_at_shapes"],
        "ctc_patterns": profile["format_variants"]["ctc"]["pattern_counts"],
        "stipend_patterns": profile["format_variants"]["stipend"]["pattern_counts"],
    }


def main() -> None:
    records = load_placements()
    profile = profile_placements(records)
    print(json.dumps(_build_smoke_summary(profile), indent=2))


if __name__ == "__main__":
    main()
