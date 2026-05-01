from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.insights.generator import (
    InsightCard,
    generate_all,
    insight_branch_fte_ratio,
    insight_company_size_vs_ctc,
    insight_ctc_season_decline,
    insight_data_eng_no_cgpa,
    insight_meesho_outlier,
    insight_no_cgpa_overall,
    insight_ppo_premium,
    insight_swe_ctc_variance,
)
from src.insights.templates import (
    card_to_streamlit,
    cards_to_streamlit,
    render_card_markdown,
    render_report_markdown,
)
from src.modeling.build_tables import DB_PATH


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def all_cards() -> list[InsightCard]:
    return generate_all(DB_PATH)


# ── InsightCard dataclass ─────────────────────────────────────────────────────


def test_all_cards_have_required_fields(all_cards: list[InsightCard]) -> None:
    for card in all_cards:
        assert card.insight_id.startswith("INS_"), f"Bad ID: {card.insight_id}"
        assert len(card.title) > 10
        assert len(card.finding) > 30
        assert card.confidence in {"HIGH", "MEDIUM", "LOW"}
        assert card.supporting_metric
        assert card.data_caveat


def test_generate_all_returns_8_cards(all_cards: list[InsightCard]) -> None:
    assert len(all_cards) == 8


def test_insight_ids_are_unique(all_cards: list[InsightCard]) -> None:
    ids = [c.insight_id for c in all_cards]
    assert len(ids) == len(set(ids))


def test_to_dict_is_json_serialisable(all_cards: list[InsightCard]) -> None:
    for card in all_cards:
        payload = json.dumps(card.to_dict())  # must not raise
        assert len(payload) > 0


# ── Individual insights ───────────────────────────────────────────────────────


def test_ctc_season_decline_peak_before_trough(all_cards: list[InsightCard]) -> None:
    card = next(c for c in all_cards if c.insight_id == "INS_001")
    assert card.numbers["peak_avg_ctc_lpa"] > card.numbers["trough_avg_ctc_lpa"]
    assert card.numbers["decline_pct"] > 30


def test_ppo_premium_multiple_above_1(all_cards: list[InsightCard]) -> None:
    card = next(c for c in all_cards if c.insight_id == "INS_002")
    assert card.numbers["premium_multiple"] > 1.5
    assert card.numbers["ppo_avg_ctc_lpa"] > card.numbers["fte_avg_ctc_lpa"]


def test_company_size_correlation_near_zero(all_cards: list[InsightCard]) -> None:
    card = next(c for c in all_cards if c.insight_id == "INS_003")
    assert abs(card.numbers["pearson_r"]) < 0.15


def test_branch_fte_ratio_numbers_present(all_cards: list[InsightCard]) -> None:
    card = next(c for c in all_cards if c.insight_id == "INS_004")
    assert "CS" in card.numbers or "CIVIL" in card.numbers
    for group, ratio in card.numbers.items():
        if isinstance(ratio, float):
            assert ratio >= 0


def test_no_cgpa_overall_pct_in_range(all_cards: list[InsightCard]) -> None:
    card = next(c for c in all_cards if c.insight_id == "INS_007")
    pct = card.numbers["no_cgpa_pct"]
    assert 20 < pct < 40  # we know it's ~28.6%


def test_meesho_multiple_above_2(all_cards: list[InsightCard]) -> None:
    card = next(c for c in all_cards if c.insight_id == "INS_008")
    assert card.numbers["multiple_vs_sector"] >= 2.0


# ── Templates ─────────────────────────────────────────────────────────────────


def test_render_card_markdown_contains_id(all_cards: list[InsightCard]) -> None:
    card = all_cards[0]
    md = render_card_markdown(card)
    assert card.insight_id in md
    assert card.title in md
    assert card.supporting_metric in md


def test_render_report_markdown_contains_all_ids(all_cards: list[InsightCard]) -> None:
    md = render_report_markdown(all_cards)
    for card in all_cards:
        assert card.insight_id in md


def test_render_report_has_header(all_cards: list[InsightCard]) -> None:
    md = render_report_markdown(all_cards)
    assert "# HirePrism" in md
    assert "Insight Report" in md


def test_card_to_streamlit_has_required_keys(all_cards: list[InsightCard]) -> None:
    s = card_to_streamlit(all_cards[0])
    for key in ("id", "title", "finding", "confidence", "confidence_emoji", "caveat", "numbers"):
        assert key in s


def test_cards_to_streamlit_length(all_cards: list[InsightCard]) -> None:
    result = cards_to_streamlit(all_cards)
    assert len(result) == len(all_cards)


def test_confidence_emoji_present(all_cards: list[InsightCard]) -> None:
    for card in all_cards:
        s = card_to_streamlit(card)
        assert s["confidence_emoji"] in {"🟢", "🟡", "🔴"}


# ── Output files ──────────────────────────────────────────────────────────────


def test_insight_report_json_exists() -> None:
    assert Path("data/insights/insight_report.json").exists()


def test_insight_report_json_is_valid(all_cards: list[InsightCard]) -> None:
    payload = json.loads(Path("data/insights/insight_report.json").read_text())
    assert isinstance(payload, list)
    assert len(payload) == len(all_cards)
    for item in payload:
        assert "insight_id" in item
        assert "title" in item
        assert "finding" in item


def test_insight_report_md_exists() -> None:
    assert Path("data/insights/insight_report.md").exists()


def test_insight_report_md_has_content() -> None:
    content = Path("data/insights/insight_report.md").read_text(encoding="utf-8")
    assert len(content) > 500
    assert "INS_001" in content
