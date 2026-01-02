from __future__ import annotations

import re
from dataclasses import dataclass, field

STATUS_MISSING = "MISSING"
STATUS_KNOWN = "KNOWN"
STATUS_RANGE = "RANGE"
STATUS_UNKNOWN = "UNKNOWN"

_UNKNOWN_TOKENS = (
    "not known",
    "not disclosed",
    "not declared",
    "not announced",
    "not specified",
)


@dataclass
class StipendResult:
    raw: str
    status: str
    min_monthly: float | None = field(default=None)
    max_monthly: float | None = field(default=None)
    normalized_monthly: float | None = field(default=None)


def parse_stipend(raw: str | None) -> StipendResult:
    """Parse a raw stipend string into structured monthly amounts and a status flag.

    All amounts are kept in rupees per month (not annualized).

    Status values:
      MISSING  — empty string or None
      KNOWN    — single numeric value parsed (includes Unpaid → 0)
      RANGE    — min and max both parsed; normalized is the midpoint
      UNKNOWN  — withheld or free text could not be parsed
    """
    if raw is None or str(raw).strip() == "":
        return StipendResult(raw="", status=STATUS_MISSING)

    stripped = str(raw).strip()
    lower = stripped.lower()

    if lower == "unpaid":
        return StipendResult(raw=stripped, status=STATUS_KNOWN, normalized_monthly=0.0)

    for token in _UNKNOWN_TOKENS:
        if token in lower:
            return StipendResult(raw=stripped, status=STATUS_UNKNOWN)

    # Normalize separators before number extraction
    normalized = _normalize_separators(stripped)

    # Degree-split: "17,500 (B.E.) / 25,000 (M.E./M.Sc./MBA)"
    if " / " in normalized:
        parts = normalized.split(" / ")
        amounts = [_extract_first_int(p) for p in parts]
        amounts = [a for a in amounts if a is not None]
        if len(amounts) >= 2:
            lo, hi = min(amounts), max(amounts)
            return StipendResult(
                raw=stripped,
                status=STATUS_RANGE,
                min_monthly=float(lo),
                max_monthly=float(hi),
                normalized_monthly=float((lo + hi) / 2),
            )
        if len(amounts) == 1:
            return StipendResult(
                raw=stripped,
                status=STATUS_KNOWN,
                normalized_monthly=float(amounts[0]),
            )

    # Range with hyphen or en-dash (already normalized to "-")
    no_commas = normalized.replace(",", "")
    range_match = re.search(r"(\d+)\s*-\s*(\d+)", no_commas)
    if range_match:
        a, b = int(range_match.group(1)), int(range_match.group(2))
        if a > 0 and b > 0 and a != b:
            lo, hi = min(a, b), max(a, b)
            return StipendResult(
                raw=stripped,
                status=STATUS_RANGE,
                min_monthly=float(lo),
                max_monthly=float(hi),
                normalized_monthly=float((lo + hi) / 2),
            )

    # Plain integer
    plain_match = re.fullmatch(r"\d+", no_commas.strip())
    if plain_match:
        val = int(no_commas.strip())
        return StipendResult(
            raw=stripped,
            status=STATUS_KNOWN,
            normalized_monthly=float(val),
        )

    return StipendResult(raw=stripped, status=STATUS_UNKNOWN)


def _normalize_separators(text: str) -> str:
    """Replace en-dash/em-dash with hyphen; normalize spaces around separators."""
    text = text.replace("–", "-").replace("—", "-")
    return text


def _extract_first_int(text: str) -> int | None:
    cleaned = text.replace(",", "")
    m = re.search(r"\b(\d{3,7})\b", cleaned)
    return int(m.group(1)) if m else None
