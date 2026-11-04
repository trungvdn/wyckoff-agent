"""Kiểm tra 2 giả thuyết đăng ký trước (Project: claude/oos-hypotheses-preregistration-2026-11-03.md).

    python scripts/hypothesis_eval.py --v2 output/h_v2 --v1 output/h_v1 --h1 output/h_h1 --h2 output/h_h2 \
        --exclude-from output/backtest_diag,output/oos_v2 --ref-index VNSMALLCAP --universe VNSmallCap --out output/hypothesis_report.md

Thước đo chấm: bexcess so với VNINDEX (cột có sẵn trong signals.csv).
Tham khảo: tính lại bexcess so với --ref-index (chỉ số cùng nhóm vốn hóa), đọc giá từ --cache-dir.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wyckoff.backtest.oos import (evaluate, evaluate_hypothesis, render_hypothesis, render_markdown,  # noqa: E402
                                  with_reference_index)
from wyckoff.config import load_config  # noqa: E402
from wyckoff.data.cache import load_cache  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Kiểm tra giả thuyết ngoài mẫu")
    for k in ("v2", "v1", "h1", "h2"):
        p.add_argument(f"--{k}", required=True, help=f"thư mục backtest {k}")
    p.add_argument("--exclude-from", default="", help="các thư mục backtest đã dùng, phân cách bằng dấu phẩy")
    p.add_argument("--ref-index", default=None, help="chỉ số tham khảo cùng nhóm vốn hóa (vd. VNSML)")
    p.add_argument("--cache-dir", default="cache")
    p.add_argument("--end", default=None, help="cắt dữ liệu giá đến ngày (khớp với lúc chạy backtest)")
    p.add_argument("--h1-min-bars", type=int, default=250,
                   help="GT1 chỉ so từ phiên thứ N của chỉ số bối cảnh (đủ SMA200 và beta); áp cho cả GT1 và v2")
    p.add_argument("--universe", default="")
    p.add_argument("--out", default="output/hypothesis_report.md")
    a = p.parse_args()

    sig = {k: pd.read_csv(Path(getattr(a, k)) / "signals.csv") for k in ("v2", "v1", "h1", "h2")}
    exclude: set[str] = set()
    for d in filter(None, a.exclude_from.split(",")):
        exclude |= set(pd.read_csv(Path(d) / "signals.csv", usecols=["symbol"])["symbol"].unique())
    syms = sorted(set(sig["v2"]["symbol"]) - exclude)

    rep = evaluate(sig["v2"], sig["v1"], 20, exclude)
    meta = {"universe": a.universe, "n_symbols": len(syms), "n_excluded": len(set(sig["v2"]["symbol"]) & exclude),
            "start": str(sig["v2"]["signal_date"].min())[:10], "end": str(sig["v2"]["signal_date"].max())[:10]}
    md = [render_markdown(rep, meta).replace("# Kiểm tra ngoài mẫu thang tin cậy v2",
                                              "# Lặp lại kiểm tra ngoài mẫu v2 so với v1"), "",
          "# Giả thuyết (thước đo chấm: so với VNINDEX)", ""]
    h1_from = None
    if a.ref_index:
        ref_df = load_cache(Path(a.cache_dir) / f"{a.ref_index}_1D.csv")
        if len(ref_df) >= a.h1_min_bars:
            h1_from = ref_df.index[a.h1_min_bars - 1]

    def since(df: pd.DataFrame) -> pd.DataFrame:
        if h1_from is None:
            return df
        d = pd.to_datetime(df["signal_date"])
        if d.dt.tz is not None:
            d = d.dt.tz_localize(None)          # giữ giờ địa phương, không đổi sang UTC
        cut = pd.Timestamp(h1_from)
        cut = cut.tz_localize(None) if cut.tzinfo is not None else cut
        return df[d.dt.normalize() >= cut.normalize()]

    note = f" (tín hiệu từ {pd.Timestamp(h1_from):%d/%m/%Y}, phiên thứ {a.h1_min_bars} của {a.ref_index})" if h1_from is not None else ""
    md.append(render_hypothesis(evaluate_hypothesis(since(sig["h1"]), since(sig["v2"]),
                                                    "GT1 – bối cảnh theo chỉ số cùng nhóm vốn hóa" + note, exclude=exclude)))
    md.append(render_hypothesis(evaluate_hypothesis(sig["h2"], sig["v2"], "GT2 – uptrend chỉ +1 khi RS > +3%", exclude=exclude)))

    if a.ref_index:
        cfg = load_config("config/default.yaml")
        ref = load_cache(Path(a.cache_dir) / f"{a.ref_index}_1D.csv")
        stocks = {}
        for s in syms:
            df = load_cache(Path(a.cache_dir) / f"{s}_1D.csv")
            stocks[s] = df.loc[:a.end] if a.end else df
        md += [f"# Tham khảo: thước đo so với {a.ref_index} (không dùng để chấm)", ""]
        rs = {k: with_reference_index(sig[k][sig[k]["symbol"].isin(syms)], stocks, ref, cfg) for k in sig}
        md.append(render_hypothesis(evaluate_hypothesis(since(rs["h1"]), since(rs["v2"]), f"GT1 (so với {a.ref_index})", exclude=exclude)))
        md.append(render_hypothesis(evaluate_hypothesis(rs["h2"], rs["v2"], f"GT2 (so với {a.ref_index})", exclude=exclude)))
    text = "\n".join(md)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
