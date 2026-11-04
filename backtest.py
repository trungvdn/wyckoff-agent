"""Event study cho detector Wyckoff trên một rổ mã.

    python backtest.py                              # VN30 hiện tại, từ 2018-01-01
    python backtest.py --symbols HPG,FPT,VNM        # danh sách tự chọn
    python backtest.py --no-pit                     # bỏ tính lại pha/tin cậy theo ngày (nhanh hơn)
    python backtest.py --demo                       # dữ liệu tổng hợp, không cần mạng
    python backtest.py --group VNMidCap --fetch-only   # chỉ tải dữ liệu vào cache (kiểm tra ngoài mẫu)
    python backtest.py --group VNMidCap --config config/v1.yaml --out-dir output/oos_v1
    python backtest.py --group VNSmallCap --config config/h1.yaml --fetch-only   # tải thêm chỉ số bối cảnh VNSMALLCAP

Đầu ra (output/backtest/): signals.csv, baseline_summary.csv, by_kind.csv, by_confidence.csv,
by_score.csv, scenarios.csv, backtest_report.html.
"""
from __future__ import annotations

import argparse
import logging
import time
from dataclasses import replace
from pathlib import Path

import pandas as pd

from wyckoff.backtest.report import render_backtest_html
from wyckoff.backtest.study import study_symbol
from wyckoff.backtest.summary import summarize
from wyckoff.config import load_config
from wyckoff.data.fetcher import vnstock_index_source
from wyckoff.data.fetcher import QuotaExhaustedError
from wyckoff.data.loader import get_ohlcv, warmup_start, with_rate_limit_retry
from wyckoff.market import benchmark_for, context_benchmark_for


def main() -> None:
    p = argparse.ArgumentParser(description="Event study Wyckoff")
    p.add_argument("--group", default=None, help="nhóm vnstock (mặc định backtest.universe, VN30)")
    p.add_argument("--symbols", default=None, help="danh sách mã, phân cách bằng dấu phẩy")
    p.add_argument("--start", default=None)
    p.add_argument("--end", default=None)
    p.add_argument("--config", default=None)
    p.add_argument("--cache-dir", default="cache")
    p.add_argument("--out-dir", default="output/backtest")
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--no-pit", action="store_true", help="không tính lại pha/tin cậy point-in-time")
    p.add_argument("--demo", action="store_true", help="dữ liệu tổng hợp")
    p.add_argument("--fetch-only", action="store_true", help="chỉ tải dữ liệu vào cache rồi dừng")
    args = p.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    cfg = load_config(args.config)
    if args.no_pit:
        cfg = replace(cfg, backtest=replace(cfg.backtest, point_in_time=False))
    bt = cfg.backtest
    start = args.start or bt.start
    group = args.group or bt.universe
    warnings: list[str] = []

    if args.demo:
        from wyckoff.synthetic import make_market_index, make_wyckoff_accumulation

        stock = make_wyckoff_accumulation("2017-06-01")
        datasets = {"DEMO": stock}
        index = make_market_index(stock.index)
        bench, start, group = "VNINDEX", "2017-06-01", "DEMO"
        ctx_index, ctx_bench = index, bench
        symbols = ["DEMO"]
        cfg = replace(cfg, backtest=replace(cfg.backtest, min_history_bars=60))   # chuỗi demo chỉ ~212 phiên
        bt = cfg.backtest
    else:
        if args.symbols:
            symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
            group = "tự chọn"
        else:
            from wyckoff.backtest.universe import symbols_by_group

            symbols = symbols_by_group(group)
        bench = benchmark_for(cfg.data.exchange, cfg.market)
        fetch_from = warmup_start(start, max(bt.min_history_bars, cfg.market.sma_slow))
        idx_src = vnstock_index_source(cfg.market.index_source, cfg.data.chunk_days, cfg.data.coverage_tolerance_days)

        def waiting(n: int, wait: float, exc: Exception) -> None:
            print(f"    hết hạn mức lượt gọi theo phút -> chờ {wait:.0f}s rồi thử lại (lần {n}/{bt.rate_limit_retries})")

        def fetch(sym: str, **kw):
            return with_rate_limit_retry(
                lambda: get_ohlcv(sym, fetch_from, args.end, cache_dir=args.cache_dir, cfg=cfg.data, refresh=args.refresh, **kw),
                retries=bt.rate_limit_retries, wait_s=bt.rate_limit_wait_s, on_wait=waiting)

        index = fetch(bench, source_fn=idx_src, check_limits=False)
        ctx_bench = context_benchmark_for(cfg.data.exchange, cfg.market)
        ctx_index = index if ctx_bench == bench else fetch(ctx_bench, source_fn=idx_src, check_limits=False)
        print(f"Chỉ số đo lợi suất vượt: {bench} ({len(index)} phiên); chỉ số bối cảnh: {ctx_bench} ({len(ctx_index)} phiên)")
        datasets = {}
        for i, sym in enumerate(symbols, 1):
            try:
                datasets[sym] = fetch(sym)
                print(f"[{i}/{len(symbols)}] tải {sym}: {len(datasets[sym])} phiên")
            except QuotaExhaustedError as exc:
                warnings.append(f"Dừng tải từ {sym}: hết hạn mức ngày/tháng của vnstock ({exc}). Các mã còn lại bị bỏ qua.")
                print(f"[{i}/{len(symbols)}] HẾT HẠN MỨC NGÀY/THÁNG – dừng tải. {exc}")
                break
            except Exception as exc:  # noqa: BLE001 - bỏ qua mã lỗi, ghi lại
                warnings.append(f"Bỏ qua {sym}: {str(exc)[:300]}")
                print(f"[{i}/{len(symbols)}] LỖI {sym}: {str(exc)[:300]}")

    if args.fetch_only:
        print(f"\nĐã tải {len(datasets)}/{len(symbols)} mã ({group}) vào {args.cache_dir}/")
        for w in warnings:
            print("  !", w)
        return

    signals, baselines = [], []
    t0 = time.time()
    for i, (sym, df) in enumerate(datasets.items(), 1):
        t = time.time()
        try:
            st = study_symbol(sym, df, cfg, index, bench, start=start, context_index=ctx_index, context_benchmark=ctx_bench)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Lỗi phân tích {sym}: {exc}")
            print(f"  ! {sym}: {exc}")
            continue
        signals.append(st.signals)
        baselines.append(st.baseline)
        print(f"  phân tích {sym}: {len(st.signals)} tín hiệu ({time.time() - t:.1f}s) [{i}/{len(datasets)}]")
    if not signals:
        raise SystemExit("Không có mã nào phân tích được")
    sig = pd.concat(signals, ignore_index=True)
    base = pd.concat(baselines)
    summary = summarize(sig, base, bt)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    sig.to_csv(out / "signals.csv", index=False)
    for name, df in summary.items():
        df.to_csv(out / f"{name}.csv", index=False)
    end = args.end or f"{max(d.index[-1] for d in datasets.values()):%Y-%m-%d}"
    meta = {"universe": group, "symbols": list(datasets), "start": start, "end": end, "n_signals": len(sig),
            "warnings": warnings}
    (out / "backtest_report.html").write_text(render_backtest_html(summary, meta, bt), encoding="utf-8")

    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 20)
    H = 20 if 20 in bt.horizons else max(bt.horizons)
    print(f"\nXong {len(datasets)} mã, {len(sig)} tín hiệu trong {time.time() - t0:.0f}s")
    print("\nNền:\n", summary["baseline"].round(2).to_string(index=False))
    bk = summary["by_kind"]
    print(f"\nTheo loại tín hiệu ({H} phiên):\n",
          bk[bk["horizon"] == H][["kind", "n", "mean_excess", "win_rate", "edge_vs_base", "edge_ci_lo", "edge_ci_hi"]]
          .round(2).to_string(index=False))
    if not summary["by_confidence"].empty:
        bc = summary["by_confidence"]
        print(f"\nTheo mức tin cậy ({H} phiên):\n",
              bc[bc["horizon"] == H][["confidence_level", "n", "mean_excess", "win_rate", "edge_vs_base"]].round(2).to_string(index=False))
    if "by_kind_beta" in summary:
        print("\nĐiều chỉnh beta (chênh so với nền, 20 / 60 phiên):\n",
              summary["by_kind_beta"][["kind", "n", "edge_b20", "edge_b20_lo", "edge_b20_hi", "edge_b60", "edge_b60_lo", "edge_b60_hi"]]
              .round(2).to_string(index=False))
    print(f"\nBáo cáo: {out / 'backtest_report.html'}")
    print("(Công cụ hỗ trợ phân tích, không phải lời khuyên đầu tư.)")


if __name__ == "__main__":
    main()
