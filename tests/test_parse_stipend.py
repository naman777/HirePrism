import pytest

from src.cleaning.parse_stipend import (
    STATUS_KNOWN,
    STATUS_MISSING,
    STATUS_RANGE,
    STATUS_UNKNOWN,
    parse_stipend,
)


# ── MISSING ──────────────────────────────────────────────────────────────────


def test_none_is_missing():
    r = parse_stipend(None)
    assert r.status == STATUS_MISSING
    assert r.normalized_monthly is None


def test_empty_string_is_missing():
    r = parse_stipend("")
    assert r.status == STATUS_MISSING


# ── KNOWN (plain integer — monthly rupees) ────────────────────────────────────


def test_plain_integer():
    r = parse_stipend("20000")
    assert r.status == STATUS_KNOWN
    assert r.normalized_monthly == 20000.0


def test_large_stipend():
    r = parse_stipend("100000")
    assert r.status == STATUS_KNOWN
    assert r.normalized_monthly == 100000.0


def test_small_stipend():
    r = parse_stipend("5000")
    assert r.status == STATUS_KNOWN
    assert r.normalized_monthly == 5000.0


def test_unpaid_maps_to_zero():
    r = parse_stipend("Unpaid")
    assert r.status == STATUS_KNOWN
    assert r.normalized_monthly == 0.0


# ── RANGE (hyphen / en-dash) ──────────────────────────────────────────────────


def test_simple_range():
    r = parse_stipend("15000-25000")
    assert r.status == STATUS_RANGE
    assert r.min_monthly == 15000.0
    assert r.max_monthly == 25000.0
    assert r.normalized_monthly == 20000.0


def test_en_dash_range():
    r = parse_stipend("10000–20000")  # en-dash
    assert r.status == STATUS_RANGE
    assert r.min_monthly == 10000.0
    assert r.max_monthly == 20000.0


def test_range_with_commas():
    r = parse_stipend("25,000-30,000")
    assert r.status == STATUS_RANGE
    assert r.min_monthly == 25000.0
    assert r.max_monthly == 30000.0


def test_range_with_en_dash_and_commas():
    r = parse_stipend("15000–25000")
    assert r.status == STATUS_RANGE
    assert r.normalized_monthly == 20000.0


# ── RANGE (degree-split slash) ────────────────────────────────────────────────


def test_degree_split_slash():
    r = parse_stipend("17,500 (B.E.) / 25,000 (M.E./M.Sc./MBA)")
    assert r.status == STATUS_RANGE
    assert r.min_monthly == 17500.0
    assert r.max_monthly == 25000.0


# ── UNKNOWN ───────────────────────────────────────────────────────────────────


def test_not_declared():
    r = parse_stipend("Not Declared")
    assert r.status == STATUS_UNKNOWN
    assert r.normalized_monthly is None


def test_not_announced():
    r = parse_stipend("Not Announced")
    assert r.status == STATUS_UNKNOWN


def test_not_announced_with_context():
    r = parse_stipend("Not Announced (As per industry Standard)")
    assert r.status == STATUS_UNKNOWN


def test_not_known():
    r = parse_stipend("Not Known")
    assert r.status == STATUS_UNKNOWN


# ── Miscellaneous ─────────────────────────────────────────────────────────────


def test_raw_preserved():
    raw = "50000-75000"
    r = parse_stipend(raw)
    assert r.raw == raw


def test_range_min_less_than_max():
    r = parse_stipend("30000-40000")
    assert r.min_monthly < r.max_monthly
