"""Event study point-in-time song song trên toàn bộ mã trong cache (không gọi mạng).

    python scripts/parallel_study.py --out output/h4_base
    python scripts/parallel_study.py --config config/h4b.yaml --out output/h4b --workers 10
"""
from __future__ import annotations

import argparse
import logging
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wyckoff.backtest.study import study_symbol  # noqa: E402
from wyckoff.config import load_config  # noqa: E402
from wyckoff.data.cache import load_cache  # noqa: E402

INDEX_SYMBOLS = {"VNINDEX", "VNSMALLCAP", "VNMIDCAP", "VN30", "HNXINDEX", "UPCOMINDEX", "VNSML", "VNMID"}
MIN_BARS = 300


def _one(job: tuple[str, str | None, str, str]) -> tuple[str, pd.DataFrame | None, str | None]:
    sym, config, cache_dir, start = job
    logging.disable(logging.WARNING)
    try:
        cfg = load_config(config)
        df = load_cache(Path(cache_dir) / f"{sym}_1D.csv")
        if df is None or len(df) < MIN_BARS:
            return sym, None, None
        index = load_cache(Path(cache_dir) / "VNINDEX_1D.csv")
        return sym, study_symbol(sym, df, cfg, index, "VNINDEX", start=start).signals, None
    except Exception as exc:  # noqa: BLE001 - một mã lỗi không dừng cả lần chạy
        return sym, None, str(exc)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Event study song song trên cache")
    p.add_argument("--config", default=None)
    p.add_argument("--cache-dir", default="cache")
    p.add_argument("--out", required=True)
    p.add_argument("--start", default="2018-01-01")
    p.add_argument("--workers", type=int, default=10)
    a = p.parse_args()

    syms = sorted(f.stem.replace("_1D", "") for f in Path(a.cache_dir).glob("*_1D.csv"))
    jobs = [(s, a.config, a.cache_dir, a.start) for s in syms if s not in INDEX_SYMBOLS]
    frames, errors = [], []
    with ProcessPoolExecutor(a.workers) as ex:
        for i, (sym, sig, err) in enumerate(ex.map(_one, jobs), 1):
            if err:
                errors.append(f"{sym}: {err}")
            elif sig is not None and not sig.empty:
                frames.append(sig)
            if i % 25 == 0:
                print(f"{i}/{len(jobs)}", flush=True)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    pd.concat(frames, ignore_index=True).to_csv(out / "signals.csv", index=False)
    print(f"Xong: {len(frames)} mã, lỗi {len(errors)} -> {out / 'signals.csv'}")
    for e in errors[:20]:
        print(" !", e)


if __name__ == "__main__":
    main()
