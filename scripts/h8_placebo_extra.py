"""Bổ sung điều tra H8 (docs/h8-investigation.md), chạy sau scripts/h8_investigate.py: close <= 0 trong cache; tỷ lệ quay lại range và độ dài range trên placebo; hồi quy trên placebo."""
import sys
import warnings
import zlib
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))
warnings.filterwarnings("ignore")

from h8_investigate import INDEX_SYMBOLS, boot_lpm, range_rows, shuffle_days  # noqa: E402
from wyckoff.config import Config  # noqa: E402
from wyckoff.data.cache import load_cache  # noqa: E402
from wyckoff.detectors.models import EventType  # noqa: E402
from wyckoff.pipeline import analyze  # noqa: E402

CACHE = REPO / "output" / "h8" / "cache"
START = pd.Timestamp("2018-01-01")


def one(sym: str):
    df = load_cache(CACHE / f"{sym}_1D.csv")
    if df is None or len(df) < 300:
        return [], [], int((df["close"] <= 0).sum()) if df is not None else 0
    zeros = int((df["close"] <= 0).sum())
    res = analyze(shuffle_days(df, 11 + zlib.crc32(sym.encode()) % 100_000), Config())
    d = res.df
    close = d["close"].to_numpy(dtype=float)
    atr = d["atr"].to_numpy(dtype=float)
    rows = []
    for r in res.ranges:
        if r.confirmed_date < START or r.end_confirmed_idx is None or r.height <= 0:
            continue
        evs = [e for e in res.events if e.range_id == r.range_id and e.kind in (EventType.SPRING, EventType.UTAD, EventType.UT)]
        for t in range(r.confirmed_idx, r.end_confirmed_idx, 5):
            if d.index[t] < START or t < 20 or atr[t] <= 0:
                continue
            rows.append({"symbol": sym, "exit": r.exit_direction, "pos": (close[t] - r.support) / r.height,
                         "drift20": (close[t] - close[t - 20]) / atr[t],
                         "s": float(any(e.kind == EventType.SPRING and e.confirmed_idx <= t for e in evs)),
                         "u": float(any(e.kind != EventType.SPRING and e.confirmed_idx <= t for e in evs))})
    return range_rows(res, sym), rows, zeros


if __name__ == "__main__":
    syms = [p.stem.replace("_1D", "") for p in sorted(CACHE.glob("*_1D.csv"))]
    syms = [s for s in syms if s not in INDEX_SYMBOLS]
    rg, pn, z = [], [], {}
    with ProcessPoolExecutor(8) as ex:
        for s, (a, b, n) in zip(syms, ex.map(one, syms, chunksize=4)):
            rg += a
            pn += b
            if n:
                z[s] = n
    print("mã có close <= 0:", z)
    r = pd.DataFrame(rg)
    real = pd.read_csv(REPO / "output" / "h8" / "investigate" / "ranges.csv")
    for name, x in (("thật", real), ("placebo", r)):
        print(name, "n", len(x), "quay lại 30 phiên %", round(x["back_in_30"].mean() * 100, 1),
              "độ dài TV", x["bars"].median(), "chiều cao ATR TV", round(x["height_atr"].median(), 2))
        print(" theo hướng", x.groupby("exit")["back_in_30"].mean().mul(100).round(1).to_dict())
    p = pd.DataFrame(pn)
    pos = pd.cut(p.pos, [-np.inf, 0, .2, .4, .6, .8, 1, np.inf])
    print(p.groupby(pos, observed=True)["exit"].agg(n="size", len=lambda s: round((s == "up").mean() * 100, 1)).to_string())
    print(boot_lpm(p, ["s", "u"]).to_string())
    print(boot_lpm(p.assign(pos_clip=p.pos.clip(-.5, 1.5)), ["s", "u", "pos_clip", "drift20"]).to_string())
