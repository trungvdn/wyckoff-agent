"use client";

// Biểu đồ nến + khối lượng tương tác (TradingView Lightweight Charts): zoom, kéo, co giãn trục.
// Toàn bộ lịch sử nằm trong `bars`; khung nhìn mặc định bắt đầu từ `view_from`.
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineStyle,
  TickMarkType,
  createChart,
  type BusinessDay,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Card, CardHeader, Eyebrow, cx } from "@/components/ui/Card";
import { fmtDate, fmtDateShort, fmtPct, fmtPrice, fmtRatio, fmtVolume } from "@/lib/format";
import type { Analysis, Bar } from "@/lib/types";
import { EventLabels, PaneLabel, PhaseBands, RangeBoxes, StageStrip } from "./chartPrimitives";

const RIGHT_GAP = 4;          // số ô trống bên phải nến cuối
const DENSE_BARS = 250;       // nhìn rộng hơn: ẩn chữ sự kiện của các cấu trúc cũ để biểu đồ đỡ dày
const MIN_VISIBLE_BARS = 10;
const ZOOM_STEP = 1.25;

const phaseLabel = (phase: string) => (phase === "invalid" ? "Vô hiệu" : phase === "potential" ? "Chờ xác nhận" : `Pha ${phase}`);
const phaseBandLabel = (phase: string) => (phase === "invalid" ? "Vô hiệu" : phase === "potential" ? "Chờ" : phase);
const POTENTIAL_STRIP_ALPHA = 0.18;

type Span = { from: number; to: number };
type PresetId = "default" | "3m" | "6m" | "1y" | "3y" | "all";

const PRESETS: { id: PresetId; label: string; months?: number }[] = [
  { id: "default", label: "Mặc định" },
  { id: "3m", label: "3T", months: 3 },
  { id: "6m", label: "6T", months: 6 },
  { id: "1y", label: "1N", months: 12 },
  { id: "3y", label: "3N", months: 36 },
  { id: "all", label: "Tất cả" },
];

function presetSpan(id: PresetId, d: Analysis): Span {
  const n = d.bars.length;
  const to = n - 1 + RIGHT_GAP;
  const months = PRESETS.find((p) => p.id === id)?.months;
  if (id === "default") return { from: d.view_from, to };
  if (!months) return { from: 0, to };
  const cutoff = new Date(`${d.bars[n - 1].t}T00:00:00Z`);
  cutoff.setUTCMonth(cutoff.getUTCMonth() - months);
  const iso = cutoff.toISOString().slice(0, 10);
  const from = d.bars.findIndex((b) => b.t >= iso);
  return { from: Math.max(from, 0), to };
}

/** Thời gian của thư viện (chuỗi hoặc BusinessDay) -> "YYYY-MM-DD". */
function timeToIso(t: Time): string {
  if (typeof t === "string") return t;
  if (typeof t === "number") return new Date(t * 1000).toISOString().slice(0, 10);
  const { year, month, day } = t as BusinessDay;
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

function tickLabel(t: Time, type: TickMarkType): string {
  const iso = timeToIso(t);
  if (type === TickMarkType.Year) return iso.slice(0, 4);
  if (type === TickMarkType.Month) return `T${Number(iso.slice(5, 7))}/${iso.slice(2, 4)}`;
  return fmtDateShort(iso);
}

function Readout({ d, index }: { d: Analysis; index: number }) {
  const bar: Bar = d.bars[index];
  const prev = index > 0 ? d.bars[index - 1] : null;
  const chg = prev ? (bar.c / prev.c - 1) * 100 : null;
  const seg = d.phase_segments.find((g) => g.i0 <= index && index <= g.i1);
  return (
    <span className="font-mono text-[13px] text-fg tabular-nums">
      {d.symbol} · {d.timeframe === "1W" ? "Tuần" : "Ngày"} {fmtDateShort(bar.t, "full")}{seg && ` · ${phaseLabel(seg.phase)}`} · O {fmtPrice(bar.o)} H {fmtPrice(bar.h)} L {fmtPrice(bar.l)} C {fmtPrice(bar.c)}{" "}
      {chg != null && <span className={chg >= 0 ? "text-pos" : "text-neg"}>{fmtPct(chg)}</span>} · KL {fmtVolume(bar.v)}
      {bar.vr != null && ` (${fmtRatio(bar.vr)}× TB20)`}
    </span>
  );
}

function Legend() {
  return (
    <ul aria-label="Chú giải" className="m-0 flex list-none flex-wrap gap-4 p-0 text-[13px] text-muted">
      <li className="flex items-center gap-1.5"><span className="h-2.5 w-3 border border-pos bg-range" />Vùng giao dịch</li>
      <li className="flex items-center gap-1.5">
        <span aria-hidden="true" className="flex">
          <span className="h-2.5 w-1.5 bg-phase-a/50" />
          <span className="h-2.5 w-1.5 bg-phase-b/50" />
          <span className="h-2.5 w-1.5 bg-phase-c/50" />
          <span className="h-2.5 w-1.5 bg-phase-d/50" />
          <span className="h-2.5 w-1.5 bg-phase-e/50" />
          <span className="h-2.5 w-1.5 bg-phase-invalid/50" />
          <span className="h-2.5 w-1.5 bg-phase-potential/50" />
        </span>
        Pha A–E, vô hiệu, chờ xác nhận
      </li>
      <li className="flex items-center gap-1.5">
        <span aria-hidden="true" className="flex">
          <span className="h-2.5 w-1.5 bg-pos/60" />
          <span className="h-2.5 w-1.5 bg-event-dim" />
          <span className="h-2.5 w-1.5 bg-neg/60" />
        </span>
        Dải giai đoạn
      </li>
      <li className="flex items-center gap-1.5">
        <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true"><polygon points="5 0 10 10 0 10" className="fill-event" /></svg>
        Sự kiện đã xác nhận
      </li>
      <li className="flex items-center gap-1.5">
        <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true"><polygon points="5 1 9.5 9.5 0.5 9.5" className="fill-none stroke-event" /></svg>
        Tiềm năng
      </li>
      <li className="flex items-center gap-1.5"><span className="w-3.5 border-t-2 border-dashed border-muted" />Kháng cự / Hỗ trợ</li>
    </ul>
  );
}

const CONTROL = "flex h-11 min-w-11 cursor-pointer items-center justify-center rounded-lg border px-2.5 text-[13px] font-medium transition-colors sm:px-3";

export function PriceChart({ data: d }: { data: Analysis }) {
  const boxRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<{ chart: IChartApi; candles: ISeriesApi<"Candlestick"> } | null>(null);
  const viewRef = useRef<Span | null>(null);       // khung nhìn hiện tại, giữ lại khi dữ liệu được làm mới
  const expectedRef = useRef<Span | null>(null);   // khung nhìn của nút đang chọn; người dùng zoom / kéo -> bỏ chọn
  const gestureRef = useRef(false);                // đã có thao tác trên biểu đồ (phân biệt với đổi kích thước)
  const cursorRef = useRef<number | null>(null);   // con trỏ điều khiển bằng bàn phím
  const [hover, setHover] = useState<number | null>(null);
  const [preset, setPreset] = useState<PresetId | null>("default");
  const [showRejected, setShowRejected] = useState(true);
  const n = d.bars.length;

  useEffect(() => {
    const box = boxRef.current;
    if (!box) return;
    const css = getComputedStyle(document.documentElement);
    const color = (name: string) => css.getPropertyValue(`--color-${name}`).trim();
    const fontFamily = getComputedStyle(box).fontFamily;
    const narrow = box.clientWidth < 560;

    const chart = createChart(box, {
      width: box.clientWidth,
      height: box.clientHeight,
      layout: {
        background: { type: ColorType.Solid, color: color("surface") },
        textColor: color("muted"),
        fontFamily,
        fontSize: 11,
        panes: { separatorColor: color("line-strong"), separatorHoverColor: color("line") },
      },
      grid: { vertLines: { visible: false }, horzLines: { color: color("grid") } },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: color("fg-2"), labelBackgroundColor: color("raised") },
        horzLine: { color: color("fg-2"), labelBackgroundColor: color("raised") },
      },
      // Chừa chỗ trên / dưới cho nhãn sự kiện
      rightPriceScale: { borderColor: color("line-strong"), scaleMargins: { top: 0.12, bottom: 0.2 } },
      timeScale: {
        borderColor: color("line-strong"),
        rightOffset: RIGHT_GAP,
        minBarSpacing: 0.1,
        fixLeftEdge: true,
        tickMarkFormatter: tickLabel,
      },
      localization: { locale: "vi-VN", timeFormatter: (t: Time) => fmtDate(timeToIso(t)) },
      // Vuốt dọc trên điện thoại vẫn cuộn trang; vuốt ngang để kéo biểu đồ
      handleScroll: { vertTouchDrag: false },
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
    candles.attachPrimitive(
      new PhaseBands(
        d.phase_segments.map((g) => ({ ...g, label: phaseBandLabel(g.phase), color: color(`phase-${g.phase.toLowerCase()}`) })),
        `600 12px ${fontFamily}`,
      ),
    );
    // Gắn sau dải pha để nằm đè lên; viền giúp vùng giao dịch nổi trên mọi màu pha
    candles.attachPrimitive(
      new RangeBoxes(d.ranges.map((r) => ({ ...r, opacity: r.current ? 0.24 : 0.16, borderOpacity: r.current ? 0.9 : 0.45 })), color("pos")),
    );
    for (const r of d.ranges.filter((x) => x.current)) {
      for (const [price, lineColor, title] of [[r.resistance, color("pos"), "Kháng cự"], [r.support, color("fg-2"), "Hỗ trợ"]] as const) {
        candles.createPriceLine({ price, color: lineColor, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: narrow ? "" : title });
      }
    }

    const event = color("event");
    candles.attachPrimitive(new EventLabels(
      d.chart_events.filter((e) => showRejected || e.status !== "rejected").map((e) => ({ ...e, high: d.bars[e.i].h, low: d.bars[e.i].l })),
      event,
      `600 12px ${fontFamily}`,
      DENSE_BARS,
    ));
    const stageColor = {
      up: color("pos"), down: color("neg"), up_potential: color("pos"), down_potential: color("neg"),
      range: color("event-dim"), accumulation: color("event"), accumulation_developing: color("event"), none: color("pending"),
    };
    candles.attachPrimitive(new StageStrip(
      d.stage_segments.map((s) => ({ ...s, color: stageColor[s.kind], alpha: s.kind.endsWith("_potential") || s.kind === "accumulation_developing" ? POTENTIAL_STRIP_ALPHA : undefined })),
      color("fg"),
      `600 11px ${fontFamily}`,
    ));
    const initial = viewRef.current ?? presetSpan("default", d);

    // Pane khối lượng: SC đỏ, SOS xanh, còn lại xám; đường TB20
    const eventAt = new Map(d.chart_events.filter((e) => e.current).map((e) => [e.i, e.kind]));
    const volumeFormat = { type: "custom", formatter: fmtVolume, minMove: 1 } as const;
    const volume = chart.addSeries(HistogramSeries, { priceFormat: volumeFormat, priceLineVisible: false, lastValueVisible: false }, 1);
    volume.setData(d.bars.map((b, i) => {
      const kind = eventAt.get(i);
      return { time: b.t as Time, value: b.v, color: color(kind === "SC" ? "neg" : kind === "SOS" ? "pos" : "vol") };
    }));
    volume.attachPrimitive(new PaneLabel("Khối lượng", color("muted"), `12px ${fontFamily}`));
    const volumeMa = chart.addSeries(LineSeries, {
      color: event,
      lineWidth: 1,
      lineStyle: LineStyle.SparseDotted,
      priceFormat: volumeFormat,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
      title: narrow ? "" : "TB20",
    }, 1);
    volumeMa.setData(d.bars.flatMap((b) => (b.vma ? [{ time: b.t as Time, value: b.vma }] : [])));
    const [pricePane, volumePane] = chart.panes();
    pricePane.setStretchFactor(0.78);
    volumePane.setStretchFactor(0.22);

    if (!viewRef.current) expectedRef.current = initial;
    chart.timeScale().setVisibleLogicalRange(initial);
    chart.timeScale().subscribeVisibleLogicalRangeChange((r) => {
      if (!r) return;
      viewRef.current = { from: r.from, to: r.to };
      if (gestureRef.current && expectedRef.current) {
        expectedRef.current = null;
        setPreset(null);
      }
    });

    chart.subscribeCrosshairMove((param) => {
      if (param.sourceEvent) {
        cursorRef.current = null; // chuột / chạm thật giành lại con trỏ từ bàn phím
      } else if (cursorRef.current !== null) {
        return;
      }
      const i = param.point && param.logical !== undefined ? Math.round(param.logical) : null;
      setHover(i !== null && i >= 0 && i < d.bars.length ? i : null);
    });

    // Giữ khung nhìn của nút đang chọn khi vùng vẽ đổi rộng (đổi kích thước; lần đo trục giá đầu tiên)
    const keepExpected = () => {
      if (expectedRef.current) chart.timeScale().setVisibleLogicalRange(expectedRef.current);
    };
    const ro = new ResizeObserver(() => {
      chart.resize(box.clientWidth, box.clientHeight);
      keepExpected();
    });
    ro.observe(box);
    const settle = requestAnimationFrame(keepExpected);
    const markGesture = () => {
      gestureRef.current = true;
    };
    const gestures = ["wheel", "pointerdown", "touchstart"] as const;
    for (const g of gestures) box.addEventListener(g, markGesture, { capture: true, passive: true });
    let alive = true;
    document.fonts?.ready.then(() => {
      if (alive) chart.applyOptions({ layout: { fontFamily } }); // vẽ lại sau khi font tự host đã tải
    });
    chartRef.current = { chart, candles };

    return () => {
      alive = false;
      cancelAnimationFrame(settle);
      for (const g of gestures) box.removeEventListener(g, markGesture, { capture: true });
      ro.disconnect();
      chartRef.current = null;
      chart.remove();
    };
  }, [d, showRejected]);

  function applySpan(span: Span) {
    chartRef.current?.chart.timeScale().setVisibleLogicalRange(span);
  }

  /** Đổi khung nhìn bằng nút +/− hoặc bàn phím: không còn khớp nút khoảng thời gian nào. */
  function applyManualSpan(span: Span) {
    expectedRef.current = null;
    setPreset(null);
    applySpan(span);
  }

  function selectPreset(id: PresetId) {
    const span = presetSpan(id, d);
    gestureRef.current = false;
    expectedRef.current = span;
    setPreset(id);
    applySpan(span);
  }

  function zoom(factor: number) {
    const r = chartRef.current?.chart.timeScale().getVisibleLogicalRange();
    if (!r) return;
    const width = Math.max((r.to - r.from) * factor, MIN_VISIBLE_BARS);
    // Giữ mép phải (nến mới nhất), như khi đọc biểu đồ từ hiện tại về quá khứ
    applyManualSpan({ from: Math.max(r.to - width, 0), to: r.to });
  }

  function moveCursor(i: number) {
    const c = chartRef.current;
    if (!c) return;
    const bar = d.bars[i];
    cursorRef.current = i;
    setHover(i);
    c.chart.setCrosshairPosition(bar.c, bar.t as Time, c.candles);
    const r = c.chart.timeScale().getVisibleLogicalRange();
    if (r && (i < r.from || i > r.to)) {
      const shift = i < r.from ? i - r.from - 1 : i - r.to + 1;
      applyManualSpan({ from: r.from + shift, to: r.to + shift });
    }
  }

  function onKey(e: KeyboardEvent<HTMLDivElement>) {
    const cur = cursorRef.current ?? n - 1;
    const moves: Record<string, number> = { ArrowLeft: cur - 1, ArrowRight: cur + 1, Home: 0, End: n - 1, PageUp: cur - 20, PageDown: cur + 20 };
    if (e.key === "Escape") {
      cursorRef.current = null;
      setHover(null);
      chartRef.current?.chart.clearCrosshairPosition();
    } else if (e.key === "+" || e.key === "=") {
      zoom(1 / ZOOM_STEP);
    } else if (e.key === "-") {
      zoom(ZOOM_STEP);
    } else if (e.key in moves) {
      e.preventDefault();
      moveCursor(Math.min(n - 1, Math.max(0, moves[e.key])));
    }
  }

  const p = d.phase;
  const label = [
    `Biểu đồ nến ${d.symbol}, ${n} nến khung ${d.timeframe === "1W" ? "tuần" : "ngày"}`,
    p.title,
    p.support != null && p.resistance != null ? `hỗ trợ ${fmtPrice(p.support)}, kháng cự ${fmtPrice(p.resistance)}` : null,
    "Phím mũi tên trái phải để xem từng nến, phím cộng trừ để phóng to thu nhỏ",
  ].filter(Boolean).join(". ");

  return (
    <Card labelledBy="chart-h" className="pb-4">
      <CardHeader>
        <div className="flex flex-wrap items-baseline gap-3.5">
          <Eyebrow id="chart-h">Biểu đồ giá &amp; khối lượng</Eyebrow>
          <Readout d={d} index={hover ?? n - 1} />
        </div>
        <Legend />
      </CardHeader>

      <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
        <div role="group" aria-label="Khoảng thời gian hiển thị" className="flex flex-wrap gap-1.5 sm:gap-2">
          {PRESETS.map((o) => (
            <button
              key={o.id}
              type="button"
              aria-pressed={preset === o.id}
              onClick={() => selectPreset(o.id)}
              className={cx(CONTROL, preset === o.id ? "border-pos bg-pos font-semibold text-on-pos" : "border-line-strong bg-surface text-fg hover:border-muted")}
            >
              {o.label}
            </button>
          ))}
        </div>
        <div className="flex gap-1.5 sm:gap-2">
          <button type="button" aria-label="Phóng to" onClick={() => zoom(1 / ZOOM_STEP)} className={cx(CONTROL, "border-line-strong bg-surface font-mono text-base text-fg hover:border-muted")}>+</button>
          <button type="button" aria-label="Thu nhỏ" onClick={() => zoom(ZOOM_STEP)} className={cx(CONTROL, "border-line-strong bg-surface font-mono text-base text-fg hover:border-muted")}>−</button>
        </div>
        <button
          type="button"
          aria-pressed={showRejected}
          onClick={() => setShowRejected((v) => !v)}
          className={cx(CONTROL, "border-line-strong bg-surface text-fg hover:border-muted")}
        >
          {showRejected ? "Ẩn sự kiện bị bác bỏ" : "Hiện sự kiện bị bác bỏ"}
        </button>
        <span className="ml-auto hidden text-xs text-muted wide:inline">Cuộn chuột để zoom · kéo để xem ngày cũ · kéo trục giá để co giãn</span>
      </div>

      <div
        ref={boxRef}
        tabIndex={0}
        role="img"
        aria-label={label}
        onKeyDown={onKey}
        onBlur={() => {
          cursorRef.current = null;
          setHover(null);
          chartRef.current?.chart.clearCrosshairPosition();
        }}
        className="relative h-[400px] w-full overflow-hidden rounded-lg font-mono sm:h-[480px] wide:h-[540px]"
      />
    </Card>
  );
}
