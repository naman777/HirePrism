"""Insight Report — 8 data-backed findings from the placement dataset."""
import json
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Insights · HirePrism", page_icon="💡", layout="wide")

from src.app.components import page_header

page_header("Insight Report", "8 findings discovered through analytical exploration of the placement data")

INSIGHT_PATH = Path("data/insights/insight_report.json")
MD_PATH = Path("data/insights/insight_report.md")

if not INSIGHT_PATH.exists():
    st.warning("Insight report not generated yet. Run `make insights`.")
    st.stop()

cards = json.loads(INSIGHT_PATH.read_text(encoding="utf-8"))

CONFIDENCE_COLOR = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🔴"}
CONFIDENCE_BG = {"HIGH": "#e8f5e9", "MEDIUM": "#fff9e6", "LOW": "#fce4ec"}

# ── Tag filter ────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Filter")
    conf_filter = st.multiselect(
        "Confidence",
        ["HIGH", "MEDIUM", "LOW"],
        default=["HIGH", "MEDIUM", "LOW"],
    )

filtered = [c for c in cards if c["confidence"] in conf_filter]
st.caption(f"Showing {len(filtered)} of {len(cards)} insights")

# ── Render insight cards ──────────────────────────────────────────────────────

for card in filtered:
    emoji = CONFIDENCE_COLOR.get(card["confidence"], "")
    with st.container(border=True):
        col_title, col_badge = st.columns([5, 1])
        with col_title:
            st.markdown(f"#### {card['insight_id']} — {card['title']}")
        with col_badge:
            st.markdown(
                f"<div style='text-align:right;font-size:1.2em'>{emoji} {card['confidence']}</div>",
                unsafe_allow_html=True,
            )

        st.markdown(card["finding"])

        with st.expander("Details"):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**Supporting metric:** `{card['supporting_metric']}`")
            with c2:
                st.markdown(f"**Data caveat:** *{card['data_caveat']}*")

            if card.get("numbers"):
                st.json(card["numbers"], expanded=False)

# ── Full markdown report ──────────────────────────────────────────────────────

st.divider()
if MD_PATH.exists():
    with st.expander("📄 View full markdown report"):
        st.markdown(MD_PATH.read_text(encoding="utf-8"))
