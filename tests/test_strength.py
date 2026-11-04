"""Sức mạnh cung cầu trong Markup / Markdown: từng tín hiệu, mức tổng hợp, chống look-ahead, view model."""
from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest

from wyckoff.agent.payload import build_payload, confidence
from wyckoff.config import ConfidenceConfig, load_config
from wyckoff.detectors.models import Swing
from wyckoff.pipeline import analyze
from wyckoff.strength import MODERATE, STRONG, WEAK, trend_strength
from wyckoff.web.viewmodel import stage_view


def frame(close: list[float] | np.ndarray, volume: list[float] | np.ndarray | None = None, vol_ratio: float = 1.0,
          sma: float | None = None) -> pd.DataFrame:
    close = np.asarray(close, dtype=float)
    n = len(close)
    idx = pd.bdate_range("2024-01-01", periods=n, name="date")
    return pd.DataFrame({
        "close": close, "volume": np.full(n, 100.0) if volume is None else np.asarray(volume, dtype=float),
        "atr": 1.0, "vol_ratio": vol_ratio, "sma": close.mean() if sma is None else sma,
    }, index=idx)


def swings(df: pd.DataFrame, highs: list[float], lows: list[float]) -> list[Swing]:
    out = []
    n = len(df)
    for i, p in enumerate(highs):
        out.append(Swing(n - 30 + i * 10, df.index[n - 30 + i * 10], p, "high", n - 25 + i * 10))
    for i, p in enumerate(lows):
        out.append(Swing(n - 25 + i * 10, df.index[n - 25 + i * 10], p, "low", n - 20 + i * 10))
    return out


def sig(ts, key: str):
    return next(s for s in ts.signals if s.key == key)


UP = np.linspace(100, 130, 40)
DOWN = UP[::-1]


# ------------------------------------------------------------------ khối lượng

def test_volume_share_counts_only_window_and_direction() -> None:
    close = np.r_[np.linspace(100, 110, 11), 111, 110, 111, 110, 111, 110, 111, 110, 111, 110, 111, 110, 111, 110, 111, 110, 111, 110, 111, 110]
    vol = np.where(np.diff(close, prepend=close[0]) > 0, 300.0, 100.0)
    ts = trend_strength(frame(close, vol), [], 0, "up")
    assert ts.up_volume_pct == pytest.approx(75.0) and ts.window == 20 and sig(ts, "volume").points == 1
    down = trend_strength(frame(close, vol), [], 0, "down")
    assert down.up_volume_pct == pytest.approx(75.0) and sig(down, "volume").points == -1   # cung chỉ 25%
    assert "25%" in sig(down, "volume").text


def test_volume_balanced_is_neutral() -> None:
    close = np.tile([100.0, 101.0], 15)
    assert sig(trend_strength(frame(close), [], 0, "up"), "volume").points == 0


# ------------------------------------------------------------------ đỉnh đáy

@pytest.mark.parametrize("highs, lows, up_pts, down_pts", [
    ([10, 12], [8, 9], 1, -1), ([12, 10], [9, 8], -1, 1), ([10, 12], [9, 8], 0, 0),
])
def test_swing_signal(highs: list[float], lows: list[float], up_pts: int, down_pts: int) -> None:
    df = frame(UP)
    assert sig(trend_strength(df, swings(df, highs, lows), 0, "up"), "swing").points == up_pts
    assert sig(trend_strength(df, swings(df, highs, lows), 0, "down"), "swing").points == down_pts


def test_swing_not_yet_confirmed_is_ignored() -> None:
    df = frame(UP)
    t = len(df) - 1
    s = swings(df, [10, 12], [8, 9]) + [Swing(t - 1, df.index[t - 1], 1.0, "low", t + 4)]
    assert sig(trend_strength(df, s, 0, "up"), "swing").points == 1


def test_swing_missing_is_neutral() -> None:
    assert sig(trend_strength(frame(UP), [], 0, "up"), "swing").points == 0


# ------------------------------------------------------------------ nhịp điều chỉnh

def test_no_correction_at_new_extreme() -> None:
    ts = trend_strength(frame(UP), [], 0, "up")
    assert not ts.correction.active and ts.correction.quality is None and sig(ts, "correction").points == 0
    assert "Chưa có nhịp" in ts.correction.verdict


def test_light_correction_has_low_volume_and_shallow_depth() -> None:
    close = np.r_[UP, 129.0, 128.0, 127.0]        # hồi 3 / 30 = 10% nhịp tăng
    ts = trend_strength(frame(close, vol_ratio=0.7, sma=100.0), [], 0, "up")
    assert ts.correction.active and ts.correction.quality == "light" and sig(ts, "correction").points == 1
    assert ts.correction.bars == 3 and ts.correction.retrace_pct == pytest.approx(10.0)
    assert "cung chưa mạnh lên" in ts.correction.verdict


@pytest.mark.parametrize("tail, vol_ratio, sma", [
    ([120.0, 110.0], 0.7, 100.0),    # sâu: 67% nhịp tăng
    ([129.0, 128.0], 1.5, 100.0),    # volume cao
    ([129.0, 128.0], 0.7, 128.5),    # close dưới SMA
])
def test_heavy_correction(tail: list[float], vol_ratio: float, sma: float) -> None:
    ts = trend_strength(frame(np.r_[UP, tail], vol_ratio=vol_ratio, sma=sma), [], 0, "up")
    assert ts.correction.quality == "heavy" and sig(ts, "correction").points == -1
    assert "cung đang mạnh lên" in ts.correction.verdict


def test_markdown_correction_is_a_rally() -> None:
    close = np.r_[DOWN, 101.0, 102.0, 103.0]
    ts = trend_strength(frame(close, vol_ratio=0.7, sma=130.0), [], 0, "down")
    assert ts.side == "supply" and ts.correction.quality == "light" and "cầu chưa quay lại" in ts.correction.verdict
    assert sig(ts, "correction").title == "Nhịp hồi"


def test_correction_uses_only_current_leg() -> None:
    close = np.r_[200.0, np.linspace(100, 130, 40), 128.0, 127.0]   # đỉnh 200 trước nhịp hiện tại không tính
    ts = trend_strength(frame(close, vol_ratio=0.7, sma=100.0), [], 1, "up")
    assert ts.correction.extreme_price == pytest.approx(130.0)


# ------------------------------------------------------------------ mức tổng hợp

def test_levels_from_score() -> None:
    vol = np.where(np.diff(UP, prepend=UP[0]) > 0, 100.0, 0.0)
    df = frame(UP, vol)
    strong = trend_strength(df, swings(df, [10, 12], [8, 9]), 0, "up")
    assert strong.level == STRONG and strong.score == 2 and strong.headline == "Cầu đang mạnh"
    weak = trend_strength(df, swings(df, [12, 10], [9, 8]), 0, "up")
    assert weak.score == 0 and weak.level == MODERATE and weak.headline == "Cầu ở mức trung bình"
    assert trend_strength(df, swings(df, [10, 12], [8, 9]), 0, "down").level == WEAK


def test_supply_headline() -> None:
    vol = np.full(len(DOWN), 100.0)
    df = frame(DOWN, vol)
    assert trend_strength(df, swings(df, [12, 10], [9, 8]), 0, "down").headline == "Cung đang mạnh"


# ------------------------------------------------------------------ trên chuỗi DEMO

def test_only_in_trend_stages(ohlcv: pd.DataFrame) -> None:
    res = analyze(ohlcv)
    assert res.current_stage().stage == "Markup" and res.trend_strength().side == "demand"
    assert analyze(ohlcv.iloc[:150]).trend_strength() is None     # đang trong range


def test_no_lookahead(ohlcv: pd.DataFrame) -> None:
    res = analyze(ohlcv)
    part = analyze(ohlcv.iloc[:205])
    broken = ohlcv.copy()
    broken.iloc[205:, broken.columns.get_loc("close")] = 1.0
    broken.iloc[205:, broken.columns.get_loc("low")] = 0.5
    assert analyze(broken.iloc[:205]).trend_strength() == part.trend_strength()
    assert res.trend_strength() is not None


# ------------------------------------------------------------------ view model

CUR = {"stage": None, "structure_type": "Transition / Uncertain", "since": "2024-01-01", "reason": "r", "prior_stage": None,
       "candidates": [], "range_id": None, "strength": None}


def test_stage_view_states() -> None:
    v = stage_view({**CUR, "range_id": 3, "candidates": ["Re-accumulation", "Initial Distribution"]}, [])
    assert v["view"] == "range" and v["title"] == "Re-accumulation hoặc Initial Distribution" and v["last_resolved"] is None
    assert stage_view({**CUR, "stage": "Markdown", "structure_type": "Trending Down"}, [])["view"] == "trend"
    t = stage_view(CUR, [{"range_id": 1, "structure_type": None, "stage": "Distribution", "resolved_date": "2024-02-01"}])
    assert t["view"] == "transition" and t["title"] == "Chưa có xu hướng rõ" and t["last_resolved"]["label"] == "Distribution"


# ------------------------------------------------------------------ H7: yếu tố tin cậy (mặc định tắt)

@pytest.mark.parametrize("side, level, pts", [
    ("demand", STRONG, 1), ("demand", MODERATE, 0), ("demand", WEAK, -1),
    ("supply", STRONG, -1), ("supply", MODERATE, 0), ("supply", WEAK, 0),
])
def test_h7a_points(side: str, level: str, pts: int, ohlcv: pd.DataFrame) -> None:
    res = analyze(ohlcv)
    s = dataclasses.replace(res.trend_strength(), side=side, level=level)
    c = confidence(res.current(), [], "trung tính", cfg=ConfidenceConfig(stage_strength=True), strength=s)
    assert next(f for f in c["factors"] if f["key"] == "stagestrength")["points"] == pts


def test_h7a_zero_without_trend(ohlcv: pd.DataFrame) -> None:
    c = confidence(analyze(ohlcv).current(), [], "trung tính", cfg=ConfidenceConfig(stage_strength=True))
    assert next(f for f in c["factors"] if f["key"] == "stagestrength")["points"] == 0


@pytest.mark.parametrize("prior, pts", [("Markdown", -1), ("Markup", 0), (None, 0)])
def test_h7b_replaces_range_context(prior: str | None, pts: int, ohlcv: pd.DataFrame) -> None:
    cur = analyze(ohlcv).current()
    c = confidence(cur, [], "sau nhịp giảm", cfg=ConfidenceConfig(prior_stage=True), prior_stage=prior)
    by = {f["key"]: f["points"] for f in c["factors"]}
    assert by["rangectx"] == 0 and by["priorstage"] == pts


def test_h7_off_by_default(ohlcv: pd.DataFrame) -> None:
    keys = {f["key"] for f in build_payload(analyze(ohlcv), "DEMO")["confidence"]["factors"]}
    assert not keys & {"stagestrength", "priorstage"}


def test_h7_configs_only_set_their_flag() -> None:
    a, b = load_config("config/h7a.yaml"), load_config("config/h7b.yaml")
    assert a.confidence == ConfidenceConfig(stage_strength=True) and b.confidence == ConfidenceConfig(prior_stage=True)
    assert dataclasses.replace(a, confidence=ConfidenceConfig()) == load_config(None)
