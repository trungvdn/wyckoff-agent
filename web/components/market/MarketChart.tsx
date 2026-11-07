"use client";

// Biểu đồ nến VN-Index: SMA20/50/200, khối lượng kèm trung bình, dấu đỉnh và dải xu hướng dưới cùng.
// Toàn bộ số liệu lấy từ API; khung nhìn mặc định 1 năm (6 tháng trên màn hình hẹp).
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type Time,
} from "lightweight-charts";
import { useEffect, useRef, useState } from "react";
import { PaneLabel, StageStrip } from "@/components/dashboard/chartPrimitives";
import { tickLabel, timeToIso } from "@/components/dashboard/chartTime";
import { Card, Eyebrow, cx } from "@/components/ui/Card";
import { fmtDate, fmtPct2, fmtPrice, fmtRatio, fmtVolume } from "@/lib/format";
import type { MarketOverview } from "@/lib/types";

const RIGHT_GAP = 4;
const NARROW_PX = 560;
const STRIP_MARGIN = 0.18; // phần đáy pane khối lượng chừa cho dải xu hướng

type Span = { from: number; to: number };
type PresetId = "3m" | "6m" | "1y" | "3y" | "all";

const PRESETS: { id: PresetId; label: string; months?: number }[] = [
  { id: "3m", label: "3T", months: 3 },
  { id: "6m", label: "6T", months: 6 },
  { id: "1y", label: "1N", months: 12 },
  { id: "3y", label: "3N", months: 36 },
  { id: "all", label: "Tất cả" },
];

function presetSpan(id: PresetId, d: MarketOverview): Span {
  const n = d.bars.length;
  const to = n - 1 + RIGHT_GAP;
  const months = PRESETS.find((p) => p.id === id)?.months;
  if (!months) return { from: 0, to };
  const cutoff = new Date(`${d.bars[n - 1].t}T00:00:00Z`);
  cutoff.setUTCMonth(cutoff.getUTCMonth() - months);
  const iso = cutoff.toISOString().slice(0, 10);
  return { from: Math.max(d.bars.findIndex((b) => b.t >= iso), 0), to };
}

function Dash({ color }: { color: string }) {
  return <span aria-hidden="true" className={cx("w-3.5 border-t-2", color)} />;
}

function Readout({ d, index }: { d: MarketOverview; index: number }) {
  const b = d.bars[index];
  const prev = index > 0 ? d.bars[index - 1] : null;
  const chg = prev ? (b.c / prev.c - 1) * 100 : null;
  const num = "font-mono text-fg-2 tabular-nums";
  return (
    <div className="flex flex-col gap-1 text-xs text-muted">
      <span className="font-mono text-[13px] text-fg tabular-nums">
        {fmtDate(b.t)} · O {fmtPrice(b.o)} H {fmtPrice(b.h)} L {fmtPrice(b.l)} C {fmtPrice(b.c)}{" "}
        {chg != null && <span className={chg >= 0 ? "text-pos" : "text-neg"}>{fmtPct2(chg)}</span>}
      </span>
      <ul aria-label="Chú giải" className="m-0 flex list-none flex-wrap gap-x-4 gap-y-1 p-0">
        <li className="flex items-center gap-1.5"><Dash color="border-sma-short" />SMA{d.sma_short_period} <span className={num}>{fmtPrice(b.sma_short)}</span></li>
        <li className="flex items-center gap-1.5"><Dash color="border-ema-fast" />SMA{d.sma_periods[0]}<span className={num}>{fmtPrice(b.sma_fast)}</span></li>
        <li className="flex items-center gap-1.5"><Dash color="border-ema-slow" />SMA{d.sma_periods[1]} <span className={num}>{fmtPrice(b.sma_slow)}</span></li>
        <li className="flex items-center gap-1.5">KL <span className={num}>{fmtVolume(b.v)}</span></li>
        <li className="flex items-center gap-1.5">
          <Dash color="border-event" />TB{d.volume_ma_period} KL <span className={num}>{fmtVolume(b.vma)}{b.vma ? ` (×${fmtRatio(b.v / b.vma)})` : ""}</span>
        </li>
      </ul>
    </div>
  );
}

function StripLegend() {
  const item = (cls: string, label: string) => (
    <li className="flex items-center gap-1.5"><span aria-hidden="true" className={cx("h-2 w-3", cls)} />{label}</li>
  );
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
      <span>Dải dưới biểu đồ:</span>
      <ul className="m-0 flex list-none flex-wrap gap-x-4 gap-y-1 p-0">
        {item("bg-pos", "Tăng")}
        {item("bg-vol", "Đi ngang")}
        {item("bg-neg", "Giảm")}
      </ul>
      {/* Ghi công theo giấy phép Lightweight Charts, thay cho logo nổi vốn che dải xu hướng */}
      <a href="https://www.tradingview.com/" target="_blank" rel="noopener noreferrer" className="text-faint hover:text-fg-2 sm:ml-auto">
        Biểu đồ: TradingView Lightweight Charts
      </a>
    </div>
  );
}

export function MarketChart({ data: d }: { data: MarketOverview }) {
  const boxRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const expectedRef = useRef<Span | null>(null);  // khung nhìn của nút đang chọn; người dùng zoom / kéo -> bỏ chọn
  const gestureRef = useRef(false);               // đã có thao tác trên biểu đồ (phân biệt với đổi kích thước)
  const [hover, setHover] = useState<number | null>(null);
  const [preset, setPreset] = useState<PresetId | null>("1y");
  const n = d.bars.length;

  useEffect(() => {
    const box = boxRef.current;
    if (!box) return;
    const css = getComputedStyle(document.documentElement);
    const color = (name: string) => css.getPropertyValue(`--color-${name}`).trim();
    const fontFamily = getComputedStyle(box).fontFamily;
    const narrow = box.clientWidth < NARROW_PX;

    const chart = createChart(box, {
      width: box.clientWidth,
      height: box.clientHeight,
      layout: {
        background: { type: ColorType.Solid, color: color("surface") },
        textColor: color("muted"),
        fontFamily,
        fontSize: 11,
        attributionLogo: false,
        panes: { separatorColor: color("line-strong"), separatorHoverColor: color("line") },
      },
      grid: { vertLines: { visible: false }, horzLines: { color: color("grid") } },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: color("fg-2"), labelBackgroundColor: color("raised") },
        horzLine: { color: color("fg-2"), labelBackgroundColor: color("raised") },
      },
      rightPriceScale: { borderColor: color("line-strong"), scaleMargins: { top: 0.1, bottom: 0.06 } },
      timeScale: { borderColor: color("line-strong"), rightOffset: RIGHT_GAP, minBarSpacing: 0.1, fixLeftEdge: true, tickMarkFormatter: tickLabel },
      localization: { locale: "vi-VN", timeFormatter: (t: Time) => fmtDate(timeToIso(t)) },
      handleScroll: { vertTouchDrag: false }, // vuốt dọc trên điện thoại vẫn cuộn trang
    });

    const candles = chart.addSeries(CandlestickSeries, {
      upColor: color("pos"),
      downColor: color("neg"),
      wickUpColor: color("pos"),
      wickDownColor: color("neg"),
      borderVisible: false,
      priceLineVisible: false,
      priceFormat: { type: "custom", formatter: fmtPrice, minMove: 0.01 },
    });
    candles.setData(d.bars.map((b) => ({ time: b.t as Time, open: b.o, high: b.h, low: b.l, close: b.c })));
    createSeriesMarkers(candles, [{
      time: d.drawdown.peak_date as Time,
      position: "aboveBar",
      shape: "arrowDown",
      color: color("event"),
      // Màn hình hẹp: nhãn dài bị cắt ở mép, con số đã có trong ô "so với đỉnh"
      text: narrow ? "Đỉnh" : `Đỉnh ${d.drawdown.lookback} phiên ${fmtPrice(d.drawdown.peak)}`,
    }]);

    const smaLine = (name: string, lineWidth: 1 | 2 = 2) => chart.addSeries(LineSeries, { color: color(name), lineWidth, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
    smaLine("sma-short", 1).setData(d.bars.flatMap((b) => (b.sma_short != null ? [{ time: b.t as Time, value: b.sma_short }] : [])));
    smaLine("ema-fast").setData(d.bars.flatMap((b) => (b.sma_fast != null ? [{ time: b.t as Time, value: b.sma_fast }] : [])));
    smaLine("ema-slow").setData(d.bars.flatMap((b) => (b.sma_slow != null ? [{ time: b.t as Time, value: b.sma_slow }] : [])));

    const volumeFormat = { type: "custom", formatter: fmtVolume, minMove: 1 } as const;
    const volume = chart.addSeries(HistogramSeries, { priceFormat: volumeFormat, priceLineVisible: false, lastValueVisible: false }, 1);
    volume.setData(d.bars.map((b) => ({ time: b.t as Time, value: b.v, color: color(b.c >= b.o ? "pos-dim" : "neg-dim") })));
    volume.priceScale().applyOptions({ scaleMargins: { top: 0.14, bottom: STRIP_MARGIN } });
    volume.attachPrimitive(new PaneLabel("Khối lượng", color("muted"), `12px ${fontFamily}`));
    const volumeMa = chart.addSeries(LineSeries, { color: color("event"), lineWidth: 1, priceFormat: volumeFormat, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false }, 1);
    volumeMa.setData(d.bars.flatMap((b) => (b.vma ? [{ time: b.t as Time, value: b.vma }] : [])));

    const trendColor = { uptrend: color("pos"), downtrend: color("neg"), sideways: color("vol") };
    volume.attachPrimitive(new StageStrip(
      d.trend_segments.map((s) => ({ i0: s.i0, i1: s.i1, label: "", color: trendColor[s.kind], alpha: 1 })),
      color("fg"),
      `600 11px ${fontFamily}`,
    ));

    const [pricePane, volumePane] = chart.panes();
    pricePane.setStretchFactor(0.76);
    volumePane.setStretchFactor(0.24);

    const initial = presetSpan(narrow ? "6m" : "1y", d);
    expectedRef.current = initial;
    gestureRef.current = false;
    chart.timeScale().setVisibleLogicalRange(initial);
    chart.timeScale().subscribeVisibleLogicalRangeChange((r) => {
      if (r && gestureRef.current && expectedRef.current) {
        expectedRef.current = null;
        setPreset(null);
      }
    });
    chart.subscribeCrosshairMove((param) => {
      const i = param.point && param.logical !== undefined ? Math.round(param.logical) : null;
      setHover(i !== null && i >= 0 && i < d.bars.length ? i : null);
    });

    const keepExpected = () => {
      if (expectedRef.current) chart.timeScale().setVisibleLogicalRange(expectedRef.current);
    };
    const ro = new ResizeObserver(() => {
      chart.resize(box.clientWidth, box.clientHeight);
      keepExpected();
    });
    ro.observe(box);
    const settle = requestAnimationFrame(() => {
      keepExpected();
      if (narrow) setPreset("6m");
    });
    const markGesture = () => {
      gestureRef.current = true;
    };
    const gestures = ["wheel", "pointerdown", "touchstart"] as const;
    for (const g of gestures) box.addEventListener(g, markGesture, { capture: true, passive: true });
    let alive = true;
    document.fonts?.ready.then(() => {
      if (alive) chart.applyOptions({ layout: { fontFamily } }); // vẽ lại sau khi font tự host đã tải
    });
    chartRef.current = chart;

    return () => {
      alive = false;
      cancelAnimationFrame(settle);
      for (const g of gestures) box.removeEventListener(g, markGesture, { capture: true });
      ro.disconnect();
      chartRef.current = null;
      chart.remove();
    };
  }, [d]);

  function selectPreset(id: PresetId) {
    const span = presetSpan(id, d);
    gestureRef.current = false;
    expectedRef.current = span;
    setPreset(id);
    chartRef.current?.timeScale().setVisibleLogicalRange(span);
  }

  const label = `Biểu đồ nến ${d.symbol}, ${n} phiên, kèm SMA${d.sma_short_period}, SMA${d.sma_periods[0]}, SMA${d.sma_periods[1]}, khối lượng và dải xu hướng. Đóng cửa phiên cuối ${fmtPrice(d.close)}.`;

  return (
    <Card labelledBy="market-chart-h" className="pb-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Eyebrow id="market-chart-h">Biểu đồ ngày</Eyebrow>
        <div role="group" aria-label="Khoảng thời gian hiển thị" className="grid grid-cols-5 gap-1 max-sm:w-full sm:flex">
          {PRESETS.map((o) => (
            <button
              key={o.id}
              type="button"
              aria-pressed={preset === o.id}
              onClick={() => selectPreset(o.id)}
              className={cx(
                "h-11 cursor-pointer rounded-md border px-2.5 text-[13px] transition-colors sm:h-8",
                preset === o.id ? "border-pos bg-pos-soft font-semibold text-pos-hover" : "border-line-strong text-fg-2 hover:border-muted",
              )}
            >
              {o.label}
            </button>
          ))}
        </div>
      </div>
      <Readout d={d} index={hover ?? n - 1} />
      <div ref={boxRef} role="img" aria-label={label} className="relative h-[420px] w-full overflow-hidden rounded-lg font-mono sm:h-[500px] wide:h-[560px]" />
      <StripLegend />
    </Card>
  );
}
