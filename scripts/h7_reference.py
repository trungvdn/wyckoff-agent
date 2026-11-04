"""Bảng tham khảo của H7 (không dùng để chấm, docs/h7-preregistration.md): lợi suất theo loại cấu trúc, tại phiên chốt nhãn,
theo mức sức mạnh cung cầu và từng tín hiệu. Nhãn lấy như biết tại từng phiên.

    python scripts/h7_reference.py --cache-dir output/h7/cache --out output/h7/reference.csv
"""
from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wyckoff.backtest.metrics import baseline_returns, rolling_beta  # noqa: E402
from wyckoff.backtest.study import period_label  # noqa: E402
from wyckoff.config import Config  # noqa: E402
from wyckoff.data.cache import load_cache  # noqa: E402
from wyckoff.market import align_index  # noqa: E402
from wyckoff.pipeline import analyze  # noqa: E402
from wyckoff.stages import TRANSITION  # noqa: E402
from wyckoff.strength import trend_strength  # noqa: E402

INDEX_SYMBOLS = {"VNINDEX", "VNSMALLCAP", "VNMIDCAP", "VN30", "HNXINDEX", "UPCOMINDEX", "VNSML", "VNMID"}
MIN_BARS = 300
HORIZONS = (20, 60)
START = pd.Timestamp("2018-01-01")


def _one(job: tuple[str, str]) -> dict | None:
    sym, cache_dir = job
    logging.disable(logging.WARNING)
    df = load_cache(Path(cache_dir) / f"{sym}_1D.csv")
    if df is None or len(df) < MIN_BARS:
        return None
    cfg = Config()
    bt = cfg.backtest
    res = analyze(df, cfg)
    al = align_index(df, load_cache(Path(cache_dir) / "VNINDEX_1D.csv"))
    beta = rolling_beta(df, al, bt.beta_window, bt.beta_min_periods)
    first = max(int(np.searchsorted(df.index.values, START.to_datetime64())), bt.min_history_bars)
    base = baseline_returns(df, al, bt.horizons, bt.cost_pct, first_signal_idx=first, beta=beta)
    split = pd.Timestamp(bt.split_date)
    agg: dict[tuple, list] = defaultdict(lambda: [0.0, 0, 0.0, 0])   # (nhóm, nhãn, giai đoạn) -> tổng, số mẫu theo 20 / 60 phiên

    def add(group: str, label: str, t: int) -> None:
        d = df.index[t]
        if d not in base.index or t < first:
            return
        v20, v60 = base.at[d, "bexcess_20"], base.at[d, "bexcess_60"]
        for key in ((group, label, "toàn kỳ"), (group, label, period_label(d, START, split))):
            a = agg[key]
            if not np.isnan(v20):
                a[0] += v20
                a[1] += 1
            if not np.isnan(v60):
                a[2] += v60
                a[3] += 1

    s = res.stages.series
    types = s["structure_type"].to_numpy()
    in_range = s["range_id"].notna().to_numpy()
    stage = s["stage"].to_numpy()
    segs = res.stages.segments
    seg_i = 0
    for t in range(first, len(df)):
        add("nền", "mọi phiên", t)
        lab = types[t]
        if lab == TRANSITION:
            lab = f"{TRANSITION} ({'trong range' if in_range[t] else 'ngoài range'})"
        add("loại cấu trúc", lab, t)
        if stage[t] in ("Markup", "Markdown"):
            while segs[seg_i].end_idx < t:
                seg_i += 1
            ts = trend_strength(res.df.iloc[:t + 1], res.swings, segs[seg_i].start_idx,
                                "up" if stage[t] == "Markup" else "down", cfg.strength, cfg.indicators.sma_period)
            add("mức sức mạnh", f"{stage[t]} · {ts.level}", t)
            for sig in ts.signals:
                add("tín hiệu", f"{stage[t]} · {sig.key} {sig.points:+d}", t)
    for r in res.stages.ranges:
        if r.resolved_idx is not None:
            add("phiên chốt nhãn", r.structure_type or f"{r.stage} (chưa rõ loại)", r.resolved_idx)
    return dict(agg)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("--cache-dir", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--workers", type=int, default=10)
    a = p.parse_args()
    syms = sorted(f.stem.replace("_1D", "") for f in Path(a.cache_dir).glob("*_1D.csv"))
    jobs = [(s, a.cache_dir) for s in syms if s not in INDEX_SYMBOLS]
    tot: dict[tuple, list] = defaultdict(lambda: [0.0, 0, 0.0, 0])
    n_sym: dict[tuple, int] = defaultdict(int)
    with ProcessPoolExecutor(a.workers) as ex:
        for res in ex.map(_one, jobs, chunksize=4):
            for k, v in (res or {}).items():
                t = tot[k]
                for i in range(4):
                    t[i] += v[i]
                n_sym[k] += 1
    rows = []
    for (group, label, period), (s20, n20, s60, n60) in tot.items():
        rows.append({"nhóm": group, "nhãn": label, "giai đoạn": period, "n": n20, "mã": n_sym[(group, label, period)],
                     "bexcess_20": s20 / n20 if n20 else np.nan, "bexcess_60": s60 / n60 if n60 else np.nan})
    out = pd.DataFrame(rows)
    for h in HORIZONS:
        col = f"bexcess_{h}"
        nen = out[out["nhãn"] == "mọi phiên"].set_index("giai đoạn")[col]
        out[f"chênh_{h}"] = out[col] - out["giai đoạn"].map(nen)
    out = out.sort_values(["nhóm", "nhãn", "giai đoạn"]).round(2)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(a.out, index=False)
    print(f"Xong -> {a.out} ({len(out)} dòng)")


if __name__ == "__main__":
    main()
