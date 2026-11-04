"""H4: SC hai phiên (thủng nhẹ đáy climax) và range neo theo SC–AR."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from wyckoff.config import Config, RangeConfig, SellingClimaxConfig
from wyckoff.detectors.events import detect_selling_climax
from wyckoff.detectors.models import EventType
from wyckoff.detectors.structure import sc_ar_anchors
from wyckoff.detectors.trading_range import RangeAnchor, detect_trading_ranges
from wyckoff.indicators.core import add_indicators
from wyckoff.pipeline import analyze

ZONE = SellingClimaxConfig(zone_bars=3, zone_undercut_atr=0.5)
CLIMAX = 80


def _climax_frame(next_low: float, third_close: float = 96.0) -> pd.DataFrame:
    """Giảm đều rồi nến climax đóng cửa sát đáy tại CLIMAX (đáy 90, giữa nến 94); phiên sau đáy `next_low`,
    phiên thứ ba sau đóng cửa `third_close`."""
    rows = [(c + 0.1, c + 0.5, c - 0.5, c, 1_000.0) for c in np.linspace(130.0, 99.0, CLIMAX)]
    rows.append((98.0, 98.0, 90.0, 90.2, 4_000.0))
    rows.append((90.3, 91.0, next_low, 90.6, 1_500.0))
    rows.append((90.6, 91.5, 90.4, 91.2, 1_000.0))
    rows.append((91.2, third_close + 0.2, 91.0, third_close, 1_000.0))
    rows += [(third_close, third_close + 0.5, third_close - 0.5, third_close, 1_000.0)] * 3
    idx = pd.bdate_range("2024-01-01", periods=len(rows))
    return add_indicators(pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"], index=idx))


def _scs(df: pd.DataFrame, cfg: SellingClimaxConfig) -> list:
    return [e for e in detect_selling_climax(df, cfg) if e.kind == EventType.SC]


def test_default_config_still_rejects_undercut_climax():
    assert _scs(_climax_frame(next_low=89.8), SellingClimaxConfig()) == []


def test_zone_accepts_small_undercut_and_uses_zone_low():
    sc = _scs(_climax_frame(next_low=89.8), ZONE)
    assert [e.idx for e in sc] == [CLIMAX] and sc[0].confirmed_idx == CLIMAX + 3
    assert sc[0].low == pytest.approx(89.8) and sc[0].details["climax_bar_low"] == pytest.approx(90.0)


def test_zone_rejects_deep_undercut():
    df = _climax_frame(next_low=85.0)
    limit = 90.0 - 0.5 * df["atr_ref"].iloc[CLIMAX]
    assert 85.0 < limit and _scs(df, ZONE) == []


def test_zone_is_causal():
    df = _climax_frame(next_low=89.8)
    assert _scs(df.iloc[:CLIMAX + 3], ZONE) == []
    assert [e.idx for e in _scs(df.iloc[:CLIMAX + 4], ZONE)] == [CLIMAX]


def _flat(n: int = 60, c: float = 100.0) -> pd.DataFrame:
    rows = [(c, c + 1.0, c - 1.0, c, 1_000.0)] * n
    return add_indicators(pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"],
                                       index=pd.bdate_range("2024-01-01", periods=n)))


def test_anchor_opens_range_at_ar_confirmation():
    df = _flat()
    ranges = detect_trading_ranges(df, [], RangeConfig(), [RangeAnchor(20, 30, 95.0, 105.0)])
    assert len(ranges) == 1
    r = ranges[0]
    assert r.anchored and (r.start_idx, r.confirmed_idx, r.support, r.resistance) == (20, 30, 95.0, 105.0)


def test_anchor_too_tall_is_ignored():
    df = _flat()
    atr = df["atr"].iloc[30]
    assert detect_trading_ranges(df, [], RangeConfig(), [RangeAnchor(20, 30, 100.0, 100.0 + 6.5 * atr)]) == []


def _cfg_h4b() -> Config:
    cfg = Config()
    return replace(cfg, sc=replace(cfg.sc, zone_bars=3, zone_undercut_atr=0.5), ranges=replace(cfg.ranges, anchor_sc_ar=True))


def test_pipeline_range_anchored_to_sc_and_ar(ohlcv: pd.DataFrame):
    res = analyze(ohlcv, _cfg_h4b())
    sc = next(e for e in res.events if e.kind == EventType.SC)
    ar = next(e for e in res.events if e.kind == EventType.AR)
    r = next(x for x in res.ranges if x.anchored)
    assert (r.support, r.resistance, r.start_idx, r.confirmed_idx) == (sc.low, ar.high, sc.idx, ar.confirmed_idx)
    assert res.current().phase == "E"
    structure = res.phases.structures[int(res.phases.series["structure_id"].iloc[-1])]
    assert structure.sc is sc and structure.rng.anchored
    assert sc_ar_anchors([sc], [ar]) == [RangeAnchor(sc.idx, ar.confirmed_idx, sc.low, ar.high)]


def test_h4b_has_no_lookahead(ohlcv: pd.DataFrame):
    cfg = _cfg_h4b()
    full = analyze(ohlcv, cfg)
    for t in (90, 130, 170, 200):
        cut = analyze(ohlcv.iloc[:t + 1], cfg)
        want = [(e.kind, e.idx, e.confirmed_idx) for e in full.events if e.confirmed_idx <= t]
        assert [(e.kind, e.idx, e.confirmed_idx) for e in cut.events] == want
        assert cut.phases.series["phase"].fillna("-").tolist() == full.phases.series["phase"].iloc[:t + 1].fillna("-").tolist()
