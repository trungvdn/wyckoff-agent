"""Kiểm tra thang tin cậy ngoài mẫu (out-of-sample) theo tiêu chí chốt trước.

Tiêu chí (chốt 03/11/2026, trước khi xem dữ liệu ngoài mẫu), đo trên lợi suất vượt chỉ số điều chỉnh beta
`bexcess_20` của mọi tín hiệu khớp được có mức tin cậy thấp / trung bình / cao:

    1. Tăng đều: TB(thấp) < TB(trung bình) < TB(cao).
    2. Mức "cao" có CI 90% bootstrap > 0 (cận dưới > 0).
    3. Chênh lệch cao − thấp của v2 lớn hơn của v1 trên cùng dữ liệu.

60 phiên và tách giai đoạn chỉ để tham khảo, không dùng để kết luận đạt / không đạt.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from wyckoff.backtest.metrics import bootstrap_mean_ci

LEVELS = ("thấp", "trung bình", "cao")


@dataclass
class LevelStats:
    level: str
    n: int
    mean: float
    ci_lo: float
    ci_hi: float


@dataclass
class ScaleResult:
    name: str
    horizon: int
    levels: list[LevelStats]
    spread: float                      # cao - thấp
    spread_ci: tuple[float, float]     # CI bootstrap của chênh lệch (lấy mẫu độc lập từng nhóm)

    def by_level(self) -> dict[str, LevelStats]:
        return {s.level: s for s in self.levels}


@dataclass
class OOSVerdict:
    horizon: int
    v2: ScaleResult
    v1: ScaleResult
    monotonic: bool
    high_ci_positive: bool
    beats_v1: bool
    passed: bool
    reference: dict[str, Any] = field(default_factory=dict)


def _clean(signals: pd.DataFrame, exclude: set[str] | None) -> pd.DataFrame:
    s = signals[signals["untradable"] == False]  # noqa: E712
    if exclude:
        s = s[~s["symbol"].isin(exclude)]
    return s[s["confidence_level"].isin(LEVELS)]


def spread_ci(lo: np.ndarray, hi: np.ndarray, n: int = 2000, ci: float = 0.90, seed: int = 7) -> tuple[float, float]:
    """CI bootstrap của TB(hi) - TB(lo), lấy mẫu lại độc lập trong từng nhóm."""
    lo, hi = lo[~np.isnan(lo)], hi[~np.isnan(hi)]
    if len(lo) < 2 or len(hi) < 2:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    d = rng.choice(hi, (n, len(hi))).mean(axis=1) - rng.choice(lo, (n, len(lo))).mean(axis=1)
    a = (1 - ci) / 2
    return (float(np.quantile(d, a)), float(np.quantile(d, 1 - a)))


def scale_stats(signals: pd.DataFrame, name: str, horizon: int = 20, exclude: set[str] | None = None,
                n_boot: int = 2000, ci: float = 0.90, seed: int = 7) -> ScaleResult:
    s = _clean(signals, exclude)
    col = f"bexcess_{horizon}"
    levels = []
    for lv in LEVELS:
        v = s.loc[s["confidence_level"] == lv, col].to_numpy(dtype=float)
        v = v[~np.isnan(v)]
        lo, hi = bootstrap_mean_ci(v, n_boot, ci, seed)
        levels.append(LevelStats(lv, len(v), float(v.mean()) if len(v) else np.nan, lo, hi))
    a = s.loc[s["confidence_level"] == "thấp", col].to_numpy(dtype=float)
    b = s.loc[s["confidence_level"] == "cao", col].to_numpy(dtype=float)
    return ScaleResult(name, horizon, levels, levels[2].mean - levels[0].mean, spread_ci(a, b, n_boot, ci, seed))


def evaluate(sig_v2: pd.DataFrame, sig_v1: pd.DataFrame, horizon: int = 20, exclude: set[str] | None = None,
             split_col: str = "period", n_boot: int = 2000, ci: float = 0.90, seed: int = 7) -> OOSVerdict:
    v2 = scale_stats(sig_v2, "v2", horizon, exclude, n_boot, ci, seed)
    v1 = scale_stats(sig_v1, "v1", horizon, exclude, n_boot, ci, seed)
    m = [x.mean for x in v2.levels]
    monotonic = bool(not np.isnan(m).any() and m[0] < m[1] < m[2])
    high_pos = bool(v2.levels[2].ci_lo > 0)
    beats = bool(v2.spread > v1.spread)
    ref: dict[str, Any] = {"h60": {"v2": scale_stats(sig_v2, "v2", 60, exclude, n_boot, ci, seed),
                                   "v1": scale_stats(sig_v1, "v1", 60, exclude, n_boot, ci, seed)}}
    if split_col in sig_v2.columns:
        ref["periods"] = {
            str(p): {"v2": scale_stats(sig_v2[sig_v2[split_col] == p], "v2", horizon, exclude, n_boot, ci, seed),
                     "v1": scale_stats(sig_v1[sig_v1[split_col] == p], "v1", horizon, exclude, n_boot, ci, seed)}
            for p in sorted(sig_v2[split_col].dropna().unique())
        }
    return OOSVerdict(horizon, v2, v1, monotonic, high_pos, beats, monotonic and high_pos and beats, ref)


def _fmt(x: float) -> str:
    return "n/a" if x is None or np.isnan(x) else f"{x:+.2f}".replace(".", ",")


def _table(r1: ScaleResult, r2: ScaleResult) -> list[str]:
    rows = ["| Mức | v1 | v2 |", "|---|---|---|"]
    a, b = r1.by_level(), r2.by_level()
    for lv in LEVELS:
        cell = lambda s: f"{_fmt(s.mean)} [{_fmt(s.ci_lo)}; {_fmt(s.ci_hi)}] (n={s.n})"  # noqa: E731
        rows.append(f"| {lv} | {cell(a[lv])} | {cell(b[lv])} |")
    rows.append(f"| cao − thấp | {_fmt(r1.spread)} [{_fmt(r1.spread_ci[0])}; {_fmt(r1.spread_ci[1])}] "
                f"| {_fmt(r2.spread)} [{_fmt(r2.spread_ci[0])}; {_fmt(r2.spread_ci[1])}] |")
    return rows


def render_markdown(v: OOSVerdict, meta: dict[str, Any]) -> str:
    ok = lambda b: "ĐẠT" if b else "KHÔNG ĐẠT"  # noqa: E731
    out = [f"# Kiểm tra ngoài mẫu thang tin cậy v2 – {meta.get('universe', '')}", "",
           "Công cụ hỗ trợ phân tích, **không phải lời khuyên đầu tư**.", "",
           f"Mẫu: {meta.get('n_symbols', '?')} mã, {meta.get('start', '')} → {meta.get('end', '')}; "
           f"loại {meta.get('n_excluded', 0)} mã trùng các mẫu đã dùng. Đơn vị: lợi suất vượt chỉ số điều chỉnh beta (%), CI 90%.", "",
           f"## Kết luận theo tiêu chí chốt trước ({v.horizon} phiên): **{ok(v.passed)}**", "",
           f"1. Tăng đều thấp < trung bình < cao: **{ok(v.monotonic)}**",
           f"2. Mức cao có CI > 0: **{ok(v.high_ci_positive)}**",
           f"3. Chênh lệch cao − thấp v2 > v1 ({_fmt(v.v2.spread)} so với {_fmt(v.v1.spread)}): **{ok(v.beats_v1)}**", "",
           f"## {v.horizon} phiên", "", *_table(v.v1, v.v2), "",
           "## Tham khảo: 60 phiên", "", *_table(v.reference["h60"]["v1"], v.reference["h60"]["v2"]), ""]
    for p, d in v.reference.get("periods", {}).items():
        out += [f"## Tham khảo: giai đoạn {p} ({v.horizon} phiên)", "", *_table(d["v1"], d["v2"]), ""]
    out += ["## Hạn chế", "",
            f"Danh sách {meta.get('universe') or 'rổ'} hiện tại (thiên lệch sống sót); tín hiệu chồng lấn giữa các mã và trong cùng cấu trúc → CI lạc quan; "
            "các ngưỡng phát hiện sự kiện vẫn là ngưỡng đã xem trên VN30.", ""]
    return "\n".join(out)


# ---------------------------------------------------------------- giả thuyết so với v2

def cluster_spreads(signals: list[pd.DataFrame], horizon: int = 20, period: str | None = None,
                    n: int = 2000, seed: int = 7, exclude: set[str] | None = None) -> np.ndarray:
    """Bootstrap theo mã, **ghép cặp**: mỗi lần lấy mẫu lại cùng một tập mã cho mọi bộ tín hiệu.
    Trả về mảng (n, len(signals)) chênh lệch TB(cao) - TB(thấp)."""
    col = f"bexcess_{horizon}"
    cleaned = [_clean(s, exclude) for s in signals]
    if period is not None:
        cleaned = [s[s["period"] == period] for s in cleaned]
    syms = sorted(set().union(*[set(s["symbol"]) for s in cleaned]))
    if not syms:
        return np.full((n, len(signals)), np.nan)
    mats = []
    for s in cleaned:
        g = s.groupby(["symbol", "confidence_level"])[col].agg(["sum", "count"]).unstack(fill_value=0)
        sm = g["sum"].reindex(index=syms, columns=list(LEVELS), fill_value=0).to_numpy(dtype=float)
        ct = g["count"].reindex(index=syms, columns=list(LEVELS), fill_value=0).to_numpy(dtype=float)
        mats.append((np.nan_to_num(sm), ct))
    rng = np.random.default_rng(seed)
    out = np.empty((n, len(signals)))
    for i in range(n):
        k = rng.integers(0, len(syms), len(syms))
        for j, (sm, ct) in enumerate(mats):
            a, c = sm[k].sum(0), ct[k].sum(0)
            with np.errstate(invalid="ignore", divide="ignore"):
                m = a / c
            out[i, j] = m[2] - m[0]
    return out


@dataclass
class HypothesisVerdict:
    name: str
    h: ScaleResult
    v2: ScaleResult
    monotonic: bool              # a1
    high_ci_positive: bool       # a2
    beats_v2: bool               # b: chênh lệch 20 phiên toàn kỳ > v2
    recent_high60_better: bool   # c: 2023–nay, TB 60 phiên của mức cao > v2
    p_cluster: float             # d: P(chênh lệch GT > v2), bootstrap theo mã ghép cặp
    accepted: bool
    recent_high60: tuple[float, float] = (np.nan, np.nan)   # (GT, v2)


def evaluate_hypothesis(sig_h: pd.DataFrame, sig_v2: pd.DataFrame, name: str, horizon: int = 20,
                        recent_period: str = "2023–nay", p_min: float = 0.80, exclude: set[str] | None = None,
                        n_boot: int = 2000, ci: float = 0.90, seed: int = 7) -> HypothesisVerdict:
    """Tiêu chí chấp nhận giả thuyết (chốt trước): a1 tăng đều, a2 mức cao CI > 0, b chênh lệch > v2,
    c giai đoạn gần nhất: TB 60 phiên của mức cao > v2, d P_theo_mã(chênh lệch > v2) >= p_min. Cần cả 5."""
    h = scale_stats(sig_h, name, horizon, exclude, n_boot, ci, seed)
    v2 = scale_stats(sig_v2, "v2", horizon, exclude, n_boot, ci, seed)
    m = [x.mean for x in h.levels]
    mono = bool(not np.isnan(m).any() and m[0] < m[1] < m[2])
    hi_pos = bool(h.levels[2].ci_lo > 0)
    beats = bool(h.spread > v2.spread)
    rh = scale_stats(sig_h[sig_h["period"] == recent_period], name, 60, exclude, n_boot, ci, seed).levels[2].mean
    rv = scale_stats(sig_v2[sig_v2["period"] == recent_period], "v2", 60, exclude, n_boot, ci, seed).levels[2].mean
    recent = bool(not np.isnan(rh) and not np.isnan(rv) and rh > rv)
    cs = cluster_spreads([sig_h, sig_v2], horizon, None, n_boot, seed, exclude)
    ok = ~np.isnan(cs).any(axis=1)
    p = float(np.mean(cs[ok, 0] > cs[ok, 1])) if ok.any() else np.nan
    acc = mono and hi_pos and beats and recent and (p >= p_min)
    return HypothesisVerdict(name, h, v2, mono, hi_pos, beats, recent, p, acc, (rh, rv))


def render_hypothesis(v: HypothesisVerdict, p_min: float = 0.80) -> str:
    ok = lambda b: "ĐẠT" if b else "KHÔNG ĐẠT"  # noqa: E731
    out = [f"## {v.name}: **{'CHẤP NHẬN' if v.accepted else 'KHÔNG CHẤP NHẬN'}**", "",
           f"- a1. Tăng đều thấp < trung bình < cao (20 phiên): **{ok(v.monotonic)}**",
           f"- a2. Mức cao có CI > 0: **{ok(v.high_ci_positive)}**",
           f"- b. Chênh lệch cao − thấp > v2 ({_fmt(v.h.spread)} so với {_fmt(v.v2.spread)}): **{ok(v.beats_v2)}**",
           f"- c. 2023–nay, mức cao 60 phiên > v2 ({_fmt(v.recent_high60[0])} so với {_fmt(v.recent_high60[1])}): "
           f"**{ok(v.recent_high60_better)}**",
           f"- d. Bootstrap theo mã: P(chênh lệch > v2) = {v.p_cluster:.2f} (cần ≥ {p_min:.2f}): **{ok(v.p_cluster >= p_min)}**", "",
           *_table(v.v2, v.h), ""]
    return "\n".join(out).replace("| Mức | v1 | v2 |", f"| Mức | v2 | {v.name} |", 1)


def with_reference_index(signals: pd.DataFrame, stocks: dict[str, pd.DataFrame], ref_index: pd.DataFrame,
                         cfg: Any) -> pd.DataFrame:
    """Thước đo tham khảo: tính lại `bexcess_H` so với chỉ số khác (vd. VNSML), beta point-in-time so với chính
    chỉ số đó. Giữ nguyên mọi cột khác (mức tin cậy, pha...). `cfg`: Config."""
    from wyckoff.backtest.metrics import forward_metrics, rolling_beta
    from wyckoff.market import align_index

    bt = cfg.backtest
    out = signals.copy()
    for sym, g in signals.groupby("symbol"):
        df = stocks.get(sym)
        if df is None:
            out.loc[g.index, [f"bexcess_{h}" for h in bt.horizons]] = np.nan
            continue
        al = align_index(df, ref_index)
        beta = rolling_beta(df, al, bt.beta_window, bt.beta_min_periods)
        for i, t in zip(g.index, g["t"].astype(int)):
            b = beta.iloc[t]
            fm = forward_metrics(df, al, t, bt.horizons, bt.cost_pct, cfg.data.price_limit, cfg.data.limit_tolerance,
                                 beta=None if pd.isna(b) else float(b))
            for h in bt.horizons:
                out.at[i, f"bexcess_{h}"] = fm[f"bexcess_{h}"]
    return out
