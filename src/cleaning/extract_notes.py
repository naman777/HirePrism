from __future__ import annotations

import re

# Ordered by specificity — first match wins
_LOCATION_PATTERNS = [
    r"location\s*[:\-–]\s*([A-Za-z][A-Za-z ,/()\-]+?)(?:\s*\||$|\n|;|\(Hybrid\)|\(Remote\)|\(Onsite\))",
    r"location\s*[:\-–]\s*([A-Za-z][A-Za-z ,/()\-]+?)(?:\||\n|;|$)",
]

_WORK_MODE_PATTERNS = {
    "Remote": re.compile(r"\bremote\b", re.IGNORECASE),
    "Hybrid": re.compile(r"\bhybrid\b", re.IGNORECASE),
    "Onsite": re.compile(r"\b(onsite|on-site|in[-\s]?office|work from office|wfo)\b", re.IGNORECASE),
}

_DURATION_PATTERNS = [
    # "18 months", "6 months", "12-month"
    re.compile(r"(\d+)\s*[-–]?\s*months?", re.IGNORECASE),
    # "one-year", "1 year"
    re.compile(r"\b(\d+)\s*[-–]?\s*years?", re.IGNORECASE),
    # "3–6 Months" (range — take the max)
    re.compile(r"(\d+)\s*[-–]\s*(\d+)\s*months?", re.IGNORECASE),
]

_GROSS_SIGNALS = re.compile(
    r"\b(gross\s*(salary|ctc|package)|gross\s*=|gross\s*:)\b", re.IGNORECASE
)


def extract_location(ctc_note: str | None) -> str | None:
    """Extract first city/location name from ctcNote or stipendNote."""
    if not ctc_note:
        return None
    for pattern in _LOCATION_PATTERNS:
        m = re.search(pattern, ctc_note, re.IGNORECASE)
        if m:
            loc = m.group(1).strip().rstrip(",").strip()
            if len(loc) >= 3:
                return loc
    return None


def extract_work_mode(text: str | None) -> str | None:
    """Return Remote / Hybrid / Onsite based on keyword presence.

    Checks ctcNote (primary) then stipendNote. Hybrid takes priority over Remote
    because a hybrid note often also contains the word 'remote'.
    """
    if not text:
        return None
    if _WORK_MODE_PATTERNS["Hybrid"].search(text):
        return "Hybrid"
    if _WORK_MODE_PATTERNS["Remote"].search(text):
        return "Remote"
    if _WORK_MODE_PATTERNS["Onsite"].search(text):
        return "Onsite"
    return None


def extract_duration_months(stipend_note: str | None) -> int | None:
    """Extract internship duration in months from stipendNote.

    For ranges (e.g. '3–6 Months') returns the upper bound.
    For year mentions, converts to months.
    """
    if not stipend_note:
        return None

    # Range pattern first: "3–6 Months"
    range_m = re.search(r"(\d+)\s*[-–]\s*(\d+)\s*months?", stipend_note, re.IGNORECASE)
    if range_m:
        return int(range_m.group(2))

    # Single month mention
    month_m = re.search(r"(\d+)\s*months?", stipend_note, re.IGNORECASE)
    if month_m:
        return int(month_m.group(1))

    # Year mention ("one-year", "1 year", "1-year")
    year_words = {"one": 1, "two": 2, "three": 3}
    for word, val in year_words.items():
        if re.search(rf"\b{word}[-\s]?year", stipend_note, re.IGNORECASE):
            return val * 12

    year_m = re.search(r"(\d+)\s*[-–]?\s*years?", stipend_note, re.IGNORECASE)
    if year_m:
        return int(year_m.group(1)) * 12

    return None


def extract_gross_ctc_signal(ctc_note: str | None) -> bool:
    """Return True if the ctcNote mentions a gross salary figure."""
    if not ctc_note:
        return False
    return bool(_GROSS_SIGNALS.search(ctc_note))
