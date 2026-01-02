from __future__ import annotations

import pandas as pd


def parse_notice_date(raw: str | None) -> pd.Timestamp | None:
    if not raw:
        return None
    try:
        return pd.to_datetime(raw, format="%d/%m/%Y")
    except (ValueError, TypeError):
        return None


def parse_created_at(seconds: int | None, nanoseconds: int | None = 0) -> pd.Timestamp | None:
    if seconds is None:
        return None
    ts = float(seconds) + float(nanoseconds or 0) / 1e9
    return pd.Timestamp(ts, unit="s", tz="UTC")
