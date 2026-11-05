"""Chấm H8 theo tiêu chí chốt trước (docs/h8-preregistration.md).

    python scripts/h8_eval.py --cache-dir output/h8/cache --out output/h8
"""
from __future__ import annotations

import argparse
import logging
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wyckoff.backtest.metrics import forward_metrics, rolling_beta  # noqa: E402
from wyckoff.backtest.study import period_label  # noqa: E402
from wyckoff.config import Config  # noqa: E402
from wyckoff.data.cache import load_cache  # noqa: E402
from wyckoff.evidence import ACC, DIST, evidence, range_events  # noqa: E402
from wyckoff.market import align_index  # noqa: E402
from wyckoff.pipeline import analyze  # noqa: E402

INDEX_SYMBOLS = {"VNINDEX", "VNSMALLCAP", "VNMIDCAP", "VN30", "HNXINDEX", "UPCOMINDEX", "VNSML", "VNMID"}
MIN_BARS = 300
START = pd.Timestamp("2018-01-01")
RECENT, EARLY = "2023–nay", "2018–2022"
MODES = ("h8a", "h8b")
BOOT_N, BOOT_CI, BOOT_SEED = 2000, 0.90, 7
MIN_RANGES, EDGE_PP, MIN_LEAD = 300, 5.0, 10


def _one(job: tuple[str, str]) -> tuple[list[dict], list[dict]]:
    sym, cache_dir = job
    logging.disable(logging.WARNING)
    df = load_cache(Path(cache_dir) / f"{sym}_1D.csv")
    if df is None or len(df) < MIN_BARS:
        return [], []
    cfg = Config()
    bt = cfg.backtest
    res = analyze(df, cfg)
    al = align_index(df, load_cache(Path(cache_dir) / "VNINDEX_1D.csv"))
    beta = rolling_beta(df, al, bt.beta_window, bt.beta_min_periods)
    split = pd.Timestamp(bt.split_date)
    signals, ranges = [], []
    by_id = {r.range_id: r for r in res.ranges}
    for mode in MODES:
        for ev in evidence(res, mode):
            r = by_id[ev.range_id]
            if r.confirmed_date < START:
                continue
            final = ev.final_state
            first = ev.first_of(final) if final else None
            kinds = sorted({e.kind.value for e in range_events(res, r, mode)})
            ranges.append({
                "mode": mode, "symbol": sym, "range_id": ev.range_id, "exit": r.exit_direction, "final_state": final,
                "last_score": ev.scores[-1] if ev.scores else 0, "n_flips": len(ev.flips),
                "lead": None if first is None or r.end_confirmed_idx is None else r.end_confirmed_idx - first,
                "period": period_label(r.confirmed_date, START, split), "kinds": ",".join(kinds),
            })
            for t, side, score in ev.flips:
                b = beta.iloc[t]
                fm = forward_metrics(df, al, t, bt.horizons, bt.cost_pct, cfg.data.price_limit, cfg.data.limit_tolerance,
                                     beta=None if pd.isna(b) else float(b))
                signals.append({"mode": mode, "symbol": sym, "range_id": ev.range_id, "t": t, "side": side, "score": score,
                                "period": period_label(df.index[t], START, split), "signal_date": df.index[t],
                                "untradable": fm.get("untradable"), "bexcess_20": fm.get("bexcess_20", np.nan),
                                "bexcess_60": fm.get("bexcess_60", np.nan)})
    return signals, ranges


def spread_by_symbol(sig: pd.DataFrame, col: str = "bexcess_20") -> tuple[float, float, float]:
    """(chênh lệch, cận dưới, cận trên) TB(nghiêng tích lũy) - TB(nghiêng phân phối); bootstrap theo mã."""
    s = sig[sig[col].notna()]
    g = s.groupby(["symbol", "side"])[col].agg(["sum", "count"]).unstack(fill_value=0)
    syms = list(g.index)
    if not syms:
        return (np.nan, np.nan, np.nan)
    sm = g["sum"].reindex(columns=[ACC, DIST], fill_value=0).to_numpy(dtype=float)
    ct = g["count"].reindex(columns=[ACC, DIST], fill_value=0).to_numpy(dtype=float)
    with np.errstate(invalid="ignore", divide="ignore"):
        tot = sm.sum(0) / ct.sum(0)
    rng = np.random.default_rng(BOOT_SEED)
    out = np.empty(BOOT_N)
    for i in range(BOOT_N):
        k = rng.integers(0, len(syms), len(syms))
        a, c = sm[k].sum(0), ct[k].sum(0)
        with np.errstate(invalid="ignore", divide="ignore"):
            m = a / c
        out[i] = m[0] - m[1]
    out = out[~np.isnan(out)]
    q = (1 - BOOT_CI) / 2
    return float(tot[0] - tot[1]), float(np.quantile(out, q)), float(np.quantile(out, 1 - q))


def score_mode(mode: str, sig_all: pd.DataFrame, rng_all: pd.DataFrame) -> tuple[list[str], dict]:
    sig = sig_all[(sig_all["mode"] == mode) & (sig_all["untradable"] == False)]  # noqa: E712
    rg = rng_all[rng_all["mode"] == mode]
    closed = rg[rg["exit"].notna()]
    base_up = float((closed["exit"] == "up").mean() * 100)
    base_down = 100 - base_up
    a = closed[closed["final_state"] == ACC]
    d = closed[closed["final_state"] == DIST]
    rate_up = float((a["exit"] == "up").mean() * 100) if len(a) else np.nan
    rate_down = float((d["exit"] == "down").mean() * 100) if len(d) else np.nan
    leaning = closed[closed["final_state"].notna()]
    lead = float(leaning["lead"].median()) if len(leaning) else np.nan
    sp, lo, hi = spread_by_symbol(sig)
    early = spread_by_symbol(sig[sig["period"] == EARLY])
    recent = spread_by_symbol(sig[sig["period"] == RECENT])
    crit = {
        1: min(len(a), len(d)) >= MIN_RANGES,
        2: bool(rate_up >= base_up + EDGE_PP),
        3: bool(rate_down >= base_down + EDGE_PP),
        4: bool(lead >= MIN_LEAD),
        5: bool(sp > 0 and lo > 0),
        6: bool(early[0] > 0 and recent[0] > 0),
    }
    f = lambda x, n=2: "n/a" if x is None or np.isnan(x) else f"{x:+.{n}f}".replace(".", ",")  # noqa: E731
    p = lambda x: "n/a" if np.isnan(x) else f"{x:.1f}%".replace(".", ",")  # noqa: E731
    ok = lambda b: "ĐẠT" if b else "KHÔNG ĐẠT"  # noqa: E731
    acc_mean = sig.loc[sig["side"] == ACC, "bexcess_20"].mean()
    dist_mean = sig.loc[sig["side"] == DIST, "bexcess_20"].mean()
    out = [f"## {mode.upper()}: **{'CHẤP NHẬN' if all(crit.values()) else 'KHÔNG CHẤP NHẬN'}**", "",
           f"1. Đủ mẫu (≥ {MIN_RANGES} range mỗi chiều): tích lũy {len(a)}, phân phối {len(d)}: **{ok(crit[1])}**",
           f"2. Nghiêng tích lũy thoát lên {p(rate_up)} (nền {p(base_up)}, cần +{EDGE_PP:g} điểm %): **{ok(crit[2])}**",
           f"3. Nghiêng phân phối thoát xuống {p(rate_down)} (nền {p(base_down)}, cần +{EDGE_PP:g} điểm %): **{ok(crit[3])}**",
           f"4. Trung vị sớm {lead if not np.isnan(lead) else 'n/a'} phiên (cần ≥ {MIN_LEAD}): **{ok(crit[4])}**",
           f"5. bexcess 20 phiên: tích lũy {f(acc_mean)}, phân phối {f(dist_mean)}; chênh {f(sp)} [{f(lo)}; {f(hi)}]: **{ok(crit[5])}**",
           f"6. Chênh theo giai đoạn: {EARLY} {f(early[0])}, {RECENT} {f(recent[0])}: **{ok(crit[6])}**", ""]
    # Tham khảo
    bins = pd.cut(closed["last_score"], [-99, -3, -2, -1, 0, 1, 2, 99], labels=["≤-3", "-2", "-1", "0", "+1", "+2", "≥+3"])
    t = closed.groupby(bins, observed=True)["exit"].agg(n="count", thoat_len=lambda s: round((s == "up").mean() * 100, 1))
    s60 = sig.groupby("side")[["bexcess_20", "bexcess_60"]].mean().round(2)
    out += ["Tham khảo (không dùng để chấm):", "",
            f"- Range không bao giờ nghiêng: {(rg['n_flips'] == 0).mean() * 100:.1f}%; có đổi chiều nhiều lần (≥ 2 tín hiệu): {(rg['n_flips'] >= 2).mean() * 100:.1f}%; tín hiệu tradable: {len(sig)}.",
            "", "Điểm cuối × tỷ lệ thoát lên (%):", "```", t.to_string(), "```", "",
            "Lợi suất theo chiều:", "```", s60.to_string(), "```", ""]
    return out, crit


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--out", default="output/h8")
    ap.add_argument("--workers", type=int, default=10)
    a = ap.parse_args()
    syms = sorted(f.stem.replace("_1D", "") for f in Path(a.cache_dir).glob("*_1D.csv"))
    sig_rows, rng_rows = [], []
    with ProcessPoolExecutor(a.workers) as ex:
        for s, r in ex.map(_one, [(x, a.cache_dir) for x in syms if x not in INDEX_SYMBOLS], chunksize=4):
            sig_rows += s
            rng_rows += r
    sig, rng = pd.DataFrame(sig_rows), pd.DataFrame(rng_rows)
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    sig.to_csv(out_dir / "signals.csv", index=False)
    rng.to_csv(out_dir / "ranges.csv", index=False)
    lines = ["# Kết quả H8 – bằng chứng trong range", "",
             f"Mẫu: {rng['symbol'].nunique()} mã, {len(rng[rng['mode'] == 'h8a'])} range từ 2018. Dữ liệu đến {pd.to_datetime(sig['signal_date']).max():%d/%m/%Y}. "
             "Đơn vị: bexcess (%), CI 90%, bootstrap theo mã. Đăng ký trước: docs/h8-preregistration.md.", ""]
    for m in MODES:
        lines += score_mode(m, sig, rng)[0]
    text = "\n".join(lines)
    (out_dir / "report.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
