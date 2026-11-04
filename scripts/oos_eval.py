"""Đánh giá ngoài mẫu thang tin cậy v2 so với v1 theo tiêu chí chốt trước (wyckoff/backtest/oos.py).

    python scripts/oos_eval.py --v2 output/oos_v2 --v1 output/oos_v1 --exclude-from output/backtest_diag \
        --universe VNMidCap --out output/oos_report.md

--exclude-from: thư mục backtest của mẫu chỉnh (đọc danh sách mã trong signals.csv) để loại mã trùng.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wyckoff.backtest.oos import evaluate, render_markdown  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Kiểm tra ngoài mẫu thang tin cậy")
    p.add_argument("--v2", required=True, help="thư mục backtest chạy với quy tắc v2")
    p.add_argument("--v1", required=True, help="thư mục backtest chạy với config/v1.yaml")
    p.add_argument("--exclude-from", default=None, help="thư mục backtest của mẫu chỉnh (loại các mã này)")
    p.add_argument("--universe", default="")
    p.add_argument("--horizon", type=int, default=20)
    p.add_argument("--out", default="output/oos_report.md")
    a = p.parse_args()

    s2 = pd.read_csv(Path(a.v2) / "signals.csv")
    s1 = pd.read_csv(Path(a.v1) / "signals.csv")
    exclude: set[str] = set()
    if a.exclude_from:
        exclude = set(pd.read_csv(Path(a.exclude_from) / "signals.csv", usecols=["symbol"])["symbol"].unique())
    syms = sorted(set(s2["symbol"]) - exclude)
    v = evaluate(s2, s1, a.horizon, exclude)
    meta = {"universe": a.universe, "n_symbols": len(syms), "n_excluded": len(set(s2["symbol"]) & exclude),
            "start": str(s2["signal_date"].min())[:10], "end": str(s2["signal_date"].max())[:10]}
    md = render_markdown(v, meta)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
