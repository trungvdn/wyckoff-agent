"""CLI giai đoạn 1.

    python run.py HPG --start 2020-01-01
    python run.py HPG --start 2020-01-01 --refresh --config config/default.yaml
    python run.py --demo            # dữ liệu tổng hợp, không cần mạng
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd

from wyckoff.config import load_config
from wyckoff.data.loader import get_ohlcv, warmup_start
from wyckoff.detectors.models import EventStatus
from wyckoff.pipeline import AnalysisResult, analyze
from wyckoff.synthetic import make_wyckoff_accumulation


def print_report(symbol: str, result: AnalysisResult) -> None:
    df = result.df
    print(f"\n=== {symbol}: {df.index[0]:%Y-%m-%d} -> {df.index[-1]:%Y-%m-%d} ({len(df)} phiên) ===")
    print(f"\nTrading range ({len(result.ranges)}):")
    for r in result.ranges:
        status = (
            "ĐANG HOẠT ĐỘNG" if r.end_confirmed_date is None
            else f"thoát {r.exit_direction} (xác nhận {r.end_confirmed_date:%Y-%m-%d})"
        )
        prior = "n/a" if r.prior_return is None else f"{r.prior_return:+.0%}"
        print(
            f"  TR#{r.range_id}: {r.start_date:%Y-%m-%d} -> {r.end_date:%Y-%m-%d}, "
            f"support {r.support:.2f}, resistance {r.resistance:.2f} "
            f"({r.height / r.atr_at_confirm:.1f} ATR), xác nhận {r.confirmed_date:%Y-%m-%d}, {status}, "
            f"bối cảnh {r.context} (lợi suất trước range {prior})"
        )
    print(f"\nSự kiện ({len(result.events)}):")
    for e in result.events:
        conf = f" [xác nhận {e.confirmed_date:%Y-%m-%d}]" if e.confirmed_idx != e.idx else ""
        inv = e.invalidated
        st = e.status.value + (f" {inv.date:%Y-%m-%d}: {inv.reason}" if inv is not None else "")
        print(f"  {e.evidence()}{conf}  <{e.event_id} | {st}>")
    open_c = [c for c in result.candidates if c.status in (EventStatus.DETECTED, EventStatus.CANDIDATE)]
    print(f"\nCandidate chưa xác nhận ({len(result.candidates)}, đang mở {len(open_c)}):")
    for c in open_c:
        print(f"  {c.event_id}: {c.status.value} từ {c.history[-1].date:%Y-%m-%d} – {c.history[-1].reason}")
    print(f"\nPha ({len(result.phases.segments)} đoạn):")
    for g in result.phases.segments:
        rid = "" if g.range_id is None else f" TR#{g.range_id}"
        print(f"  {g.phase:7s} {g.start_date:%Y-%m-%d} -> {g.end_date:%Y-%m-%d}{rid}  [{g.reason}]")

    print(f"\nSự kiện phía phân phối, chỉ ghi nhận ({len(result.distribution)}):")
    for e in result.distribution:
        print(f"  {e.evidence()}  <{e.event_id} | {e.status.value}>")

    stage = result.current_stage()
    print(f"\n=== GIAI ĐOẠN HIỆN TẠI: {stage.structure_type}" + (f" ({stage.stage})" if stage.stage else "") + " ===")
    print(f"  {stage.reason}" + (f"; giả thuyết: {' hoặc '.join(stage.candidates)}" if stage.candidates else ""))

    cur = result.current()
    print(f"\n=== PHA HIỆN TẠI ({cur.date:%Y-%m-%d}): {cur.phase or 'chưa có cấu trúc'} ===")
    if cur.phase:
        print(f"  Từ {cur.since:%Y-%m-%d} – {cur.reason}")
        if cur.support is not None:
            res_txt = f"{cur.resistance:.2f}" if cur.resistance is not None else "n/a"
            print(f"  Support {cur.support:.2f} / resistance {res_txt}, ATR {cur.atr:.2f}"
                  + (f", bối cảnh {cur.range_context}" if cur.range_context else ""))
        print("  Bằng chứng:")
        for ev in cur.evidence:
            print(f"    - {ev}")
        for title, levels in (("Kịch bản xác nhận", cur.confirm), ("Kịch bản vô hiệu", cur.invalidate)):
            print(f"  {title}:")
            for lv in levels:
                print(f"    - {lv.label}: {lv.condition}")
        for w in cur.warnings:
            print(f"  ! {w}")
    print("\n(Công cụ hỗ trợ phân tích, không phải lời khuyên đầu tư.)")


def main() -> None:
    p = argparse.ArgumentParser(description="Wyckoff phase-1: dữ liệu + phát hiện sự kiện")
    p.add_argument("symbol", nargs="?", default="HPG")
    p.add_argument("--start", default="2020-01-01")
    p.add_argument("--end", default=None)
    p.add_argument("--config", default=None)
    p.add_argument("--cache-dir", default="cache")
    p.add_argument("--out-dir", default="output")
    p.add_argument("--refresh", action="store_true", help="bỏ qua cache, tải lại toàn bộ")
    p.add_argument("--demo", action="store_true", help="dùng dữ liệu tổng hợp")
    p.add_argument("--swings", action="store_true", help="vẽ thêm swing high/low")
    p.add_argument("--explain", action="store_true", help="giai đoạn 2: LLM diễn giải + báo cáo HTML")
    p.add_argument("--no-llm", action="store_true", help="với --explain: dùng báo cáo theo mẫu, không gọi LLM")
    p.add_argument("--model", default=None, help="model Claude (mặc định claude-sonnet-5-5)")
    p.add_argument("--no-market", action="store_true", help="với --explain: không dùng bối cảnh chỉ số thị trường")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = load_config(args.config)
    symbol = "DEMO" if args.demo else args.symbol.upper()

    if args.demo:
        result = analyze(make_wyckoff_accumulation(), cfg)
    else:
        fetch_from = warmup_start(args.start, cfg.data.warmup_bars)
        ohlcv = get_ohlcv(symbol, fetch_from, args.end, cache_dir=args.cache_dir, cfg=cfg.data, refresh=args.refresh)
        n_warm = int((ohlcv.index < pd.Timestamp(args.start)).sum())
        logging.info("Khởi động chỉ báo bằng %d phiên trước %s (từ %s)", n_warm, args.start, ohlcv.index[0].date())
        result = analyze(ohlcv, cfg).since(args.start)
    print_report(symbol, result)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    result.events_frame(include_candidates=True).to_csv(out / f"{symbol}_events.csv", index=False)
    result.ranges_frame().to_csv(out / f"{symbol}_ranges.csv", index=False)
    result.phases_frame().to_csv(out / f"{symbol}_phases.csv", index=False)
    result.stages_frame().to_csv(out / f"{symbol}_stages.csv", index=False)
    result.distribution_frame().to_csv(out / f"{symbol}_distribution.csv", index=False)
    result.distribution_phases_frame().to_csv(out / f"{symbol}_distribution_phases.csv", index=False)
    (out / f"{symbol}_current_phase.json").write_text(
        json.dumps(result.current().to_dict(), ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    from wyckoff.charts.plot import build_figure, save_html

    try:
        import plotly  # noqa: F401
        has_plotly = True
    except ImportError:
        has_plotly = False
        print("Chưa cài plotly -> bỏ qua biểu đồ (pip install plotly)")
    fig = build_figure(result, symbol, show_swings=args.swings) if has_plotly else None
    if fig is not None:
        print(f"Biểu đồ: {save_html(fig, out / f'{symbol}_wyckoff.html')}")

    if args.explain:
        run_explain(result, symbol, out, fig, args, cfg)


def load_market(result, symbol: str, args, cfg):
    """Tải chỉ số so sánh, chạy detector trên chỉ số, dựng bối cảnh thị trường. Lỗi -> (None, None, None)."""
    from wyckoff.service import load_market as _load_market

    return _load_market(result, symbol, cfg, start=args.start, end=args.end, cache_dir=args.cache_dir,
                        refresh=args.refresh, demo=args.demo)


def run_explain(result, symbol: str, out: Path, fig, args, cfg) -> None:
    from wyckoff.agent.explain import explain
    from wyckoff.agent.llm import DEFAULT_MODEL, AnthropicClient, LLMError
    from wyckoff.agent.payload import build_payload, payload_json
    from wyckoff.agent.report import render_html

    market, idx, bench = (None, None, None) if (args.no_market or not cfg.market.enabled) else load_market(result, symbol, args, cfg)
    if market:
        print(f"\nThị trường: {bench} xu hướng {market['trend']}, RS 60 phiên {market['rs'].get('rs_change_60d_pct')}%, "
              f"phân kỳ đáy: {market['divergence']['bullish_divergence']}")
    payload = build_payload(result, symbol, market)
    (out / f"{symbol}_payload.json").write_text(payload_json(payload), encoding="utf-8")
    client, reason = None, "chạy với --no-llm"
    if not args.no_llm:
        try:
            client = AnthropicClient(model=args.model or DEFAULT_MODEL)
        except LLMError as exc:
            reason = str(exc)
            print(f"Không dùng được LLM ({exc}) -> báo cáo theo mẫu")
    res = explain(payload, client, cache_dir=out / "llm_cache", no_llm_reason=reason)
    (out / f"{symbol}_explanation.json").write_text(
        json.dumps({"source": res.source, "model": res.model, "attempts": res.attempts, "errors": res.errors,
                    "explanation": res.explanation}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    chart = fig.to_html(full_html=False, include_plotlyjs="cdn") if fig is not None else None
    rs_chart = None
    if fig is not None and idx is not None:
        from wyckoff.charts.plot import build_rs_figure

        rs_chart = build_rs_figure(result.df, idx, bench, symbol, cfg.market.rs_sma).to_html(full_html=False, include_plotlyjs="cdn")
    html_text = render_html(payload, res.explanation, source=res.source, model=res.model,
                            errors=res.errors if res.source == "template" else None, chart_html=chart, rs_chart_html=rs_chart)
    path = out / f"{symbol}_report.html"
    path.write_text(html_text, encoding="utf-8")
    print(f"\nDiễn giải: {res.source}" + (f" ({res.model}, {res.attempts} lần gọi)" if res.model else ""))
    for e in res.errors:
        print(f"  ! {e}")
    print(f"\n{res.explanation['summary']}")
    print(f"Báo cáo: {path}")


if __name__ == "__main__":
    pd.set_option("display.width", 160)
    main()
