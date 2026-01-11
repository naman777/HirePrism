from __future__ import annotations

from jinja2 import Environment

from src.insights.generator import InsightCard

_CONFIDENCE_EMOJI = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🔴"}
_CONFIDENCE_LABEL = {"HIGH": "High confidence", "MEDIUM": "Medium confidence", "LOW": "Low confidence"}

# ── Markdown template ─────────────────────────────────────────────────────────

_MD_CARD = """\
### {{ card.insight_id }} — {{ card.title }}

{{ card.finding }}

**Supporting metric:** `{{ card.supporting_metric }}`
**Confidence:** {{ confidence_label }}
**Data caveat:** *{{ card.data_caveat }}*

---
"""

_MD_REPORT = """\
# Placelytics — Insight Report

*Generated from {{ total }} analysed placement offers.*

{% for card in cards %}
{{ render_card(card) }}
{% endfor %}
"""

_env = Environment(autoescape=False)
_card_tmpl = _env.from_string(_MD_CARD)
_report_tmpl = _env.from_string(_MD_REPORT)


def render_card_markdown(card: InsightCard) -> str:
    """Render a single InsightCard as a Markdown block."""
    return _card_tmpl.render(
        card=card,
        confidence_label=f"{_CONFIDENCE_EMOJI.get(card.confidence, '')} "
                         f"{_CONFIDENCE_LABEL.get(card.confidence, card.confidence)}",
    )


def render_report_markdown(cards: list[InsightCard], total_offers: int = 654) -> str:
    """Render all InsightCards into a full Markdown report."""
    return _report_tmpl.render(
        cards=cards,
        total=total_offers,
        render_card=render_card_markdown,
    )


# ── Streamlit-friendly dict ───────────────────────────────────────────────────

def card_to_streamlit(card: InsightCard) -> dict:
    """Return a flat dict suitable for rendering in a Streamlit metric/card widget."""
    return {
        "id": card.insight_id,
        "title": card.title,
        "finding": card.finding,
        "confidence": card.confidence,
        "confidence_emoji": _CONFIDENCE_EMOJI.get(card.confidence, ""),
        "caveat": card.data_caveat,
        "metric": card.supporting_metric,
        "numbers": card.numbers,
    }


def cards_to_streamlit(cards: list[InsightCard]) -> list[dict]:
    return [card_to_streamlit(c) for c in cards]
