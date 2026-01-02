from __future__ import annotations

import re
from dataclasses import dataclass, field

RUPEES_PER_LPA = 100_000

STATUS_MISSING = "MISSING"
STATUS_KNOWN = "KNOWN"
STATUS_RANGE = "RANGE"
STATUS_PENDING = "PENDING"
STATUS_UNKNOWN = "UNKNOWN"

# Tokens that signal the CTC is not yet determined
_PENDING_TOKENS = (
    "to be notified",
    "to be discussed",
    "to be intimated",
    "will be communicated",
    "will be intimated",
    "will be discussed",
    "negotiable",
    "process pending",
    "yet to be",
    "performance dependent",
    "subject to performance",
    "subject to interview",
    "not announced yet",
    "not announced by",
    "not shared yet",
)

# Tokens that signal the CTC is intentionally withheld
_UNKNOWN_TOKENS = (
    "not known",
    "not disclosed",
    "not declared",
    "not announced",
    "not specified",
    "not applicable",
    "internship & fte",
    "max of stipend",
)


@dataclass
class CTCResult:
    raw: str
    status: str
    min_lpa: float | None = field(default=None)
    max_lpa: float | None = field(default=None)
    normalized_lpa: float | None = field(default=None)


def parse_ctc(raw: str | None) -> CTCResult:
    """Parse a raw CTC string into structured LPA fields and a status flag.

    Status values:
      MISSING  — empty string or None
      KNOWN    — single numeric value successfully parsed
      RANGE    — min and max both parsed; normalized_lpa is the midpoint
      PENDING  — value exists but is not yet determined (negotiable, TBN, etc.)
      UNKNOWN  — company deliberately withheld or free text could not be parsed
    """
    if raw is None or str(raw).strip() == "":
        return CTCResult(raw="", status=STATUS_MISSING)

    stripped = str(raw).strip()
    lower = stripped.lower()

    for token in _PENDING_TOKENS:
        if token in lower:
            return CTCResult(raw=stripped, status=STATUS_PENDING)

    for token in _UNKNOWN_TOKENS:
        if token in lower:
            return CTCResult(raw=stripped, status=STATUS_UNKNOWN)

    # Degree-split format: "6,56,000 (B.E.) / 7,36,000 (M.E./M.Sc./MBA)"
    if " / " in stripped:
        parts = stripped.split(" / ")
        amounts = [_extract_first_rupee_int(p) for p in parts]
        amounts = [a for a in amounts if a is not None]
        if len(amounts) >= 2:
            lo, hi = min(amounts), max(amounts)
            return CTCResult(
                raw=stripped,
                status=STATUS_RANGE,
                min_lpa=_to_lpa(lo),
                max_lpa=_to_lpa(hi),
                normalized_lpa=_to_lpa((lo + hi) / 2),
            )
        if len(amounts) == 1:
            return CTCResult(
                raw=stripped,
                status=STATUS_KNOWN,
                normalized_lpa=_to_lpa(amounts[0]),
            )

    # Range with hyphen or en-dash: "800000-1200000" or "12,00,000-16,00,000 (...)"
    no_commas = stripped.replace(",", "")
    range_match = re.search(r"(\d+)\s*[-–]\s*(\d+)", no_commas)
    if range_match:
        a, b = int(range_match.group(1)), int(range_match.group(2))
        if a > 0 and b > 0 and a != b:
            lo, hi = min(a, b), max(a, b)
            return CTCResult(
                raw=stripped,
                status=STATUS_RANGE,
                min_lpa=_to_lpa(lo),
                max_lpa=_to_lpa(hi),
                normalized_lpa=_to_lpa((lo + hi) / 2),
            )

    # Plain integer: "411000"
    plain_match = re.fullmatch(r"\d+", no_commas.strip())
    if plain_match:
        val = int(no_commas.strip())
        return CTCResult(
            raw=stripped,
            status=STATUS_KNOWN,
            normalized_lpa=_to_lpa(val),
        )

    return CTCResult(raw=stripped, status=STATUS_UNKNOWN)


def _extract_first_rupee_int(text: str) -> int | None:
    cleaned = text.replace(",", "")
    m = re.search(r"\b(\d{4,8})\b", cleaned)
    return int(m.group(1)) if m else None


def _to_lpa(rupees: float) -> float:
    return round(rupees / RUPEES_PER_LPA, 5)
