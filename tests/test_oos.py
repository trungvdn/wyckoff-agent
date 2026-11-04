"""Test cho kiểm tra ngoài mẫu (wyckoff/backtest/oos.py)."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from wyckoff.backtest.oos import (cluster_spreads, evaluate, evaluate_hypothesis, render_hypothesis, render_markdown,
                                 scale_stats, spread_ci)


def _sig(means: dict[str, float], n: int = 200, seed: int = 0, symbol: str = "AAA", sd: float = 1.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for lv, m in means.items():
        for i in range(n):
            rows.append({"symbol": symbol, "untradable": False, "confidence_level": lv,
                         "bexcess_20": m + sd * rng.standard_normal(), "bexcess_60": 2 * m,
                         "period": "2018–2022" if i % 2 else "2023–nay"})
    return pd.DataFrame(rows)


def test_pass_when_all_criteria_met() -> None:
    v2 = _sig({"thấp": -1.0, "trung bình": 0.5, "cao": 2.0})
    v1 = _sig({"thấp": 0.0, "trung bình": 0.5, "cao": 1.0}, seed=1)
    r = evaluate(v2, v1, n_boot=300)
    assert r.monotonic and r.high_ci_positive and r.beats_v1 and r.passed
    assert set(r.reference["periods"]) == {"2018–2022", "2023–nay"}


def test_fail_not_monotonic() -> None:
    v2 = _sig({"thấp": 1.0, "trung bình": 0.5, "cao": 2.0})
    r = evaluate(v2, _sig({"thấp": 0.0, "trung bình": 0.0, "cao": 0.0}), n_boot=300)
    assert not r.monotonic and not r.passed


def test_fail_high_ci_includes_zero() -> None:
    v2 = _sig({"thấp": -2.0, "trung bình": -1.0, "cao": 0.05}, sd=3.0)
    r = evaluate(v2, _sig({"thấp": 0.0, "trung bình": 0.0, "cao": 0.0}), n_boot=300)
    assert r.monotonic and not r.high_ci_positive and not r.passed


def test_fail_when_v1_spread_larger() -> None:
    v2 = _sig({"thấp": -1.0, "trung bình": 0.5, "cao": 2.0})
    v1 = _sig({"thấp": -3.0, "trung bình": 0.0, "cao": 3.0}, seed=2)
    r = evaluate(v2, v1, n_boot=300)
    assert not r.beats_v1 and not r.passed


def test_exclude_and_untradable_dropped() -> None:
    a = _sig({"thấp": 0.0, "trung bình": 0.0, "cao": 0.0}, n=10, symbol="AAA")
    b = _sig({"thấp": 9.0, "trung bình": 9.0, "cao": 9.0}, n=10, symbol="BBB")
    s = pd.concat([a, b], ignore_index=True)
    s.loc[0, "untradable"] = True
    st = scale_stats(s, "x", exclude={"BBB"}, n_boot=100).by_level()
    assert st["thấp"].n == 9 and st["cao"].n == 10 and abs(st["cao"].mean) < 1.0


def test_spread_ci_contains_true_difference() -> None:
    rng = np.random.default_rng(3)
    lo, hi = rng.normal(0, 1, 500), rng.normal(1, 1, 500)
    a, b = spread_ci(lo, hi, n=500)
    assert a < 1.0 < b


def test_render_markdown_has_verdict() -> None:
    v2 = _sig({"thấp": -1.0, "trung bình": 0.5, "cao": 2.0})
    md = render_markdown(evaluate(v2, v2, n_boot=100), {"universe": "VNMidCap", "n_symbols": 1})
    assert "KHÔNG ĐẠT" in md and "không phải lời khuyên đầu tư" in md   # v2 == v1 -> không hơn v1


def test_cluster_spreads_paired_shape_and_value() -> None:
    a = pd.concat([_sig({"thấp": 0.0, "trung bình": 0.5, "cao": 2.0}, n=30, seed=i, symbol=f"S{i}", sd=0.1)
                   for i in range(5)], ignore_index=True)
    cs = cluster_spreads([a, a], n=200)
    assert cs.shape == (200, 2) and np.allclose(cs[:, 0], cs[:, 1]) and abs(cs[:, 0].mean() - 2.0) < 0.1


def _multi(means: dict[str, float], k: int = 6, seed: int = 0) -> pd.DataFrame:
    return pd.concat([_sig(means, n=60, seed=seed + i, symbol=f"S{i}") for i in range(k)], ignore_index=True)


def test_hypothesis_accepted_when_all_criteria_met() -> None:
    v2 = _multi({"thấp": 0.0, "trung bình": 0.3, "cao": 0.6})
    h = _multi({"thấp": -1.0, "trung bình": 0.5, "cao": 2.0}, seed=50)
    v = evaluate_hypothesis(h, v2, "GT", n_boot=300)
    assert v.monotonic and v.high_ci_positive and v.beats_v2 and v.recent_high60_better and v.p_cluster > 0.95
    assert v.accepted and "CHẤP NHẬN" in render_hypothesis(v)


def test_hypothesis_rejected_when_recent_worse() -> None:
    v2 = _multi({"thấp": 0.0, "trung bình": 0.3, "cao": 0.6})
    h = _multi({"thấp": -1.0, "trung bình": 0.5, "cao": 2.0}, seed=50)
    h.loc[(h["period"] == "2023–nay") & (h["confidence_level"] == "cao"), "bexcess_60"] = -10.0
    v = evaluate_hypothesis(h, v2, "GT", n_boot=300)
    assert not v.recent_high60_better and not v.accepted


def test_reference_index_recomputes_excess(ohlcv: pd.DataFrame) -> None:
    from wyckoff.backtest.oos import with_reference_index
    from wyckoff.backtest.study import study_symbol
    from wyckoff.config import Config
    from wyckoff.synthetic import make_market_index

    cfg = Config()
    cfg = replace(cfg, backtest=replace(cfg.backtest, min_history_bars=60, beta_min_periods=20, beta_window=60))
    idx = make_market_index(ohlcv.index)
    st = study_symbol("DEMO", ohlcv, cfg, idx, "VNINDEX", start=str(ohlcv.index[0].date()))
    same = with_reference_index(st.signals, {"DEMO": ohlcv}, idx, cfg)
    pd.testing.assert_series_equal(same["bexcess_20"], st.signals["bexcess_20"], check_names=False)
    flat = idx.copy()
    flat[["open", "high", "low", "close"]] = 100.0
    ref = with_reference_index(st.signals, {"DEMO": ohlcv}, flat, cfg)
    assert ref["confidence_level"].equals(st.signals["confidence_level"])
    assert not ref["bexcess_20"].equals(st.signals["bexcess_20"])
