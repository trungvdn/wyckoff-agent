"""Bối cảnh thị trường: xu hướng chỉ số, RS, phân kỳ đáy, đối chiếu sự kiện, tích hợp payload/báo cáo."""
from __future__ import annotations

import logging
import sys
import types

import numpy as np
import pandas as pd
import pytest

from wyckoff.agent.payload import build_payload, current_structure_events
from wyckoff.agent.report import render_html, template_explanation
from wyckoff.agent.validate import style_issues, validate_explanation
from wyckoff.config import MarketConfig
from wyckoff.market import (
    align_index, benchmark_for, build_market_context, bullish_divergence, event_alignment, market_confidence_factors,
    market_overview, market_regime, relative_strength, trend_conditions,
)
from wyckoff.pipeline import analyze
from wyckoff.synthetic import make_market_index


def _series(values, start: str = "2022-01-03") -> pd.DataFrame:
    c = np.asarray(values, dtype=float)
    idx = pd.bdate_range(start, periods=len(c))
    return pd.DataFrame({"open": c, "high": c * 1.005, "low": c * 0.995, "close": c, "volume": 1e6}, index=idx)


# --------------------------------------------------------------- cơ bản

def test_benchmark_by_exchange() -> None:
    assert benchmark_for("hose") == "VNINDEX" and benchmark_for("HNX") == "HNXINDEX" and benchmark_for("UPCOM") == "UPCOMINDEX"
    with pytest.raises(ValueError):
        benchmark_for("NYSE")


@pytest.mark.parametrize("values,label", [
    (np.linspace(100, 200, 300), "uptrend"),
    (np.linspace(200, 100, 300), "downtrend"),
    (150 + 5 * np.sin(np.arange(300) / 4), "sideways"),
])
def test_market_regime_labels(values, label: str) -> None:
    reg = market_regime(_series(values))
    assert reg["trend"].iloc[-1] == label
    assert reg["trend"].iloc[:199].isna().all()       # chưa đủ 200 phiên cho SMA200


def test_relative_strength() -> None:
    idx = _series(np.linspace(100, 120, 120))
    same = _series(np.linspace(100, 120, 120) * 2)
    rs = relative_strength(same, idx)
    assert np.allclose(rs["rs"], 2.0) and np.allclose(rs["rs_chg_60"].dropna(), 0.0)
    faster = _series(np.linspace(100, 150, 120))
    assert relative_strength(faster, idx)["rs_chg_60"].iloc[-1] > 0


def test_align_index_ffill_no_future() -> None:
    stock = _series(np.ones(10) * 10)
    idx = _series(np.arange(10) + 100.0).drop(index=stock.index[5])
    al = align_index(stock, idx)
    assert al["close"].iloc[5] == 104.0                # lấy phiên trước, không lấy phiên sau (106)


def test_bullish_divergence() -> None:
    n = 60
    idx_vals = np.r_[np.full(40, 100.0), np.full(20, 95.0)]       # 20 phiên cuối: chỉ số tạo đáy thấp hơn
    held = np.r_[np.full(40, 10.0), np.full(20, 10.5)]            # cổ phiếu giữ đáy
    broke = np.r_[np.full(40, 10.0), np.full(20, 9.0)]            # cổ phiếu cũng thủng
    idx = _series(idx_vals)
    assert bool(bullish_divergence(_series(held), idx, 20)["divergence"].iloc[-1]) is True
    assert bool(bullish_divergence(_series(broke), idx, 20)["divergence"].iloc[-1]) is False
    assert pd.isna(bullish_divergence(_series(held), idx, 20)["divergence"].iloc[n // 2])   # chưa đủ 2 cửa sổ


def test_market_series_no_lookahead() -> None:
    idx = make_market_index(pd.bdate_range("2021-01-04", periods=400))
    stock = _series(100 + 10 * np.sin(np.arange(400) / 9), "2021-01-04")
    full_reg, full_rs = market_regime(idx), relative_strength(stock, idx)
    for cut in (210, 300, 399):
        pd.testing.assert_series_equal(market_regime(idx.iloc[:cut])["trend"], full_reg["trend"].iloc[:cut])
        pd.testing.assert_frame_equal(relative_strength(stock.iloc[:cut], idx.iloc[:cut]), full_rs.iloc[:cut])


# ------------------------------------------------------------- context

@pytest.fixture
def ctx_setup(ohlcv: pd.DataFrame):
    res = analyze(ohlcv)
    idx = make_market_index(ohlcv.index)
    return res, idx


def test_build_market_context(ctx_setup) -> None:
    res, idx = ctx_setup
    ctx = build_market_context(res.df, idx, "VNINDEX", current_structure_events(res), index_current={"phase": "B"})
    assert ctx["benchmark"] == "VNINDEX" and ctx["trend"] in ("uptrend", "downtrend", "sideways")
    assert set(ctx["rs"]) == {"rs_change_20d_pct", "rs_change_60d_pct", "rs_above_sma"}
    assert [a["event"] for a in ctx["event_alignment"]][0] == "SC"
    assert ctx["index_phase_reference"] == {"phase": "B"} and ctx["warnings"] == []


def test_context_ignores_future_index_rows(ctx_setup) -> None:
    res, _ = ctx_setup
    longer = make_market_index(pd.bdate_range(res.df.index[0], periods=len(res.df) + 30))
    ctx = build_market_context(res.df, longer, "VNINDEX", [])
    assert ctx["index_last_date"] == f"{res.df.index[-1]:%Y-%m-%d}"


def test_context_warns_when_index_short(ctx_setup) -> None:
    res, idx = ctx_setup
    ctx = build_market_context(res.df, idx.iloc[:-3], "VNINDEX", [])
    assert ctx["warnings"] and "VNINDEX" in ctx["warnings"][0]


def test_event_alignment_change(ctx_setup) -> None:
    res, idx = ctx_setup
    ev = current_structure_events(res)[:1]
    (a,) = event_alignment(ev, idx, market_regime(idx))
    d = ev[0].date
    expected = (idx["close"].loc[d] / idx["close"].shift(1).loc[d] - 1) * 100
    assert a["index_change_pct"] == pytest.approx(round(expected, 2))


@pytest.mark.parametrize("trend,rs,div,points", [
    ("uptrend", 5.0, False, [1, 1]),          # RS > +3% -> +1
    ("downtrend", -5.0, False, [-1, -1]),     # RS < -3% -> -1
    ("uptrend", 1.0, False, [0, 0]),          # |RS| < 3% -> đi ngang, 0; GT2 mặc định: uptrend không cộng
    ("sideways", 1.0, True, [0, 1]),          # RS 0 + phân kỳ +1 -> nhóm +1
    ("sideways", 5.0, True, [0, 1]),          # RS +1 + phân kỳ +1 -> nhóm tối đa +1
    ("downtrend", -5.0, True, [-1, 0]),       # RS -1 + phân kỳ +1 -> 0
    (None, None, False, [0]),
])
def test_market_confidence_factors(trend, rs, div, points) -> None:
    ctx = {"benchmark": "VNINDEX", "trend": trend, "index_close": 1, "sma_fast": 1, "sma_slow": 1,
           "rs": {"rs_change_60d_pct": rs}, "divergence": {"bullish_divergence": div, "index_recent_low": 1,
                                                           "index_prior_low": 2, "stock_recent_low": 3, "stock_prior_low": 2}}
    assert [f["points"] for f in market_confidence_factors(ctx)] == points
    assert market_confidence_factors(None) == []


def test_rs_band_configurable() -> None:
    ctx = {"benchmark": "VNINDEX", "trend": None, "index_close": 1, "sma_fast": 1, "sma_slow": 1,
           "rs": {"rs_change_60d_pct": 1.0}, "divergence": {"bullish_divergence": False}}
    assert market_confidence_factors(ctx, MarketConfig(rs_neutral_band_pct=0.5))[-1]["points"] == 1


def test_hpg_like_case_scores_medium() -> None:
    """Trường hợp HPG 03/11/2026: VNINDEX giảm, RS 60 phiên +1,0%, có phân kỳ -> tổng thị trường 0."""
    ctx = {"benchmark": "VNINDEX", "trend": "downtrend", "index_close": 1699.62, "sma_fast": 1772.05, "sma_slow": 1793.39,
           "rs": {"rs_change_60d_pct": 1.0}, "divergence": {"bullish_divergence": True, "index_recent_low": 1677.19,
                                                            "index_prior_low": 1731.03, "stock_recent_low": 19.85,
                                                            "stock_prior_low": 19.6}}
    f = market_confidence_factors(ctx)
    assert [x["points"] for x in f] == [-1, 1] and "đi ngang so với thị trường" in f[1]["evidence"]
    assert "1.699,62" in f[0]["evidence"]


# ------------------------------------------------------- payload / báo cáo

def test_payload_with_market(ctx_setup) -> None:
    res, idx = ctx_setup
    ctx = build_market_context(res.df, idx, "VNINDEX", current_structure_events(res))
    p = build_payload(res, "DEMO", ctx)
    assert p["market"]["benchmark"] == "VNINDEX"
    factors = [f["factor"] for f in p["confidence"]["factors"]]
    assert any("VNINDEX xu hướng" in f for f in factors) and any(f.startswith("Sức mạnh tương đối") for f in factors)
    assert p["confidence"]["score"] == sum(f["points"] for f in p["confidence"]["factors"])
    t = template_explanation(p)
    assert validate_explanation(t, p) == [] and style_issues(t["market_assessment"]) == []
    page = render_html(p, t, source="template", rs_chart_html="<div id='rs'></div>")
    assert "Bối cảnh thị trường" in page and "Chỉ số trong phiên sự kiện" in page and "id='rs'" in page


def test_payload_without_market(ohlcv: pd.DataFrame) -> None:
    p = build_payload(analyze(ohlcv), "DEMO")
    assert p["market"] is None
    t = template_explanation(p)
    assert t["market_assessment"] == "Không có dữ liệu thị trường." and validate_explanation(t, p) == []
    assert "Bối cảnh thị trường" in render_html(p, t, source="template")


def test_llm_market_text_checked(ctx_setup) -> None:
    res, idx = ctx_setup
    p = build_payload(res, "DEMO", build_market_context(res.df, idx, "VNINDEX", current_structure_events(res)))
    t = template_explanation(p)
    t["market_assessment"] = "VN-Index rs_change_60d_pct cao, mục tiêu 1.500 điểm."
    errs = validate_explanation(t, p)
    assert any("rs_change_60d_pct" in e for e in errs) and any("1.500" in e for e in errs)


# --------------------------------------------------------------- dữ liệu

def test_index_source_uses_market_index(monkeypatch: pytest.MonkeyPatch) -> None:
    from wyckoff.data.fetcher import vnstock_index_source

    calls = {}
    data = make_market_index(pd.bdate_range("2024-01-01", periods=30)).reset_index().rename(columns={"index": "time"})

    class _Idx:
        def __init__(self, sym):
            calls["symbol"] = sym

        def ohlcv(self, **kw):
            calls.update(kw)
            return data

    class _Market:
        def index(self, sym):
            return _Idx(sym)

    monkeypatch.setitem(sys.modules, "vnstock", types.SimpleNamespace(Market=_Market))
    out = vnstock_index_source()("VNINDEX", "2024-01-01", "2024-02-09")
    assert calls["symbol"] == "VNINDEX" and calls["source"] == "kbs" and len(out) == 30


def test_loader_skips_limit_check_for_index(tmp_path, caplog) -> None:
    from wyckoff.data.loader import get_ohlcv

    idx = make_market_index(pd.bdate_range("2024-01-01", periods=30))
    idx.iloc[10:, :4] *= 0.8                                # -20% một phiên: hợp lệ với chỉ số? vẫn không cảnh báo
    raw = idx.reset_index().rename(columns={"index": "time"})
    caplog.set_level(logging.WARNING)
    get_ohlcv("VNINDEX", "2024-01-01", "2024-02-09", cache_dir=tmp_path, source_fn=lambda *a: raw, check_limits=False)
    assert "CHƯA điều chỉnh" not in caplog.text


@pytest.mark.parametrize("trend,rs,points", [
    ("uptrend", 5.0, [1, 1]),       # RS > +3% -> uptrend vẫn +1
    ("uptrend", 1.0, [0, 0]),       # RS đi ngang -> uptrend 0
    ("uptrend", -5.0, [0, -1]),     # RS yếu -> uptrend 0
    ("uptrend", None, [0]),         # thiếu RS -> 0
    ("downtrend", 5.0, [-1, 1]),    # downtrend giữ -1
])
def test_trend_up_requires_rs(trend, rs, points) -> None:
    ctx = {"benchmark": "VNINDEX", "trend": trend, "index_close": 1, "sma_fast": 1, "sma_slow": 1,
           "rs": {"rs_change_60d_pct": rs}, "divergence": {"bullish_divergence": False}}
    f = market_confidence_factors(ctx, MarketConfig(trend_up_requires_rs=True))
    assert [x["points"] for x in f] == points
    if trend == "uptrend" and points[0] == 0:
        assert "không cộng điểm" in f[0]["factor"]


def test_context_benchmark_for() -> None:
    from wyckoff.market import context_benchmark_for
    assert context_benchmark_for("HOSE", MarketConfig()) == "VNINDEX"
    assert context_benchmark_for("HOSE", MarketConfig(context_benchmark="VNSML")) == "VNSML"


def test_study_uses_context_index(ohlcv: pd.DataFrame) -> None:
    from dataclasses import replace as dc_replace
    from wyckoff.backtest.study import study_symbol
    from wyckoff.config import Config
    from wyckoff.synthetic import make_market_index
    cfg = Config()
    cfg = dc_replace(cfg, backtest=dc_replace(cfg.backtest, min_history_bars=60))
    idx = make_market_index(ohlcv.index)
    other = idx.copy()
    other[["open", "high", "low", "close"]] = other[["open", "high", "low", "close"]].iloc[::-1].to_numpy()
    start = str(ohlcv.index[0].date())
    a = study_symbol("DEMO", ohlcv, cfg, idx, "VNINDEX", start=start)
    b = study_symbol("DEMO", ohlcv, cfg, idx, "VNINDEX", start=start, context_index=other, context_benchmark="VNSML")
    pd.testing.assert_series_equal(a.signals["bexcess_20"], b.signals["bexcess_20"])   # thước đo không đổi
    assert not a.signals["rs_60"].equals(b.signals["rs_60"])                           # bối cảnh đổi


def test_trend_up_without_rs_requirement_v1_behaviour() -> None:
    ctx = {"benchmark": "VNINDEX", "trend": "uptrend", "index_close": 1, "sma_fast": 1, "sma_slow": 1,
           "rs": {"rs_change_60d_pct": 1.0}, "divergence": {"bullish_divergence": False}}
    assert [f["points"] for f in market_confidence_factors(ctx, MarketConfig(trend_up_requires_rs=False))] == [1, 0]


def test_gt2_is_default_and_v1_configs_disable_it() -> None:
    from wyckoff.config import load_config
    assert MarketConfig().trend_up_requires_rs is True
    assert load_config("config/default.yaml").market.trend_up_requires_rs is True
    assert load_config("config/v1.yaml").market.trend_up_requires_rs is False
    assert load_config("config/v2_pre_gt2.yaml").market.trend_up_requires_rs is False


# --------------------------------------------------------------- trang thị trường

@pytest.mark.parametrize("values, kind, side", [
    (np.linspace(100, 300, 320), "uptrend", "up"),
    (np.linspace(300, 100, 320), "downtrend", "down"),
])
def test_overview_conditions_match_regime(values, kind, side):
    o = market_overview(_series(values))
    other = "down" if side == "up" else "up"
    assert o["trend"]["kind"] == kind
    assert all(c["met"] for c in o["conditions"][side]) and not any(c["met"] for c in o["conditions"][other])


def test_overview_conditions_agree_with_regime_every_session():
    """Đạt đủ ba điều kiện một chiều <=> market_regime gắn đúng nhãn đó, trên chuỗi có đủ cả ba trạng thái."""
    idx = _series(100 + 30 * np.sin(np.arange(1200) * 2 * np.pi / 500))
    cfg = MarketConfig()
    r = market_regime(idx, cfg)
    seen = set()
    for i in range(cfg.sma_slow + cfg.slope_bars, len(idx)):
        conds = trend_conditions(idx["close"].iloc[i], r["sma_fast"].iloc[i], r["sma_slow"].iloc[i], r["sma_fast"].iloc[i - cfg.slope_bars], cfg)
        kind = r["trend"].iloc[i]
        seen.add(kind)
        assert all(c["met"] for c in conds["up"]) == (kind == "uptrend")
        assert all(c["met"] for c in conds["down"]) == (kind == "downtrend")
    assert seen == {"uptrend", "downtrend", "sideways"}


def test_overview_condition_gaps():
    c = trend_conditions(1725.36, 1769.06, 1791.07, 1779.82)["up"]
    assert [x["met"] for x in c] == [False, False, False]
    assert c[0]["gap_pct"] == 2.53 and c[0]["threshold"] == 1769.06
    assert c[1]["gap_points"] == 22.01
    assert c[2]["slope_pct"] == -0.6


def test_overview_numbers_and_segments():
    values = np.r_[np.linspace(100, 200, 300), np.linspace(200, 150, 60)]
    idx = _series(values)
    o = market_overview(idx)
    assert o["close"] == pytest.approx(150) and o["as_of"] == f"{idx.index[-1]:%Y-%m-%d}"
    assert o["change_pct"] == pytest.approx((values[-1] / values[-2] - 1) * 100, abs=0.01)
    r60 = next(x for x in o["returns"] if x["window"] == 60)
    assert r60["pct"] == pytest.approx((values[-1] / values[-61] - 1) * 100, abs=0.01) and r60["from_date"] == f"{idx.index[-61]:%Y-%m-%d}"
    # đỉnh tính theo high của 250 phiên, cùng định nghĩa với bối cảnh thị trường ở trang cổ phiếu
    d = o["drawdown"]
    assert d["peak"] == pytest.approx(200 * 1.005) and d["peak_date"] == f"{idx.index[299]:%Y-%m-%d}" and d["sessions_since"] == 60
    assert d["pct"] == pytest.approx((150 / (200 * 1.005) - 1) * 100, abs=0.01)
    # các đoạn liền nhau, kết thúc ở nến cuối, khớp nhãn của market_regime
    segs, labels = o["trend_segments"], market_regime(idx)["trend"]
    assert segs[-1]["i1"] == len(idx) - 1 and all(a["i1"] + 1 == b["i0"] for a, b in zip(segs, segs[1:]))
    assert all((labels.iloc[s["i0"]: s["i1"] + 1] == s["kind"]).all() for s in segs)
    last = segs[-1]
    assert o["trend"]["since"] == o["bars"][last["i0"]]["t"] and o["trend"]["sessions"] == last["i1"] - last["i0"] + 1
    assert len(o["bars"]) == len(idx) and o["bars"][0]["vma"] is None and o["bars"][-1]["vma"] == 1_000_000
    # SMA20 chỉ để vẽ
    assert o["sma_short_period"] == 20 and o["bars"][18]["sma_short"] is None
    assert o["bars"][-1]["sma_short"] == pytest.approx(values[-20:].mean(), abs=0.01)


def test_overview_short_history_has_no_trend():
    o = market_overview(_series(np.linspace(100, 110, 100)))
    assert o["trend"]["kind"] is None and o["conditions"] is None and o["trend_segments"] == []
    assert o["trend"]["since"] is None and o["bars"][-1]["sma_slow"] is None
    assert next(x for x in o["returns"] if x["window"] == 120)["pct"] is None
