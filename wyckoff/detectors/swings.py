"""Swing high/low dạng pivot (fractal) có thời điểm xác nhận rõ ràng."""
from __future__ import annotations

import pandas as pd

from wyckoff.config import SwingConfig
from wyckoff.detectors.models import Swing


def find_swings(df: pd.DataFrame, cfg: SwingConfig | None = None) -> list[Swing]:
    """Pivot high tại i: high[i] > max(high[i-left:i]) và high[i] >= max(high[i+1:i+right+1]).

    Pivot low đối xứng. Pivot chỉ biết được ở phiên i+right (`confirmed_idx`), nên mọi
    detector dùng swing phải lọc theo `confirmed_idx <= t` để tránh look-ahead.
    """
    cfg = cfg or SwingConfig()
    left, right = cfg.left, cfg.right
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    dates = df.index
    n = len(df)
    swings: list[Swing] = []
    for i in range(left, n - right):
        h = highs[i]
        if h > highs[i - left:i].max() and h >= highs[i + 1:i + right + 1].max():
            swings.append(Swing(i, dates[i], float(h), "high", i + right))
        lo = lows[i]
        if lo < lows[i - left:i].min() and lo <= lows[i + 1:i + right + 1].min():
            swings.append(Swing(i, dates[i], float(lo), "low", i + right))
    swings.sort(key=lambda s: (s.idx, s.kind))
    return swings
