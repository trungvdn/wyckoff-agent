"""Chuỗi giá tổng hợp có cài sẵn SC -> trading range -> Spring -> SOS (dùng cho test và --demo).

Vị trí cài sẵn (index):
    0..99    downtrend 100 -> 70.3
    100      Selling Climax (low 64, vol 3x)
    101..175 trading range: support 64 (đáy SC), resistance 74
    176      Spring: thủng 64 xuống 62.5, vol 0.6x; 177 đóng cửa 65.5 (quay lại range)
    178..190 hồi lên sát resistance
    191      SOS: close 77.2 > 74, vol 2x, spread rộng, đóng cửa gần đỉnh
    192..211 markup
"""
from __future__ import annotations

import math

import pandas as pd

SC_IDX, SPRING_IDX, SPRING_CONFIRM_IDX, SOS_IDX = 100, 176, 177, 191
SUPPORT, RESISTANCE = 64.0, 74.0
BASE_VOL = 1_000_000.0


def make_wyckoff_accumulation(start: str = "2023-01-02") -> pd.DataFrame:
    rows: list[tuple[float, float, float, float, float]] = []

    def bar(o: float, h: float, lo: float, c: float, v: float = BASE_VOL) -> None:
        rows.append((o, h, lo, c, v))

    prev = 100.0
    for i in range(100):                       # downtrend
        c = 100.0 - 0.3 * i
        bar(prev, c + 1, c - 1, c)
        prev = c
    bar(prev, 70.5, 64.0, 68.0, 3 * BASE_VOL)  # SC
    prev = 68.0
    for k in range(75):                        # trading range
        c = 69.25 + 3.75 * math.sin(2 * math.pi * k / 20)
        bar(prev, max(prev, c) + 1, min(prev, c) - 1 if k else c - 1, c)
        prev = c
    bar(prev, 66.0, 62.5, 63.5, 0.6 * BASE_VOL)   # Spring: thủng support
    bar(63.5, 66.0, 63.2, 65.5, 0.9 * BASE_VOL)   # quay lại range
    prev = 65.5
    for k in range(13):                        # hồi lên (đỉnh không vượt resistance)
        c = 65.5 + 0.6 * (k + 1)
        bar(prev, min(c + 1, RESISTANCE - 0.1), c - 1, c)
        prev = c
    bar(prev, 77.5, 72.8, 77.2, 2 * BASE_VOL)  # SOS
    prev = 77.2
    for k in range(20):                        # markup
        c = 77.2 + 0.4 * (k + 1)
        bar(prev, c + 1, c - 1, c)
        prev = c

    idx = pd.bdate_range(start, periods=len(rows), name="date")
    return pd.DataFrame(rows, index=idx, columns=["open", "high", "low", "close", "volume"])


MIRROR_LEVEL = 150.0     # giá phân phối = MIRROR_LEVEL - giá tích lũy


def mirror_prices(df: pd.DataFrame, level: float = MIRROR_LEVEL) -> pd.DataFrame:
    """Lật giá quanh `level` (high <-> low), volume giữ nguyên: tích lũy thành phân phối."""
    return pd.DataFrame({"open": level - df["open"], "high": level - df["low"], "low": level - df["high"],
                         "close": level - df["close"], "volume": df["volume"]}, index=df.index)


def make_wyckoff_distribution(start: str = "2023-01-02") -> pd.DataFrame:
    """Lật `make_wyckoff_accumulation`: tăng 50 -> 79.7, BC tại SC_IDX (đỉnh 86), range support 76 / resistance 86,
    upthrust tại SPRING_IDX, SOW tại SOS_IDX, rồi markdown."""
    return mirror_prices(make_wyckoff_accumulation(start))


def make_market_index(dates: pd.DatetimeIndex, start: float = 1000.0) -> pd.DataFrame:
    """Chỉ số tổng hợp cho demo/test: giảm nhẹ nửa đầu, tăng dần nửa sau (biến động nhỏ, không đáy mới cuối kỳ)."""
    n = len(dates)
    rows: list[tuple[float, float, float, float, float]] = []
    prev = start
    for i in range(n):
        drift = -0.002 if i < n // 2 else 0.003
        c = prev * (1 + drift + 0.004 * math.sin(i / 3))
        rows.append((prev, max(prev, c) * 1.003, min(prev, c) * 0.997, c, 5e8))
        prev = c
    return pd.DataFrame(rows, index=dates, columns=["open", "high", "low", "close", "volume"])
