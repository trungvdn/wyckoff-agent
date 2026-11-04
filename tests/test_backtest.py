"""Backtest / event study: đo lợi suất, nền, CI, point-in-time không nhìn trước, kịch bản, tổng hợp, HTML."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from wyckoff.backtest.metrics import baseline_returns, bootstrap_mean_ci, forward_metrics, scenario_race
from wyckoff.backtest.report import render_backtest_html
from wyckoff.backtest.study import study_symbol
from wyckoff.backtest.summary import summarize
from wyckoff.config import Config
from wyckoff.synthetic import SOS_IDX, SPRING_CONFIRM_IDX, SPRING_IDX, make_market_index


def _px(opens, closes, highs=None, lows=None) -> pd.DataFrame:
    o, c = np.asarray(opens, float), np.asarray(closes, float)
    h = np.asarray(highs, float) if highs is not None else np.maximum(o, c)
    lo = np.asarray(lows, float) if lows is not None else np.minimum(o, c)
    return pd.DataFrame({"open": o, "high": h, "low": lo, "close": c, "volume": 1.0},
                        index=pd.bdate_range("2024-01-01", periods=len(o)))


@pytest.fixture
def cfg() -> Config:
    c = Config()
    return replace(c, backtest=replace(c.backtest, min_history_bars=60, bootstrap_n=500))


# ------------------------------------------------------------------ metrics

def test_forward_metrics_entry_next_open() -> None:
    df = _px([10, 10, 11, 12, 13], [10, 10.5, 12, 12.5, 14], highs=[10, 11, 12.5, 13, 15], lows=[9.5, 9.8, 10.8, 11.5, 12.9])
    idx = _px([100, 100, 100, 100, 100], [100, 100, 101, 102, 104])
    m = forward_metrics(df, idx, signal_idx=1, horizons=(2, 3), cost_pct=0.3)
    assert m["entry_date"] == df.index[2] and m["entry_price"] == 11
    assert m["ret_2"] == pytest.approx((12.5 / 11 - 1) * 100 - 0.3)          # close phiên 3
    assert m["excess_2"] == pytest.approx(m["ret_2"] - (102 / 100 - 1) * 100)
    assert m["mfe_3"] == pytest.approx((15 / 11 - 1) * 100) and m["mae_3"] == pytest.approx((10.8 / 11 - 1) * 100)
    assert np.isnan(forward_metrics(df, idx, 3, (3,))["ret_3"])               # chưa đủ phiên


def test_forward_metrics_flags_ceiling_open() -> None:
    df = _px([10, 10.7, 10.8], [10, 10.8, 11])
    assert forward_metrics(df, None, 0, (1,), price_limit=0.07)["untradable"] is True
    assert forward_metrics(df, None, 1, (1,), price_limit=0.07)["untradable"] is False


def test_forward_metrics_no_entry_on_last_bar() -> None:
    df = _px([10, 11], [10, 11])
    m = forward_metrics(df, None, 1, (5,))
    assert m["entry_date"] is None and np.isnan(m["ret_5"])


def test_baseline_matches_loop() -> None:
    rng = np.random.default_rng(1)
    c = 20 * np.cumprod(1 + rng.normal(0, 0.02, 80))
    o = np.r_[c[0], c[:-1]] * (1 + rng.normal(0, 0.003, 80))
    df = _px(o, c)
    idx = _px(np.linspace(1000, 1100, 80), np.linspace(1001, 1101, 80))
    base = baseline_returns(df, idx, (5, 20), cost_pct=0.3, first_signal_idx=10)
    for t in (10, 30, 54):
        m = forward_metrics(df, idx, t, (5, 20), cost_pct=0.3)
        assert base.loc[df.index[t], "ret_5"] == pytest.approx(m["ret_5"])
        assert base.loc[df.index[t], "excess_20"] == pytest.approx(m["excess_20"])
    assert base.index[0] == df.index[10] and np.isnan(base["ret_20"].iloc[-1])


def test_bootstrap_ci() -> None:
    v = np.r_[np.full(50, 1.0), np.full(50, 3.0)]
    lo, hi = bootstrap_mean_ci(v, n=1000, ci=0.9, seed=1)
    assert lo < 2.0 < hi and hi - lo < 0.6
    assert bootstrap_mean_ci(np.array([1.0]))[0] != bootstrap_mean_ci(np.array([1.0]))[0]   # NaN


@pytest.mark.parametrize("closes,up,down,expected", [
    ([10, 10.5, 12, 9], 11.0, 9.5, ("xác nhận", 2)),
    ([10, 9.8, 9.2, 12], 11.0, 9.5, ("vô hiệu", 2)),
    ([10, 10.1, 10.2, 10.3], 11.0, 9.5, ("chưa rõ", None)),
    ([10, 10.1], None, None, ("không áp dụng", None)),
])
def test_scenario_race(closes, up, down, expected) -> None:
    assert scenario_race(np.asarray(closes, float), 0, up, down, max_bars=10) == expected


# -------------------------------------------------------------------- study

def test_study_symbol_synthetic(ohlcv: pd.DataFrame, cfg: Config) -> None:
    idx = make_market_index(ohlcv.index)
    st = study_symbol("DEMO", ohlcv, cfg, idx, "VNINDEX", start=str(ohlcv.index[0].date()))
    s = st.signals
    spring = s[s["kind"] == "Spring (volume thấp)"].iloc[0]
    assert spring["t"] == SPRING_CONFIRM_IDX and spring["entry_date"] == ohlcv.index[SPRING_CONFIRM_IDX + 1]
    assert spring["event_date"] == ohlcv.index[SPRING_IDX] and spring["pit_phase"] == "C"
    assert spring["scenario"] == "xác nhận" and spring["scenario_bars"] == SOS_IDX - SPRING_CONFIRM_IDX
    assert {"pha A", "pha B", "pha C", "pha D", "SC", "AR", "ST", "SOS"} <= set(s["kind"])
    assert len(st.baseline) == len(ohlcv) - 60 and (st.baseline["symbol"] == "DEMO").all()


def test_point_in_time_ignores_future(ohlcv: pd.DataFrame, cfg: Config) -> None:
    """Phá dữ liệu SAU phiên xác nhận Spring: pha/tin cậy/mức giá tại phiên đó không được đổi."""
    idx = make_market_index(ohlcv.index)
    start = str(ohlcv.index[0].date())
    a = study_symbol("DEMO", ohlcv, cfg, idx, "VNINDEX", start=start).signals
    broken = ohlcv.copy()
    broken.iloc[SPRING_CONFIRM_IDX + 1:, :4] *= 0.5
    b = study_symbol("DEMO", broken, cfg, idx, "VNINDEX", start=start).signals
    cols = ["pit_phase", "confidence_level", "confidence_score", "up_level", "down_level", "market_trend", "rs_60"]
    ra = a[a["kind"] == "Spring (volume thấp)"].iloc[0]
    rb = b[b["kind"] == "Spring (volume thấp)"].iloc[0]
    for c in cols:
        assert (pd.isna(ra[c]) and pd.isna(rb[c])) or ra[c] == pytest.approx(rb[c]) if isinstance(ra[c], float) else ra[c] == rb[c]


def test_start_filter_and_no_pit(ohlcv: pd.DataFrame, cfg: Config) -> None:
    no_pit = replace(cfg, backtest=replace(cfg.backtest, point_in_time=False))
    st = study_symbol("DEMO", ohlcv, no_pit, None, None, start=str(ohlcv.index[150].date()))
    assert (st.signals["signal_date"] >= ohlcv.index[150]).all() and "confidence_level" not in st.signals
    assert st.signals["excess_20"].isna().all()                              # không có chỉ số


# ---------------------------------------------------------------- summary

def test_summarize_and_report(ohlcv: pd.DataFrame, cfg: Config) -> None:
    idx = make_market_index(ohlcv.index)
    st = study_symbol("DEMO", ohlcv, cfg, idx, "VNINDEX", start=str(ohlcv.index[0].date()))
    sm = summarize(st.signals, st.baseline, cfg.backtest)
    assert set(sm) >= {"baseline", "by_kind", "by_confidence", "by_score", "scenarios", "by_kind_beta", "by_factor"}
    b = sm["baseline"].set_index("horizon")
    assert b.loc[20, "n"] > 0
    k = sm["by_kind"]
    row = k[(k["kind"] == "Spring (volume thấp)") & (k["horizon"] == 20)].iloc[0]
    assert row["n"] == 1 and row["edge_vs_base"] == pytest.approx(row["mean_excess"] - b.loc[20, "mean_excess"])
    assert set(sm["scenarios"]["kind"]) <= {"pha B", "pha C", "pha D"}
    page = render_backtest_html(sm, {"universe": "DEMO", "symbols": ["DEMO"], "start": "2023", "end": "2024",
                                     "n_signals": len(st.signals), "warnings": ["thử"]}, cfg.backtest)
    assert "Event study" in page and "Thiên lệch sống sót" in page and "Spring (volume thấp)" in page and "thử" in page


def test_untradable_excluded(ohlcv: pd.DataFrame, cfg: Config) -> None:
    idx = make_market_index(ohlcv.index)
    st = study_symbol("DEMO", ohlcv, cfg, idx, "VNINDEX", start=str(ohlcv.index[0].date()))
    sig = st.signals.copy()
    sig.loc[sig["kind"] == "SOS", "untradable"] = True
    k = summarize(sig, st.baseline, cfg.backtest)["by_kind"]
    assert "SOS" not in set(k["kind"])


# ------------------------------------------------------------ chẩn đoán (bước 1)

from wyckoff.backtest.metrics import rolling_beta  # noqa: E402
from wyckoff.backtest.summary import breakdown, by_factor, by_kind_beta, by_kind_period, diagnose  # noqa: E402


def _levered(beta: float, n: int = 300, seed: int = 3) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    ri = rng.normal(0, 0.01, n)
    idx_c = 1000 * np.cumprod(1 + ri)
    st_c = 20 * np.cumprod(1 + beta * ri)
    return _px(np.r_[idx_c[0], idx_c[:-1]], idx_c), _px(np.r_[st_c[0], st_c[:-1]], st_c)


def test_rolling_beta_recovers_leverage() -> None:
    idx, st = _levered(1.7)
    b = rolling_beta(st, idx, window=250, min_periods=120)
    assert b.iloc[:119].isna().all() and b.iloc[-1] == pytest.approx(1.7, abs=1e-6)


def test_rolling_beta_no_lookahead() -> None:
    idx, st = _levered(1.3)
    full = rolling_beta(st, idx)
    part = rolling_beta(st.iloc[:200], idx.iloc[:200])
    pd.testing.assert_series_equal(part, full.iloc[:200])


def test_bexcess_removes_beta() -> None:
    idx, st = _levered(2.0)
    m = forward_metrics(st, idx, 150, (20,), cost_pct=0.0, beta=2.0)
    assert abs(m["bexcess_20"]) < abs(m["excess_20"]) or abs(m["excess_20"]) < 1e-6
    base = baseline_returns(st, idx, (20,), cost_pct=0.0, beta=pd.Series(2.0, index=st.index))
    assert base.loc[st.index[150], "bexcess_20"] == pytest.approx(m["bexcess_20"])


def test_study_has_diagnostic_columns(ohlcv: pd.DataFrame, cfg: Config) -> None:
    idx = make_market_index(ohlcv.index)
    s = study_symbol("DEMO", ohlcv, cfg, idx, "VNINDEX", start=str(ohlcv.index[0].date()))
    sig = s.signals
    sp = sig[sig["kind"] == "Spring (volume thấp)"].iloc[0]
    assert sp["spring_type"] == "low_volume" and sp["pen_atr"] > 0 and sp["recovery_bars"] == 2
    assert sp["range_bars"] == SPRING_CONFIRM_IDX - 100 and sp["range_height_atr"] > 0
    assert {"f_sc", "f_st", "f_spring", "f_mkttrend", "f_relstrength", "f_rangectx"} <= set(sig.columns)
    assert sp["f_sc"] == 1 and sp["f_spring"] == 0 and sp["h_spring"] == 1
    assert set(sig["period"]) <= {"2023–2022", "2023–nay"} and "period" in s.baseline
    sos = sig[sig["kind"] == "SOS"].iloc[0]
    assert sos["breakout_atr"] > 0


def test_factor_keys_in_payload(ohlcv: pd.DataFrame) -> None:
    from wyckoff.agent.payload import build_payload
    from wyckoff.pipeline import analyze

    p = build_payload(analyze(ohlcv.iloc[:SPRING_CONFIRM_IDX + 5]), "DEMO")
    keys = {f["key"] for f in p["confidence"]["factors"]}
    assert {"sc", "st", "spring", "rangectx"} <= keys and all("_" not in k for k in keys)


def _fake_signals() -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(5)
    n = 80
    sig = pd.DataFrame({
        "kind": ["Spring (volume thấp)"] * 40 + ["SOS"] * 40, "untradable": False,
        "period": ["2018–2022"] * 20 + ["2023–nay"] * 20 + ["2018–2022"] * 20 + ["2023–nay"] * 20,
        "ret_20": rng.normal(0, 5, n), "ret_60": rng.normal(0, 8, n),
        "bexcess_20": np.r_[rng.normal(-2, 3, 40), rng.normal(2, 3, 40)], "bexcess_60": rng.normal(0, 6, n),
        "pen_atr": np.r_[np.full(20, 0.2), np.full(20, 1.2), np.full(40, np.nan)],
        "spring_type": ["low_volume"] * 40 + [None] * 40,
        "f_spring": np.r_[np.ones(40), np.zeros(40)], "f_mkttrend": rng.choice([-1, 0, 1], n),
        "market_trend": rng.choice(["uptrend", "downtrend"], n), "confidence_level": "cao",
        "range_bars": rng.integers(20, 200, n), "breakout_atr": np.r_[np.full(40, np.nan), rng.uniform(0.2, 3, 40)],
        "ev_vol_ratio": rng.uniform(1.5, 4, n),
    })
    base = pd.DataFrame({"period": ["2018–2022"] * 500 + ["2023–nay"] * 500,
                         "bexcess_5": 0.0, "bexcess_20": 0.5, "bexcess_60": 1.0})
    return sig, base


def test_diagnostic_tables() -> None:
    sig, base = _fake_signals()
    bt = Config().backtest
    kb = by_kind_beta(sig, base, bt).set_index("kind")
    assert kb.loc["SOS", "edge_b20"] == pytest.approx(sig[sig.kind == "SOS"]["bexcess_20"].mean() - 0.5)
    assert kb.loc["SOS", "edge_b20_lo"] < kb.loc["SOS", "edge_b20"] < kb.loc["SOS", "edge_b20_hi"]
    kp = by_kind_period(sig, base, bt)
    assert set(kp["period"]) == {"2018–2022", "2023–nay"} and len(kp) == 4
    bf = by_factor(sig, base, bt)
    assert set(bf["factor"]) == {"spring", "mkttrend"} and bf.groupby("factor")["n"].sum().eq(80).all()
    bd = breakdown(sig, base, bt, "Spring")
    pen = bd[bd["attribute"] == "pen_atr"].set_index("bucket")
    assert pen.loc["[0, 0.5)", "n"] == 20 and pen.loc["[1, inf)" if "[1, inf)" in pen.index else "[1, ∞)", "n"] == 20
    assert "volume thấp" in set(bd[bd["attribute"] == "spring_type"]["bucket"])
    assert set(diagnose(sig, base, bt)) >= {"by_kind_beta", "by_kind_period", "by_factor", "breakdown_spring", "breakdown_sos"}


def test_report_has_diagnostics() -> None:
    sig, base = _fake_signals()
    bt = Config().backtest
    sm = {"baseline": pd.DataFrame(), "by_kind": pd.DataFrame(columns=["horizon"]), "by_confidence": pd.DataFrame(),
          "by_score": pd.DataFrame(), "scenarios": pd.DataFrame(), **diagnose(sig, base, bt)}
    page = render_backtest_html(sm, {"universe": "X", "symbols": [], "start": "", "end": "", "n_signals": 80}, bt)
    assert "Chẩn đoán 1" in page and "Chẩn đoán 3" in page and "Spring theo thuộc tính" in page
