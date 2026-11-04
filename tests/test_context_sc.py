"""Test cho đề xuất A-D: khởi động dữ liệu, SC kiểu VN, SC failed, bối cảnh range."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from wyckoff.config import RangeConfig, SellingClimaxConfig, SpringConfig
from wyckoff.data.loader import warmup_start
from wyckoff.detectors.events import detect_selling_climax, detect_spring, floor_days
from wyckoff.detectors.models import EventType
from wyckoff.detectors.swings import find_swings
from wyckoff.detectors.trading_range import classify_context, detect_trading_ranges
from wyckoff.indicators.core import add_indicators
from wyckoff.pipeline import analyze
from wyckoff.synthetic import SC_IDX, SPRING_IDX, make_wyckoff_accumulation


def _set_bar(df: pd.DataFrame, i: int, **vals: float) -> None:
    for k, v in vals.items():
        df.iloc[i, df.columns.get_loc(k)] = v


# ---------------------------------------------------------------- A. warm-up

def test_warmup_start_gives_enough_bars() -> None:
    ws = pd.Timestamp(warmup_start("2020-01-01", 120))
    assert len(pd.bdate_range(ws, "2019-12-31")) >= 120


def test_since_trims_but_keeps_warm_indicators(ohlcv: pd.DataFrame) -> None:
    full = analyze(ohlcv)
    cut = full.df.index[150]
    part = full.since(cut)
    assert part.df.index[0] == cut and part.df["sma"].notna().all()
    assert all(e.date >= cut for e in part.events)
    assert [e.kind for e in part.events] == [EventType.ST, EventType.SPRING, EventType.SOS]   # SC (idx 100) bị cắt
    assert part.phases.series.index[0] == cut and part.phases.segments[0].phase == "B"
    assert len(part.ranges) == 1                                               # range kéo dài qua cut


# ---------------------------------------------------------- C. SC thất bại

def test_sc_failed_before_ar(ohlcv: pd.DataFrame) -> None:
    df = ohlcv.copy()
    _set_bar(df, SC_IDX + 2, open=70.0, high=70.2, low=62.0, close=62.6)   # close < 64 - 0.5 ATR
    ev = detect_selling_climax(add_indicators(df))
    assert [(e.kind, e.idx) for e in ev] == [(EventType.SC, SC_IDX), (EventType.SC_FAILED, SC_IDX + 2)]
    assert ev[1].details["sc_date"] == ev[0].date.strftime("%Y-%m-%d")


def test_no_sc_failed_after_ar(ohlcv: pd.DataFrame) -> None:
    df = ohlcv.copy()
    i = SC_IDX + 10       # sau đỉnh AR ~73 (> 64 + 3 ATR)
    _set_bar(df, i, open=70.0, high=70.2, low=62.0, close=62.6)
    assert [e.kind for e in detect_selling_climax(add_indicators(df))] == [EventType.SC]


# ------------------------------------------------------ B. SC kiểu Việt Nam

def _floor_chain_df(reversal_vol: float = 2_500_000) -> pd.DataFrame:
    rows, prev = [], 100.0
    for i in range(80):
        c = 100.0 - 0.3 * i
        rows.append((prev, c + 0.5, c - 0.5, c, 1_000_000))
        prev = c
    for k in range(6):                                  # 3 phiên giảm sàn xen kẽ
        c = prev * (0.93 if k % 2 == 0 else 0.995)
        rows.append((prev, prev, c, c, 1_000_000))
        prev = c
    lo = prev * 0.97                                    # phiên rút chân
    rows.append((prev, prev * 1.005, lo, prev * 1.0, reversal_vol))
    prev = prev * 1.0
    for _ in range(5):
        rows.append((prev, prev * 1.01, prev * 0.995, prev * 1.005, 1_000_000))
        prev *= 1.005
    idx = pd.bdate_range("2024-01-01", periods=len(rows))
    return pd.DataFrame(rows, index=idx, columns=["open", "high", "low", "close", "volume"])


def test_floor_days_detected() -> None:
    df = _floor_chain_df()
    assert floor_days(df).sum() == 3


def test_sc_floor_chain_pattern() -> None:
    ind = add_indicators(_floor_chain_df())
    no_climax = SellingClimaxConfig(min_spread_atr=99)   # tắt dạng climax để cô lập dạng chuỗi sàn
    (sc,) = [e for e in detect_selling_climax(ind, no_climax) if e.kind == EventType.SC]
    assert sc.idx == 86 and sc.details["confirmation"] == "floor_chain" and sc.details["floor_days_before"] == 3
    assert detect_selling_climax(ind, replace(no_climax, floor_chain_min_days=4)) == []


def test_sc_floor_chain_needs_volume() -> None:
    ind = add_indicators(_floor_chain_df(reversal_vol=1_500_000))
    assert detect_selling_climax(ind, SellingClimaxConfig(min_spread_atr=99)) == []


def test_true_range_measure_counts_gap(ohlcv: pd.DataFrame) -> None:
    df = ohlcv.copy()
    # SC mở cửa gap xuống: H-L hẹp (1.2 ATR) nhưng True Range (tính gap từ close trước 70.3) rộng
    _set_bar(df, SC_IDX, open=66.4, high=66.4, low=64.0, close=65.5)
    ind = add_indicators(df)
    assert [e.idx for e in detect_selling_climax(ind, SellingClimaxConfig(spread_measure="true_range"))] == [SC_IDX]
    assert detect_selling_climax(ind, SellingClimaxConfig(spread_measure="range")) == []


def test_invalid_spread_measure(ind: pd.DataFrame) -> None:
    with pytest.raises(ValueError):
        detect_selling_climax(ind, SellingClimaxConfig(spread_measure="foo"))


# -------------------------------------------------------- D. bối cảnh range

@pytest.mark.parametrize("ret,label", [(-0.2, "sau nhịp giảm"), (-0.15, "sau nhịp giảm"), (0.0, "trung tính"),
                                       (0.29, "trung tính"), (0.30, "sau nhịp tăng")])
def test_classify_context(ret: float, label: str) -> None:
    close = np.ones(200)
    close[150] = 1 + ret
    assert classify_context(close, 150, RangeConfig(context_lookback=120)) == (label, pytest.approx(ret))


def test_classify_context_unknown_without_history() -> None:
    assert classify_context(np.ones(50), 30, RangeConfig()) == ("chưa rõ", None)


def test_synthetic_range_context(ind: pd.DataFrame) -> None:
    (rng,) = detect_trading_ranges(ind, find_swings(ind))
    assert rng.context == "chưa rõ"   # range bắt đầu ở phiên 100 < 120 phiên lịch sử
    (rng,) = detect_trading_ranges(ind, find_swings(ind), RangeConfig(context_lookback=60))
    assert rng.context == "sau nhịp giảm" and rng.prior_return < -0.15


def test_spring_skipped_in_distribution_range(ind: pd.DataFrame) -> None:
    (rng,) = detect_trading_ranges(ind, find_swings(ind))
    dist = replace(rng, context="sau nhịp tăng")
    assert [e.idx for e in detect_spring(ind, [dist])] == [SPRING_IDX]        # mặc định: không lọc
    no_dist = SpringConfig(allowed_contexts=("sau nhịp giảm", "trung tính", "chưa rõ"))
    assert detect_spring(ind, [dist], no_dist) == []
