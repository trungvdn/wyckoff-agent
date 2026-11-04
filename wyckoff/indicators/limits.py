"""Cờ trần / sàn (quy chuẩn 04/11/2026 mục 8). Causal: chỉ dùng phiên t và close phiên t-1.

Trên giá đã điều chỉnh, ngưỡng như `floor_days`: |Δclose| >= price_limit - tolerance (HOSE 7% - 0,5% = 6,5%).
- limit_up / limit_down: phiên tăng / giảm hết biên độ.
- ceiling_locked: limit_up và high - close <= 1 tick (đóng cửa tại giá cao nhất = giá trần).
- floor_locked: limit_down và close - low <= 1 tick.
Không phân biệt được khóa lúc ATC hay cả phiên (chỉ có dữ liệu ngày).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from wyckoff.indicators.ticks import tick_size

LIMIT_FLAGS = ("limit_up", "limit_down", "ceiling_locked", "floor_locked")
_EPS = 1e-9


def add_limit_flags(df: pd.DataFrame, price_limit: float = 0.07, tolerance: float = 0.005,
                    exchange: str = "HOSE") -> pd.DataFrame:
    out = df.copy()
    change = out["close"].pct_change()
    thr = price_limit - tolerance
    tick = np.array([tick_size(float(c), exchange) if np.isfinite(c) else np.nan for c in out["close"]])
    out["limit_up"] = (change >= thr).fillna(False).astype(bool)
    out["limit_down"] = (change <= -thr).fillna(False).astype(bool)
    out["ceiling_locked"] = out["limit_up"] & ((out["high"] - out["close"]) <= tick + _EPS)
    out["floor_locked"] = out["limit_down"] & ((out["close"] - out["low"]) <= tick + _EPS)
    return out


def limit_label(row: pd.Series) -> str | None:
    """Nhãn cụ thể nhất của một phiên: ceiling_locked > limit_up, floor_locked > limit_down."""
    for k in ("ceiling_locked", "floor_locked", "limit_up", "limit_down"):
        if bool(row.get(k, False)):
            return k
    return None
