"""Tổng hợp kết quả event study."""
from __future__ import annotations

import numpy as np
import pandas as pd

from wyckoff.backtest.metrics import bootstrap_mean_ci
from wyckoff.config import BacktestConfig
from wyckoff.detectors.models import SPRING_TYPE_LABEL

CONF_ORDER = ["thấp", "trung bình", "cao", "không áp dụng"]


def baseline_table(baseline: pd.DataFrame, horizons: tuple[int, ...]) -> pd.DataFrame:
    rows = []
    for H in horizons:
        ex = baseline[f"excess_{H}"].dropna()
        ret = baseline[f"ret_{H}"].dropna()
        rows.append({"horizon": H, "n": len(ret), "mean_ret": ret.mean(), "mean_excess": ex.mean(),
                     "median_excess": ex.median(), "win_rate": (ret > 0).mean() * 100})
    return pd.DataFrame(rows)


def _stats(g: pd.DataFrame, H: int, base_mean_excess: float, cfg: BacktestConfig) -> dict[str, float]:
    ex = g[f"excess_{H}"].to_numpy(dtype=float)
    ret = g[f"ret_{H}"].to_numpy(dtype=float)
    ok = ~np.isnan(ret)
    lo, hi = bootstrap_mean_ci(ex - base_mean_excess, cfg.bootstrap_n, cfg.ci, cfg.seed)
    return {
        "n": int(ok.sum()),
        "mean_ret": float(np.nanmean(ret)) if ok.any() else np.nan,
        "mean_excess": float(np.nanmean(ex)) if ok.any() else np.nan,
        "median_excess": float(np.nanmedian(ex)) if ok.any() else np.nan,
        "win_rate": float((ret[ok] > 0).mean() * 100) if ok.any() else np.nan,
        "edge_vs_base": float(np.nanmean(ex) - base_mean_excess) if ok.any() else np.nan,
        "edge_ci_lo": lo, "edge_ci_hi": hi,
        "mfe": float(np.nanmean(g[f"mfe_{H}"])) if ok.any() else np.nan,
        "mae": float(np.nanmean(g[f"mae_{H}"])) if ok.any() else np.nan,
    }


def by_kind(signals: pd.DataFrame, baseline: pd.DataFrame, cfg: BacktestConfig) -> pd.DataFrame:
    """Mỗi loại tín hiệu x mỗi khung: n, lợi suất, lợi suất vượt, tỉ lệ thắng, chênh so với nền + CI.
    Bỏ các tín hiệu không khớp được (mở cửa giá trần)."""
    sig = signals[signals["untradable"] == False]  # noqa: E712
    base = baseline_table(baseline, cfg.horizons).set_index("horizon")["mean_excess"]
    rows = []
    for kind, g in sig.groupby("kind"):
        for H in cfg.horizons:
            rows.append({"kind": kind, "horizon": H, **_stats(g, H, base[H], cfg)})
    out = pd.DataFrame(rows)
    return out.sort_values(["horizon", "edge_vs_base"], ascending=[True, False]).reset_index(drop=True)


def by_confidence(signals: pd.DataFrame, baseline: pd.DataFrame, cfg: BacktestConfig,
                  kinds: tuple[str, ...] = ("pha C", "pha D", "Spring (volume thấp)", "Spring (shakeout)", "SOS")) -> pd.DataFrame:
    """Hiệu chỉnh mức tin cậy: lợi suất theo mức tin cậy point-in-time (các tín hiệu tăng giá chính)."""
    if "confidence_level" not in signals:
        return pd.DataFrame()
    sig = signals[(signals["untradable"] == False) & signals["kind"].isin(kinds)]  # noqa: E712
    base = baseline_table(baseline, cfg.horizons).set_index("horizon")["mean_excess"]
    rows = []
    for level, g in sig.groupby("confidence_level"):
        for H in cfg.horizons:
            rows.append({"confidence_level": level, "horizon": H, **_stats(g, H, base[H], cfg)})
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["_o"] = out["confidence_level"].map({k: i for i, k in enumerate(CONF_ORDER)})
    return out.sort_values(["horizon", "_o"]).drop(columns="_o").reset_index(drop=True)


def by_score(signals: pd.DataFrame, cfg: BacktestConfig,
             kinds: tuple[str, ...] = ("pha C", "pha D", "Spring (volume thấp)", "Spring (shakeout)", "SOS"),
             horizon: int = 20) -> pd.DataFrame:
    if "confidence_score" not in signals:
        return pd.DataFrame()
    sig = signals[(signals["untradable"] == False) & signals["kind"].isin(kinds)].dropna(subset=["confidence_score"])  # noqa: E712
    g = sig.groupby("confidence_score")
    return pd.DataFrame({
        "n": g[f"ret_{horizon}"].count(),
        "mean_excess": g[f"excess_{horizon}"].mean(),
        "win_rate": g[f"ret_{horizon}"].apply(lambda s: (s.dropna() > 0).mean() * 100),
    }).reset_index()


def scenario_table(signals: pd.DataFrame) -> pd.DataFrame:
    """Tỉ lệ kịch bản xác nhận / vô hiệu / chưa rõ theo pha point-in-time khi mở pha B/C/D."""
    if "scenario" not in signals:
        return pd.DataFrame()
    sig = signals[signals["kind"].isin(["pha B", "pha C", "pha D"])]
    rows = []
    for kind, g in sig.groupby("kind"):
        n = len(g)
        row = {"kind": kind, "n": n}
        for o in ("xác nhận", "vô hiệu", "chưa rõ"):
            sub = g[g["scenario"] == o]
            row[f"{o} %"] = len(sub) / n * 100 if n else np.nan
            row[f"{o} phiên (trung vị)"] = sub["scenario_bars"].median() if len(sub) else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def summarize(signals: pd.DataFrame, baseline: pd.DataFrame, cfg: BacktestConfig) -> dict[str, pd.DataFrame]:
    out = {
        "baseline": baseline_table(baseline, cfg.horizons),
        "by_kind": by_kind(signals, baseline, cfg),
        "by_confidence": by_confidence(signals, baseline, cfg),
        "by_score": by_score(signals, cfg),
        "scenarios": scenario_table(signals),
    }
    out.update(diagnose(signals, baseline, cfg))
    return out


# ----------------------------------------------------------- chẩn đoán (bước 1)

MAIN_KINDS = ("pha C", "pha D", "Spring (volume thấp)", "Spring (shakeout)", "SOS")


def _tradable(signals: pd.DataFrame) -> pd.DataFrame:
    return signals[signals["untradable"] == False]  # noqa: E712


def _bstats(g: pd.DataFrame, base_b: dict[int, float], cfg: BacktestConfig, horizons=(20, 60)) -> dict[str, float]:
    out: dict[str, float] = {"n": int(g["ret_20"].notna().sum()) if "ret_20" in g else len(g)}
    for H in horizons:
        col = f"bexcess_{H}"
        if col not in g:
            continue
        v = g[col].to_numpy(dtype=float)
        out[f"mean_b{H}"] = float(np.nanmean(v)) if np.isfinite(v).any() else np.nan
        out[f"edge_b{H}"] = out[f"mean_b{H}"] - base_b.get(H, np.nan)
        lo, hi = bootstrap_mean_ci(v - base_b.get(H, np.nan), cfg.bootstrap_n, cfg.ci, cfg.seed)
        out[f"edge_b{H}_lo"], out[f"edge_b{H}_hi"] = lo, hi
        r = g[f"ret_{H}"].dropna()
        out[f"win_{H}"] = float((r > 0).mean() * 100) if len(r) else np.nan
    return out


def baseline_beta(baseline: pd.DataFrame, horizons: tuple[int, ...], by_period: bool = False) -> dict:
    if by_period:
        return {p: {H: float(g[f"bexcess_{H}"].mean()) for H in horizons} for p, g in baseline.groupby("period")}
    return {H: float(baseline[f"bexcess_{H}"].mean()) for H in horizons}


def by_kind_beta(signals: pd.DataFrame, baseline: pd.DataFrame, cfg: BacktestConfig) -> pd.DataFrame:
    """Lợi suất vượt đã điều chỉnh beta (bexcess) theo loại tín hiệu, so với nền cùng cách đo."""
    base = baseline_beta(baseline, cfg.horizons)
    rows = [{"kind": k, **_bstats(g, base, cfg)} for k, g in _tradable(signals).groupby("kind")]
    return pd.DataFrame(rows).sort_values("edge_b60", ascending=False).reset_index(drop=True)


def by_kind_period(signals: pd.DataFrame, baseline: pd.DataFrame, cfg: BacktestConfig) -> pd.DataFrame:
    """Độ ổn định: cùng phép đo, tách theo giai đoạn (nền tính riêng từng giai đoạn)."""
    base = baseline_beta(baseline, cfg.horizons, by_period=True)
    rows = []
    for (k, p), g in _tradable(signals).groupby(["kind", "period"]):
        rows.append({"kind": k, "period": p, **_bstats(g, base.get(p, {}), cfg)})
    return pd.DataFrame(rows).sort_values(["kind", "period"]).reset_index(drop=True)


def by_factor(signals: pd.DataFrame, baseline: pd.DataFrame, cfg: BacktestConfig,
              kinds: tuple[str, ...] = MAIN_KINDS) -> pd.DataFrame:
    """Đóng góp từng yếu tố tin cậy: kết quả theo điểm của yếu tố đó (tín hiệu tăng giá chính)."""
    sig = _tradable(signals)
    sig = sig[sig["kind"].isin(kinds)]
    base = baseline_beta(baseline, cfg.horizons)
    rows = []
    for col in sorted(c for c in sig.columns if c.startswith("f_")):
        for val, g in sig.groupby(sig[col].fillna(0)):
            rows.append({"factor": col[2:], "points": int(val), **_bstats(g, base, cfg)})
    # yếu tố 0 điểm (vd. Spring/Test v2): so sánh theo có mặt / vắng mặt
    for col in sorted(c for c in sig.columns if c.startswith("h_")):
        if f"f_{col[2:]}" in sig.columns and sig[f"f_{col[2:]}"].fillna(0).nunique() > 1:
            continue
        for val, g in sig.groupby(sig[col].fillna(0)):
            rows.append({"factor": f"{col[2:]} (có mặt)", "points": int(val), **_bstats(g, base, cfg)})
    return pd.DataFrame(rows)


BREAKDOWN_SPECS: dict[str, list[tuple[str, list[float] | None]]] = {
    "Spring": [("spring_type", None), ("pen_atr", [0, 0.5, 1.0, np.inf]), ("pen_max_vol_ratio", [0, 0.5, 0.8, 1.0, 2.0, np.inf]),
               ("recovery_close_pos", [0, 0.7, 0.9, 1.01]), ("recovery_bars", [0, 1.5, 2.5, 3.5]),
               ("range_bars", [0, 40, 80, 160, np.inf]), ("range_height_atr", [0, 4, 5, 6.01]),
               ("range_context", None), ("market_trend", None), ("confidence_level", None), ("period", None)],
    "SOS": [("breakout_atr", [0, 0.5, 1.0, 2.0, np.inf]), ("ev_vol_ratio", [1.5, 2, 3, np.inf]),
            ("range_bars", [0, 40, 80, 160, np.inf]), ("range_context", None), ("market_trend", None),
            ("confidence_level", None), ("period", None)],
    "SC": [("sc_decline", [0, 0.2, 0.3, 0.4, 1.0]), ("ev_vol_ratio", [2, 3, 5, np.inf]), ("beta", [-np.inf, 0.8, 1.2, np.inf]),
           ("market_trend", None), ("period", None)],
}
BREAKDOWN_KINDS = {"Spring": ("Spring (volume thấp)", "Spring (shakeout)"), "SOS": ("SOS",), "SC": ("SC",)}


def _fmt_bin(iv: pd.Interval) -> str:
    lo = "-∞" if np.isneginf(iv.left) else f"{iv.left:g}"
    hi = "∞" if np.isinf(iv.right) else f"{iv.right:g}"
    return f"[{lo}, {hi})"


def breakdown(signals: pd.DataFrame, baseline: pd.DataFrame, cfg: BacktestConfig, family: str) -> pd.DataFrame:
    """Kết quả (đã điều chỉnh beta) theo từng thuộc tính của sự kiện / bối cảnh tại thời điểm tín hiệu."""
    sig = _tradable(signals)
    sig = sig[sig["kind"].isin(BREAKDOWN_KINDS[family])]
    base = baseline_beta(baseline, cfg.horizons)
    rows = []
    for attr, bins in BREAKDOWN_SPECS[family]:
        if attr not in sig or sig[attr].isna().all():
            continue
        if bins is None:
            keys = sig[attr].map(lambda v: SPRING_TYPE_LABEL.get(v, v) if isinstance(v, str) else v).fillna("không có").astype(str)
        else:
            keys = pd.cut(sig[attr].astype(float), bins=bins, right=False).map(lambda iv: _fmt_bin(iv) if isinstance(iv, pd.Interval) else "không có")
            keys = keys.astype(object).fillna("không có")
        for k, g in sig.groupby(keys, observed=True):
            rows.append({"attribute": attr, "bucket": str(k), **_bstats(g, base, cfg)})
    return pd.DataFrame(rows)


def diagnose(signals: pd.DataFrame, baseline: pd.DataFrame, cfg: BacktestConfig) -> dict[str, pd.DataFrame]:
    if "bexcess_20" not in signals:
        return {}
    out = {"by_kind_beta": by_kind_beta(signals, baseline, cfg), "by_kind_period": by_kind_period(signals, baseline, cfg)}
    if any(c.startswith("f_") for c in signals.columns):
        out["by_factor"] = by_factor(signals, baseline, cfg)
    for fam in BREAKDOWN_SPECS:
        out[f"breakdown_{fam.lower()}"] = breakdown(signals, baseline, cfg, fam)
    return out
