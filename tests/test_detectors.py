from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from wyckoff.config import Config, RangeConfig, SellingClimaxConfig, SOSConfig, SpringConfig
from wyckoff.detectors.events import detect_selling_climax, detect_sos, detect_spring
from wyckoff.detectors.models import EventType
from wyckoff.detectors.swings import find_swings
from wyckoff.detectors.trading_range import detect_trading_ranges
from wyckoff.indicators.core import add_indicators
from wyckoff.pipeline import analyze
from wyckoff.synthetic import (
    RESISTANCE, SC_IDX, SOS_IDX, SPRING_CONFIRM_IDX, SPRING_IDX, SUPPORT, make_wyckoff_accumulation,
)


def _ranges(ind: pd.DataFrame):
    return detect_trading_ranges(ind, find_swings(ind), RangeConfig())


def test_single_range_found(ind: pd.DataFrame) -> None:
    ranges = _ranges(ind)
    assert len(ranges) == 1
    r = ranges[0]
    assert r.support == SUPPORT and r.resistance == RESISTANCE
    assert r.start_idx == SC_IDX
    assert SC_IDX + 20 <= r.confirmed_idx < SPRING_IDX
    assert r.exit_direction == "up" and r.end_confirmed_idx == SOS_IDX + 2


def test_range_rejected_when_too_tall(ind: pd.DataFrame) -> None:
    assert detect_trading_ranges(ind, find_swings(ind), RangeConfig(max_height_atr=2.0)) == []


def test_full_pipeline_events(ohlcv: pd.DataFrame) -> None:
    core = {EventType.SC, EventType.SPRING, EventType.SOS}
    ev = [(e.kind, e.idx, e.confirmed_idx) for e in analyze(ohlcv).events if e.kind in core]
    assert ev == [
        (EventType.SC, SC_IDX, SC_IDX),
        (EventType.SPRING, SPRING_IDX, SPRING_CONFIRM_IDX),
        (EventType.SOS, SOS_IDX, SOS_IDX),
    ]


def test_sc_evidence(ind: pd.DataFrame) -> None:
    (sc,) = detect_selling_climax(ind)
    assert sc.vol_ratio == pytest.approx(3.0) and sc.spread_atr > 1.5 and sc.close_pos >= 0.5


def test_sc_closing_near_low_needs_zone_reversal(ohlcv: pd.DataFrame) -> None:
    df = ohlcv.copy()
    df.iloc[SC_IDX, df.columns.get_loc("close")] = 64.5   # close_pos ~0.08
    ind = add_indicators(df)
    assert detect_selling_climax(ind, SellingClimaxConfig(zone_bars=0)) == []
    (sc,) = detect_selling_climax(ind)                      # phiên sau đóng cửa > điểm giữa 67.25
    assert sc.idx == SC_IDX and sc.confirmed_idx == SC_IDX + 1 and sc.details["confirmation"] == "zone"


def test_sc_rejected_without_volume(ohlcv: pd.DataFrame) -> None:
    df = ohlcv.copy()
    df.iloc[SC_IDX, df.columns.get_loc("volume")] = 1_500_000  # 1.5x
    assert detect_selling_climax(add_indicators(df)) == []


def test_sc_threshold_configurable(ind: pd.DataFrame) -> None:
    assert detect_selling_climax(ind, SellingClimaxConfig(min_vol_ratio=3.5)) == []


def test_spring_rejected_on_high_volume(ohlcv: pd.DataFrame) -> None:
    df = ohlcv.copy()
    df.iloc[SPRING_IDX, df.columns.get_loc("volume")] = 1_500_000
    ind = add_indicators(df)
    assert detect_spring(ind, _ranges(ind)) == []


def test_spring_rejected_when_recovery_too_slow(ind: pd.DataFrame) -> None:
    assert detect_spring(ind, _ranges(ind), SpringConfig(max_recovery_bars=1)) == []


def test_spring_single_bar(ohlcv: pd.DataFrame) -> None:
    df = ohlcv.copy()
    df.iloc[SPRING_IDX, df.columns.get_loc("close")] = 64.5   # quay lại ngay phiên thủng, close_pos 0.57
    ind = add_indicators(df)
    (sp,) = detect_spring(ind, _ranges(ind), SpringConfig(max_recovery_bars=1))
    assert sp.idx == sp.confirmed_idx == SPRING_IDX and sp.details["recovery_bars"] == 1


def test_spring_needs_range(ind: pd.DataFrame) -> None:
    assert detect_spring(ind, []) == []


def test_sos_rejected_on_low_volume(ohlcv: pd.DataFrame) -> None:
    df = ohlcv.copy()
    df.iloc[SOS_IDX, df.columns.get_loc("volume")] = 1_000_000
    ind = add_indicators(df)
    assert detect_sos(ind, _ranges(ind)) == []


def test_sos_threshold_configurable(ind: pd.DataFrame) -> None:
    assert detect_sos(ind, _ranges(ind), SOSConfig(min_close_pos=0.95)) == []


@pytest.mark.parametrize("cutoff", list(range(110, 212, 3)))
def test_no_lookahead(cutoff: int) -> None:
    """Chạy trên dữ liệu cắt tại `cutoff` phải cho đúng các sự kiện/range đã xác nhận trước đó."""
    full_df = make_wyckoff_accumulation()
    full = analyze(full_df)
    part = analyze(full_df.iloc[:cutoff])

    def key(evts):
        return [(e.kind, e.idx, e.confirmed_idx, round(e.vol_ratio, 9)) for e in evts]

    assert key(part.events) == key([e for e in full.events if e.confirmed_idx < cutoff])
    full_ranges = [(r.start_idx, r.confirmed_idx, r.support, r.resistance) for r in full.ranges if r.confirmed_idx < cutoff]
    assert [(r.start_idx, r.confirmed_idx, r.support, r.resistance) for r in part.ranges] == full_ranges
    pd.testing.assert_frame_equal(part.df, full.df.iloc[:cutoff])
    pd.testing.assert_series_equal(part.phases.series["phase"], full.phases.series["phase"].iloc[:cutoff])


def test_config_override_from_yaml(tmp_path) -> None:
    from wyckoff.config import load_config

    p = tmp_path / "c.yaml"
    p.write_text("sc:\n  min_vol_ratio: 2.5\nspring:\n  max_recovery_bars: 2\n", encoding="utf-8")
    cfg = load_config(p)
    assert cfg.sc.min_vol_ratio == 2.5 and cfg.spring.max_recovery_bars == 2
    assert cfg.sos == Config().sos


def test_config_rejects_unknown_key(tmp_path) -> None:
    from wyckoff.config import load_config

    p = tmp_path / "c.yaml"
    p.write_text("sc:\n  min_volume: 2\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(p)


def test_default_yaml_matches_defaults() -> None:
    from pathlib import Path

    from wyckoff.config import load_config

    assert load_config(Path(__file__).parents[1] / "config" / "default.yaml") == Config()


# ------------------------------------------------- quy tắc bổ sung (đề xuất 2-5)

def _set_bar(df: pd.DataFrame, i: int, **vals: float) -> None:
    for k, v in vals.items():
        df.iloc[i, df.columns.get_loc(k)] = v


def _springs(df: pd.DataFrame, cfg: SpringConfig | None = None):
    ind = add_indicators(df)
    return detect_spring(ind, _ranges(ind), cfg)


def test_sc_zone_rejected_when_next_bar_makes_lower_low(ohlcv: pd.DataFrame) -> None:
    df = ohlcv.copy()
    _set_bar(df, SC_IDX, close=64.5)
    _set_bar(df, SC_IDX + 1, low=63.5, close=69.0, high=69.5)   # đóng cửa cao nhưng thủng đáy climax
    assert [e for e in detect_selling_climax(add_indicators(df)) if e.idx == SC_IDX] == []


def test_spring_needs_bars_after_range_confirmation(ohlcv: pd.DataFrame) -> None:
    assert _springs(ohlcv, SpringConfig(min_bars_after_confirm=60)) == []


def test_spring_penetration_must_exceed_one_tick(ohlcv: pd.DataFrame) -> None:
    df = ohlcv.copy()
    # giá 64 (>= 50 nghìn) trên HOSE -> tick 0.1
    _set_bar(df, SPRING_IDX, low=63.93, close=63.93)   # thủng 0.07 < 1 tick
    _set_bar(df, SPRING_IDX + 1, low=63.97)
    assert _springs(df, SpringConfig(min_penetration_atr=0.0)) == []
    _set_bar(df, SPRING_IDX, low=63.85, close=63.9)    # thủng 0.15 > 1 tick
    (sp,) = _springs(df, SpringConfig(min_penetration_atr=0.0))
    assert sp.idx == SPRING_IDX


def test_spring_weak_recovery_bar_is_skipped(ohlcv: pd.DataFrame) -> None:
    df = ohlcv.copy()
    _set_bar(df, SPRING_CONFIRM_IDX, close=64.1)   # trên support nhưng close_pos 0.32
    (sp,) = _springs(df)
    assert sp.confirmed_idx == SPRING_CONFIRM_IDX + 1 and sp.details["recovery_close_pos"] >= 0.5


def test_spring_recovery_needs_one_tick_above_support(ohlcv: pd.DataFrame) -> None:
    df = ohlcv.copy()
    _set_bar(df, SPRING_CONFIRM_IDX, close=64.0, high=64.2, low=63.2)   # đúng bằng support
    (sp,) = _springs(df)
    assert sp.confirmed_idx > SPRING_CONFIRM_IDX


def test_shakeout_confirmed_by_test(ohlcv: pd.DataFrame) -> None:
    df = ohlcv.copy()
    _set_bar(df, SPRING_IDX, volume=1_500_000)                     # thủng với volume 1.5x -> shakeout
    test_idx = SPRING_CONFIRM_IDX + 2
    _set_bar(df, test_idx, low=63.5, high=66.7, close=66.0, volume=500_000)
    events = _springs(df)
    assert [(e.kind, e.idx, e.confirmed_idx) for e in events] == [
        (EventType.SPRING, SPRING_IDX, test_idx),
        (EventType.TEST, test_idx, test_idx),
    ]
    assert events[0].details["spring_type"] == "shakeout"
    assert events[1].details["volume_vs_shakeout"] == pytest.approx(1 / 3, abs=1e-3)


def test_shakeout_without_test_is_not_a_spring(ohlcv: pd.DataFrame) -> None:
    df = ohlcv.copy()
    _set_bar(df, SPRING_IDX, volume=1_500_000)
    assert _springs(df) == []


def test_test_volume_must_be_lower_than_shakeout(ohlcv: pd.DataFrame) -> None:
    df = ohlcv.copy()
    _set_bar(df, SPRING_IDX, volume=1_500_000)
    _set_bar(df, SPRING_CONFIRM_IDX + 2, low=63.5, high=66.7, close=66.0, volume=1_000_000)  # 0.67x > 0.6x
    events = _springs(df)
    assert not [e for e in events if e.kind == EventType.TEST or e.idx == SPRING_IDX]
    # phiên đó thủng lại support với volume thấp -> tự nó là một Spring volume thấp mới
    assert [(e.idx, e.details["spring_type"]) for e in events] == [(SPRING_CONFIRM_IDX + 2, "low_volume")]


@pytest.mark.parametrize("second_low,kept", [(63.0, False), (62.0, True)])
def test_spring_merge_keeps_only_lower_low(ohlcv: pd.DataFrame, second_low: float, kept: bool) -> None:
    df = ohlcv.copy()
    j = SPRING_IDX + 6                                    # Spring thứ hai cách 6 phiên
    _set_bar(df, j, open=68.0, high=68.5, low=second_low, close=68.0, volume=500_000)
    springs = [e for e in _springs(df) if e.kind == EventType.SPRING]
    assert [s.idx for s in springs] == ([SPRING_IDX, j] if kept else [SPRING_IDX])


def test_sos_close_pos_rounding(ohlcv: pd.DataFrame) -> None:
    df = ohlcv.copy()
    _set_bar(df, SOS_IDX, close=72.8 + 0.698 * 4.7)       # close_pos = 0.698
    ind = add_indicators(df)
    assert len(detect_sos(ind, _ranges(ind), decimals=2)) == 1
    assert detect_sos(ind, _ranges(ind), decimals=6) == []


def test_shakeout_invalidated_by_lower_low_before_test(ohlcv: pd.DataFrame) -> None:
    df = ohlcv.copy()
    _set_bar(df, SPRING_IDX, volume=1_500_000)                       # shakeout, đáy 62.5
    _set_bar(df, SPRING_CONFIRM_IDX + 1, low=62.0, volume=1_500_000)  # thủng đáy shakeout trước Test
    _set_bar(df, SPRING_CONFIRM_IDX + 2, low=63.5, high=66.7, close=66.0, volume=500_000)
    assert not [e for e in _springs(df) if e.idx == SPRING_IDX or e.kind == EventType.TEST]
