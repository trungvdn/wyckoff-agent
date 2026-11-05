"""Giai đoạn / loại cấu trúc: quy tắc state machine, ma trận chốt nhãn, chống look-ahead, không đổi pha."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from wyckoff.config import load_config
from wyckoff.detectors.models import CTX_AFTER_RISE, CTX_NEUTRAL, TradingRange
from wyckoff.pipeline import analyze
from wyckoff.stages import (
    ACCUMULATION, DISTRIBUTION, INITIAL_ACCUMULATION, INITIAL_DISTRIBUTION, MARKDOWN, MARKUP, RE_ACCUMULATION,
    RE_DISTRIBUTION, STAGES, TRANSITION, TRENDING_DOWN, TRENDING_UP, TYPE_TO_STAGE, classify_stages, current_stage,
)
from wyckoff.synthetic import SC_IDX, SOS_IDX


def frame(close: list[float] | np.ndarray, sma: list[float] | np.ndarray | None = None) -> pd.DataFrame:
    close = np.asarray(close, dtype=float)
    idx = pd.bdate_range("2024-01-01", periods=len(close), name="date")
    s = pd.Series(close).rolling(50, min_periods=50).mean().to_numpy() if sma is None else np.asarray(sma, dtype=float)
    return pd.DataFrame({"close": close, "sma": s}, index=idx)


def tr(df: pd.DataFrame, rid: int, start: int, conf: int, end_conf: int | None = None, direction: str | None = None,
       context: str = CTX_NEUTRAL) -> TradingRange:
    d = df.index
    return TradingRange(
        range_id=rid, start_idx=start, start_date=d[start], end_idx=end_conf or len(df) - 1, end_date=d[end_conf or len(df) - 1],
        confirmed_idx=conf, confirmed_date=d[conf], support=1.0, resistance=2.0, atr_at_confirm=0.1,
        end_confirmed_idx=end_conf, end_confirmed_date=None if end_conf is None else d[end_conf],
        exit_direction=direction, context=context,  # type: ignore[arg-type]
    )


UP = np.linspace(50, 150, 120)
DOWN = np.linspace(150, 50, 120)


# ------------------------------------------------------------------ xu hướng ngoài range

def test_trend_needs_enter_bars_and_sloped_sma() -> None:
    res = classify_stages(frame(UP), [])
    types = res.series["structure_type"]
    assert types.iloc[0] == TRANSITION
    first_up = int(np.argmax(types.to_numpy() == TRENDING_UP))
    assert first_up == 49 + 20 + 4       # SMA có từ phiên 49, có độ dốc từ phiên 69, thêm 5 close liên tiếp
    assert res.series["stage"].iloc[-1] == MARKUP
    assert classify_stages(frame(DOWN), []).series["stage"].iloc[-1] == MARKDOWN


def test_flat_market_stays_transition() -> None:
    res = classify_stages(frame(np.full(150, 100.0)), [])
    assert set(res.series["structure_type"]) == {TRANSITION} and res.series["stage"].isna().all()


def test_trend_lost_after_exit_bars_wrong_side() -> None:
    close = np.r_[UP, np.full(4, 50.0), [200.0], np.full(5, 50.0)]
    sma = np.r_[np.linspace(40, 140, 120), np.full(10, 140.0)]
    types = classify_stages(frame(close, sma), []).series["structure_type"].to_numpy()
    assert types[123] == TRENDING_UP          # 4 close sai phía: chưa mất
    assert types[124] == TRENDING_UP          # close quay lại đúng phía: đếm lại
    assert types[128] == TRENDING_UP          # mới 4 close sai phía
    assert types[129] == TRANSITION           # đủ 5 close


# ------------------------------------------------------------------ ma trận 2x2

@pytest.mark.parametrize("prior, direction, typ, stage, after", [
    (UP, "up", RE_ACCUMULATION, ACCUMULATION, TRENDING_UP),
    (UP, "down", INITIAL_DISTRIBUTION, DISTRIBUTION, TRENDING_DOWN),
    (DOWN, "up", INITIAL_ACCUMULATION, ACCUMULATION, TRENDING_UP),
    (DOWN, "down", RE_DISTRIBUTION, DISTRIBUTION, TRENDING_DOWN),
])
def test_resolution_matrix(prior: np.ndarray, direction: str, typ: str, stage: str, after: str) -> None:
    df = frame(np.r_[prior, np.full(40, prior[-1])])
    res = classify_stages(df, [tr(df, 0, 118, 130, 150, direction)])
    label = res.ranges[0]
    assert (label.structure_type, label.stage, label.exit_direction) == (typ, stage, direction)
    assert label.resolved_idx == 150 and label.prior_source == "trend"
    assert res.series["structure_type"].iloc[150] == after
    assert TYPE_TO_STAGE[after] in STAGES


def test_inside_range_is_uncertain_with_two_candidates() -> None:
    df = frame(np.r_[UP, np.full(40, UP[-1])])
    res = classify_stages(df, [tr(df, 0, 118, 130)])
    row = res.series.iloc[-1]
    assert row["structure_type"] == TRANSITION and pd.isna(row["stage"]) and row["prior_stage"] == MARKUP
    cur = current_stage(res)
    assert cur.candidates == (RE_ACCUMULATION, INITIAL_DISTRIBUTION) and cur.stage is None and cur.range_id == 0
    assert res.ranges[0].stage is None and res.ranges[0].resolved_idx is None


def test_consecutive_ranges_use_previous_exit_as_prior() -> None:
    df = frame(np.full(200, 100.0))           # không có xu hướng theo SMA: chỉ range quyết định
    res = classify_stages(df, [tr(df, 0, 20, 40, 80, "down"), tr(df, 1, 78, 100, 140, "down")])
    first, second = res.ranges
    assert first.prior_stage is None and first.stage == DISTRIBUTION and first.structure_type is None
    assert second.prior_stage == MARKDOWN and second.structure_type == RE_DISTRIBUTION


def test_context_only_used_when_no_trend_known() -> None:
    df = frame(np.full(120, 100.0))
    res = classify_stages(df, [tr(df, 0, 20, 40, context=CTX_AFTER_RISE)])
    assert res.ranges[0].prior_stage == MARKUP and res.ranges[0].prior_source == "context"
    res = classify_stages(df, [tr(df, 0, 20, 40)])
    assert res.ranges[0].prior_stage is None and res.ranges[0].candidates == (ACCUMULATION, DISTRIBUTION)


# ------------------------------------------------------------------ trên chuỗi DEMO

def test_demo_sequence(ohlcv: pd.DataFrame) -> None:
    res = analyze(ohlcv)
    s = res.stages.series
    assert s["structure_type"].iloc[SC_IDX - 1] == TRENDING_DOWN
    assert s["structure_type"].iloc[SOS_IDX - 1] == TRANSITION
    assert s["stage"].iloc[-1] == MARKUP
    label = res.stages.ranges[-1]
    assert label.structure_type == INITIAL_ACCUMULATION and label.stage == ACCUMULATION
    segs = res.stages.segments
    assert segs[0].start_idx == 0 and segs[-1].end_idx == len(s) - 1
    assert all(a.end_idx + 1 == b.start_idx for a, b in zip(segs, segs[1:]))


def test_no_lookahead(ohlcv: pd.DataFrame) -> None:
    full = analyze(ohlcv).stages
    for cut in (90, 130, 175, 192, 195, 205):
        part = analyze(ohlcv.iloc[:cut]).stages
        pd.testing.assert_frame_equal(part.series, full.series.iloc[:cut])
        for r in part.ranges:
            f = next(x for x in full.ranges if x.range_id == r.range_id)
            assert (r.prior_stage, r.candidates) == (f.prior_stage, f.candidates)
            assert r.resolved_idx is None or r.resolved_idx == f.resolved_idx


def test_since_keeps_current_stage(ohlcv: pd.DataFrame) -> None:
    res = analyze(ohlcv)
    cut = res.since(ohlcv.index[150])
    assert len(cut.stages.series) == len(cut.df) and cut.current_stage() == res.current_stage()


def test_stage_config_in_yaml_matches_defaults() -> None:
    assert load_config("config/default.yaml").stage == load_config(None).stage
