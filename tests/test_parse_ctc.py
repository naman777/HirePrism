import pytest

from src.cleaning.parse_ctc import (
    STATUS_KNOWN,
    STATUS_MISSING,
    STATUS_PENDING,
    STATUS_RANGE,
    STATUS_UNKNOWN,
    parse_ctc,
)


# ── MISSING ──────────────────────────────────────────────────────────────────


def test_none_is_missing():
    r = parse_ctc(None)
    assert r.status == STATUS_MISSING
    assert r.normalized_lpa is None


def test_empty_string_is_missing():
    r = parse_ctc("")
    assert r.status == STATUS_MISSING


def test_whitespace_only_is_missing():
    r = parse_ctc("   ")
    assert r.status == STATUS_MISSING


# ── KNOWN (plain integer in rupees) ──────────────────────────────────────────


def test_plain_integer_becomes_known():
    r = parse_ctc("411000")
    assert r.status == STATUS_KNOWN
    assert abs(r.normalized_lpa - 4.11) < 1e-4


def test_common_integer_600000():
    r = parse_ctc("600000")
    assert r.status == STATUS_KNOWN
    assert abs(r.normalized_lpa - 6.0) < 1e-4


def test_high_salary_integer():
    r = parse_ctc("2500000")
    assert r.status == STATUS_KNOWN
    assert abs(r.normalized_lpa - 25.0) < 1e-4


def test_very_high_salary_integer():
    r = parse_ctc("12300000")
    assert r.status == STATUS_KNOWN
    assert abs(r.normalized_lpa - 123.0) < 1e-4


def test_odd_decimal_integer():
    r = parse_ctc("1262218")
    assert r.status == STATUS_KNOWN
    assert abs(r.normalized_lpa - 12.62218) < 1e-4


# ── RANGE (hyphen separated) ─────────────────────────────────────────────────


def test_simple_range():
    r = parse_ctc("800000-1200000")
    assert r.status == STATUS_RANGE
    assert abs(r.min_lpa - 8.0) < 1e-4
    assert abs(r.max_lpa - 12.0) < 1e-4
    assert abs(r.normalized_lpa - 10.0) < 1e-4


def test_range_with_indian_commas():
    r = parse_ctc("12,00,000-16,00,000 (Subject to Role and individual performance)")
    assert r.status == STATUS_RANGE
    assert abs(r.min_lpa - 12.0) < 1e-4
    assert abs(r.max_lpa - 16.0) < 1e-4


def test_range_min_less_than_max():
    r = parse_ctc("300000-600000")
    assert r.min_lpa < r.max_lpa


def test_range_normalized_is_midpoint():
    r = parse_ctc("1000000-1200000")
    assert abs(r.normalized_lpa - 11.0) < 1e-4


def test_tight_range():
    r = parse_ctc("900000-950000")
    assert r.status == STATUS_RANGE
    assert abs(r.normalized_lpa - 9.25) < 1e-4


# ── RANGE (degree-split slash format) ────────────────────────────────────────


def test_degree_split_slash():
    r = parse_ctc("6,56,000 (B.E.) / 7,36,000 (M.E./M.Sc./MBA)")
    assert r.status == STATUS_RANGE
    assert abs(r.min_lpa - 6.56) < 1e-3
    assert abs(r.max_lpa - 7.36) < 1e-3


# ── PENDING ──────────────────────────────────────────────────────────────────


def test_to_be_notified():
    r = parse_ctc("To be notified")
    assert r.status == STATUS_PENDING
    assert r.normalized_lpa is None


def test_negotiable_post_interviews():
    r = parse_ctc("Negotiable post Interviews")
    assert r.status == STATUS_PENDING


def test_negotiable_if_retained():
    r = parse_ctc("Negotiable if retained")
    assert r.status == STATUS_PENDING


def test_will_be_communicated():
    r = parse_ctc("Will be communicated shortly")
    assert r.status == STATUS_PENDING


def test_yet_to_be_intimated():
    r = parse_ctc("Yet to be intimated")
    assert r.status == STATUS_PENDING


# ── UNKNOWN ───────────────────────────────────────────────────────────────────


def test_not_disclosed():
    r = parse_ctc("Not Disclosed")
    assert r.status == STATUS_UNKNOWN
    assert r.normalized_lpa is None


def test_not_declared():
    r = parse_ctc("Not Declared")
    assert r.status == STATUS_UNKNOWN


def test_not_known():
    r = parse_ctc("Not Known")
    assert r.status == STATUS_UNKNOWN


def test_not_announced():
    r = parse_ctc("Not Announced")
    assert r.status == STATUS_UNKNOWN


def test_not_announced_with_context():
    # Contains numbers in brackets but is still an "Not Announced" case
    r = parse_ctc("Not Announced (Last Year 800000-1000000)")
    assert r.status == STATUS_UNKNOWN


def test_free_text_falls_to_unknown():
    r = parse_ctc("Will be discussed after internship")
    # "will be discussed" → PENDING
    assert r.status == STATUS_PENDING


def test_raw_preserved():
    raw = "800000-1200000"
    r = parse_ctc(raw)
    assert r.raw == raw
