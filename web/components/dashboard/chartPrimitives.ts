// Phần vẽ thêm trên Lightweight Charts: vùng giao dịch (chữ nhật theo chỉ số nến) và nhãn của pane.
import type {
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesPrimitive,
  Logical,
  SeriesAttachedParameter,
  Time,
} from "lightweight-charts";

export interface RangeBoxSpec {
  i0: number; // nến đầu
  i1: number; // nến cuối
  support: number;
  resistance: number;
  opacity: number;        // độ đậm nền
  borderOpacity: number;  // độ đậm viền
}

export interface PhaseBandSpec {
  i0: number;
  i1: number;
  label: string;
  color: string;
}

const PHASE_BAND_ALPHA = 0.13;

/** Dải nền theo pha phủ hết chiều cao vùng giá, tên pha ở đỉnh dải (ẩn nếu dải hẹp hơn chữ). */
export class PhaseBands implements ISeriesPrimitive<Time> {
  private host: SeriesAttachedParameter<Time> | null = null;
  private readonly views: IPrimitivePaneView[];

  constructor(bands: PhaseBandSpec[], font: string) {
    const renderer: IPrimitivePaneRenderer = {
      draw: (target) => {
        const time = this.host?.chart.timeScale();
        if (!time) return;
        const half = time.options().barSpacing / 2;
        target.useMediaCoordinateSpace(({ context, mediaSize }) => {
          context.font = font;
          context.textAlign = "left";
          for (const b of bands) {
            const x0 = time.logicalToCoordinate(b.i0 as Logical);
            const x1 = time.logicalToCoordinate(b.i1 as Logical);
            if (x0 === null || x1 === null) continue;
            const left = x0 - half;
            const width = x1 - x0 + 2 * half;
            context.fillStyle = b.color;
            context.globalAlpha = PHASE_BAND_ALPHA;
            context.fillRect(left, 0, width, mediaSize.height);
            // Khi dải bắt đầu ngoài màn hình, giữ tên pha ở mép trái phần đang thấy
            const labelX = Math.max(left, 0) + 4;
            if (left + width - labelX >= context.measureText(b.label).width + 4) {
              context.globalAlpha = 1;
              context.fillText(b.label, labelX, 14);
            }
          }
          context.globalAlpha = 1;
        });
      },
    };
    this.views = [{ zOrder: () => "bottom", renderer: () => renderer }];
  }

  attached(param: SeriesAttachedParameter<Time>) {
    this.host = param;
  }

  detached() {
    this.host = null;
  }

  paneViews() {
    return this.views;
  }
}

export interface StageStripSpec {
  i0: number;
  i1: number;
  label: string;
  color: string;
  alpha?: number;   // đoạn còn tiềm năng vẽ nhạt hơn
}

const STAGE_STRIP_HEIGHT = 16;

/** Dải giai đoạn mỏng ở đáy vùng giá, tên giai đoạn trong dải (ẩn nếu dải hẹp hơn chữ). */
export class StageStrip implements ISeriesPrimitive<Time> {
  private host: SeriesAttachedParameter<Time> | null = null;
  private readonly views: IPrimitivePaneView[];

  constructor(segments: StageStripSpec[], textColor: string, font: string) {
    const renderer: IPrimitivePaneRenderer = {
      draw: (target) => {
        const time = this.host?.chart.timeScale();
        if (!time) return;
        const half = time.options().barSpacing / 2;
        target.useMediaCoordinateSpace(({ context, mediaSize }) => {
          const top = mediaSize.height - STAGE_STRIP_HEIGHT;
          context.font = font;
          context.textAlign = "left";
          for (const s of segments) {
            const x0 = time.logicalToCoordinate(s.i0 as Logical);
            const x1 = time.logicalToCoordinate(s.i1 as Logical);
            if (x0 === null || x1 === null) continue;
            const left = x0 - half;
            const width = x1 - x0 + 2 * half;
            context.fillStyle = s.color;
            context.globalAlpha = s.alpha ?? 0.45;
            context.fillRect(left, top, width, STAGE_STRIP_HEIGHT);
            const labelX = Math.max(left, 0) + 4;
            if (s.label && left + width - labelX >= context.measureText(s.label).width + 4) {
              context.globalAlpha = 1;
              context.fillStyle = textColor;
              context.fillText(s.label, labelX, top + 12);
            }
          }
          context.globalAlpha = 1;
        });
      },
    };
    this.views = [{ zOrder: () => "normal", renderer: () => renderer }];
  }

  attached(param: SeriesAttachedParameter<Time>) {
    this.host = param;
  }

  detached() {
    this.host = null;
  }

  paneViews() {
    return this.views;
  }
}

/** Tô nền và viền các trading range, nằm dưới nến; tọa độ tính lại mỗi lần vẽ nên theo sát zoom và kéo. */
export class RangeBoxes implements ISeriesPrimitive<Time> {
  private host: SeriesAttachedParameter<Time> | null = null;
  private readonly views: IPrimitivePaneView[];

  constructor(boxes: RangeBoxSpec[], color: string) {
    const renderer: IPrimitivePaneRenderer = {
      draw: (target) => {
        const host = this.host;
        if (!host) return;
        const time = host.chart.timeScale();
        target.useBitmapCoordinateSpace(({ context, horizontalPixelRatio: hr, verticalPixelRatio: vr }) => {
          context.fillStyle = color;
          context.strokeStyle = color;
          context.lineWidth = Math.max(1, Math.floor(hr));
          for (const b of boxes) {
            // logicalToCoordinate chỉ nhận chỉ số nguyên (số lẻ trả về 0) nên mở rộng nửa ô bằng barSpacing
            const half = time.options().barSpacing / 2;
            const x0 = time.logicalToCoordinate(b.i0 as Logical);
            const x1 = time.logicalToCoordinate(b.i1 as Logical);
            const top = host.series.priceToCoordinate(b.resistance);
            const bottom = host.series.priceToCoordinate(b.support);
            if (x0 === null || x1 === null || top === null || bottom === null) continue;
            context.globalAlpha = b.opacity;
            const rect = [(x0 - half) * hr, top * vr, (x1 - x0 + 2 * half) * hr, (bottom - top) * vr] as const;
            context.fillRect(...rect);
            context.globalAlpha = b.borderOpacity;
            context.strokeRect(...rect);
          }
          context.globalAlpha = 1;
        });
      },
    };
    this.views = [{ zOrder: () => "bottom", renderer: () => renderer }];
  }

  attached(param: SeriesAttachedParameter<Time>) {
    this.host = param;
  }

  detached() {
    this.host = null;
  }

  paneViews() {
    return this.views;
  }
}

export interface EventLabelSpec {
  i: number;
  kind: string;
  high: number;
  low: number;
  above: boolean;     // nhãn phía trên nến (AR, SOS, UTAD), còn lại phía dưới
  current: boolean;   // thuộc cấu trúc hiện tại
  status: "potential" | "confirmed" | "rejected";
}

const OLD_EVENT_ALPHA = 0.55;
const REJECTED_EVENT_ALPHA = 0.3;
const TEXT_H = 14;

/** Nhãn sự kiện Wyckoff: tam giác chỉ vào nến + tên. Nhãn gần nhau được xếp tầng, không đè nhau và không
 *  bị cắt ở mép. Nhìn rộng hơn `denseBars` nến thì sự kiện của cấu trúc cũ chỉ còn tam giác.
 *  Đã xác nhận: tam giác đặc. Tiềm năng: tam giác rỗng, tên có "?". Bị bác bỏ: mờ, gạch ngang tên. */
export class EventLabels implements ISeriesPrimitive<Time> {
  private host: SeriesAttachedParameter<Time> | null = null;
  private readonly views: IPrimitivePaneView[];

  constructor(events: EventLabelSpec[], color: string, font: string, denseBars: number) {
    // Cấu trúc hiện tại đặt trước để được vị trí sát nến nhất
    const ordered = [...events].sort((a, b) => Number(b.current) - Number(a.current));
    const renderer: IPrimitivePaneRenderer = {
      draw: (target) => {
        const host = this.host;
        const time = host?.chart.timeScale();
        const visible = time?.getVisibleLogicalRange();
        if (!host || !time || !visible) return;
        const dense = visible.to - visible.from > denseBars;
        target.useMediaCoordinateSpace(({ context, mediaSize }) => {
          context.font = font;
          context.fillStyle = color;
          context.strokeStyle = color;
          context.textAlign = "center";
          const placed: { x: number; y: number; w: number }[] = [];
          for (const e of ordered) {
            if (e.i < visible.from - 1 || e.i > visible.to + 1) continue;
            const x = time.logicalToCoordinate(e.i as Logical);
            const y = host.series.priceToCoordinate(e.above ? e.high : e.low);
            if (x === null || y === null) continue;
            const dir = e.above ? -1 : 1;
            const tip = y + dir * 5;
            context.globalAlpha = e.status === "rejected" ? REJECTED_EVENT_ALPHA : e.current ? 1 : OLD_EVENT_ALPHA;
            context.beginPath();
            context.moveTo(x, tip);
            context.lineTo(x + 5, tip + dir * 8);
            context.lineTo(x - 5, tip + dir * 8);
            context.closePath();
            if (e.status === "potential") context.stroke();
            else context.fill();
            if (!e.current && dense) continue;

            const text = e.status === "potential" ? `${e.kind}?` : e.kind;
            const w = context.measureText(text).width;
            const tx = Math.min(Math.max(x, w / 2 + 2), mediaSize.width - w / 2 - 2);
            let ty = tip + dir * (e.above ? 12 : 21);
            while (placed.some((p) => Math.abs(p.x - tx) < (p.w + w) / 2 + 4 && Math.abs(p.y - ty) < TEXT_H)) ty += dir * TEXT_H;
            placed.push({ x: tx, y: ty, w });
            context.fillText(text, tx, ty);
            if (e.status === "rejected") context.fillRect(tx - w / 2, ty - 4, w, 1);
          }
          context.globalAlpha = 1;
        });
      },
    };
    this.views = [{ renderer: () => renderer }];
  }

  attached(param: SeriesAttachedParameter<Time>) {
    this.host = param;
  }

  detached() {
    this.host = null;
  }

  paneViews() {
    return this.views;
  }
}

/** Chữ cố định ở góc trên bên trái pane chứa series (vd. "Khối lượng"). */
export class PaneLabel implements ISeriesPrimitive<Time> {
  private readonly views: IPrimitivePaneView[];

  constructor(text: string, color: string, font: string) {
    const renderer: IPrimitivePaneRenderer = {
      draw: (target) => {
        target.useMediaCoordinateSpace(({ context }) => {
          context.font = font;
          context.fillStyle = color;
          context.fillText(text, 6, 16);
        });
      },
    };
    this.views = [{ zOrder: () => "top", renderer: () => renderer }];
  }

  paneViews() {
    return this.views;
  }
}
