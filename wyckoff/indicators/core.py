"""Chỉ báo nền. Tất cả đều causal: giá trị tại t chỉ dùng dữ liệu <= t.

Các cột tham chiếu (`atr_ref`, `vol_ma`) dùng dữ liệu đến t-1 để nến t không
tự làm loãng chính ngưỡng so sánh của nó.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from wyckoff.config import IndicatorConfig

REQUIRED_COLUMNS = ("open", "high", "low", "close", "volume")


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    ranges = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()],
        axis=1,
    )
    return ranges.max(axis=1, skipna=True)


def wilder_atr(df: pd.DataFrame, period: int) -> pd.Series:
    """ATR kiểu Wilder: khởi tạo bằng trung bình TR `period` phiên đầu, sau đó làm mượt 1/period."""
    tr = true_range(df).to_numpy(dtype=float)
    atr = np.full(len(tr), np.nan)
    if len(tr) >= period:
        atr[period - 1] = tr[:period].mean()
        for i in range(period, len(tr)):
            atr[i] = atr[i - 1] + (tr[i] - atr[i - 1]) / period
    return pd.Series(atr, index=df.index, name="atr")


def close_position(df: pd.DataFrame) -> pd.Series:
    spread = df["high"] - df["low"]
    pos = (df["close"] - df["low"]) / spread.where(spread > 0)
    return pos.fillna(0.5).clip(0.0, 1.0)


def add_indicators(df: pd.DataFrame, cfg: IndicatorConfig | None = None) -> pd.DataFrame:
    cfg = cfg or IndicatorConfig()
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Thiếu cột {missing}")
    out = df.copy()
    out["spread"] = out["high"] - out["low"]
    out["tr"] = true_range(out)
    out["atr"] = wilder_atr(out, cfg.atr_period)
    out["atr_ref"] = out["atr"].shift(1)
    out["close_pos"] = close_position(out)
    out["vol_ma"] = out["volume"].rolling(cfg.vol_ma_period, min_periods=cfg.vol_ma_period).mean().shift(1)
    out["vol_ratio"] = out["volume"] / out["vol_ma"]
    out["spread_atr"] = out["spread"] / out["atr_ref"]
    out["tr_atr"] = out["tr"] / out["atr_ref"]          # biên độ thật (tính cả gap) / ATR
    out["change"] = out["close"].pct_change()
    out["sma"] = out["close"].rolling(cfg.sma_period, min_periods=cfg.sma_period).mean()
    return out
