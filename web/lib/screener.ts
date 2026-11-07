// Điều kiện lọc của trang Lọc cổ phiếu. Lọc chạy trên trình duyệt với kết quả quét đã lưu (~320 dòng).
import { fmtPct } from "./format";
import type { ScanRow, StageGroup, StageStatus } from "./types";

export const STAGE_OPTIONS: { id: StageGroup; label: string }[] = [
  { id: "Accumulation", label: "Accumulation" },
  { id: "Re-accumulation", label: "Re-accumulation" },
  { id: "Markup", label: "Markup" },
  { id: "Distribution", label: "Distribution" },
  { id: "Re-distribution", label: "Re-distribution" },
  { id: "Markdown", label: "Markdown" },
  { id: "unclear", label: "Chưa rõ" },
];

export const STATUS_OPTIONS: { id: StageStatus; label: string }[] = [
  { id: "confirmed", label: "Đã xác nhận" },
  { id: "developing", label: "Đang hình thành" },
  { id: "potential", label: "Tiềm năng" },
];

export const PHASE_OPTIONS: { id: string; label: string }[] = [
  { id: "A", label: "A" },
  { id: "B", label: "B" },
  { id: "C", label: "C" },
  { id: "D", label: "D" },
  { id: "E", label: "E" },
  { id: "invalid", label: "Vô hiệu" },
];

export const CONFIDENCE_OPTIONS = [
  { id: 0, label: "Bất kỳ" },
  { id: 2, label: "Trung bình" },
  { id: 3, label: "Cao" },
];

export const EVENT_OPTIONS = ["SOS", "Spring", "LPS", "UTAD", "Test", "ST", "AR", "SC"];
export const ANY_EVENT = "*";

export type Op = ">=" | "<=";
export type NumKey = "confirm_pct" | "invalidate_gap" | "sma_fast_pct" | "rs60" | "value20" | "close" | "vol_ratio";

export interface NumField {
  key: NumKey;
  label: string;
  defaultOp: Op;
  unit: string; // dùng trong thẻ điều kiện
  hint: string; // đơn vị hiện trong ô nhập
  group: "price" | "liquidity";
}

export const NUM_FIELDS: NumField[] = [
  { key: "confirm_pct", label: "Tới mức xác nhận", defaultOp: "<=", unit: "%", hint: "%", group: "price" },
  { key: "invalidate_gap", label: "Cách mức vô hiệu", defaultOp: ">=", unit: "%", hint: "%", group: "price" },
  { key: "sma_fast_pct", label: "So với SMA50", defaultOp: ">=", unit: "%", hint: "%", group: "price" },
  { key: "rs60", label: "RS 60 phiên", defaultOp: ">=", unit: "%", hint: "%", group: "price" },
  { key: "value20", label: "GTGD TB20", defaultOp: ">=", unit: " tỷ", hint: "tỷ", group: "liquidity" },
  { key: "close", label: "Giá", defaultOp: ">=", unit: "", hint: "nghìn đ", group: "liquidity" },
  { key: "vol_ratio", label: "KL phiên so TB20", defaultOp: ">=", unit: "×", hint: "lần", group: "liquidity" },
];

export interface Filters {
  stages: StageGroup[]; // rỗng: mọi giai đoạn
  statuses: StageStatus[]; // rỗng: mọi trạng thái
  phases: string[]; // rỗng: mọi pha
  minConfidence: number;
  event: string | null; // null: không lọc; "*": bất kỳ sự kiện
  eventWithin: number;
  phaseChangedWithin: number | null; // null: không lọc
  num: Partial<Record<NumKey, { op: Op; value: number }>>;
  excludeHeld: boolean;
}

export const EMPTY_FILTERS: Filters = {
  stages: [],
  statuses: [],
  phases: [],
  minConfidence: 0,
  event: null,
  eventWithin: 10,
  phaseChangedWithin: null,
  num: {},
  excludeHeld: false,
};

/** Bộ lọc đã lưu từ phiên bản cũ hoặc bị sửa tay: giữ phần hợp lệ, phần còn lại lấy mặc định. */
export function normalizeFilters(raw: unknown): Filters {
  const f = (raw && typeof raw === "object" ? raw : {}) as Partial<Filters>;
  const pick = <T,>(xs: unknown, allowed: readonly T[]) => (Array.isArray(xs) ? xs.filter((x): x is T => allowed.includes(x as T)) : []);
  const num: Filters["num"] = {};
  for (const field of NUM_FIELDS) {
    const c = f.num?.[field.key];
    if (c && (c.op === ">=" || c.op === "<=") && Number.isFinite(c.value)) num[field.key] = { op: c.op, value: c.value };
  }
  const posInt = (x: unknown, d: number) => (Number.isInteger(x) && (x as number) > 0 ? (x as number) : d);
  return {
    stages: pick(f.stages, STAGE_OPTIONS.map((o) => o.id)),
    statuses: pick(f.statuses, STATUS_OPTIONS.map((o) => o.id)),
    phases: pick(f.phases, PHASE_OPTIONS.map((o) => o.id)),
    minConfidence: [0, 1, 2, 3].includes(f.minConfidence as number) ? (f.minConfidence as number) : 0,
    event: f.event === ANY_EVENT || EVENT_OPTIONS.includes(f.event as string) ? (f.event as string) : null,
    eventWithin: posInt(f.eventWithin, 10),
    phaseChangedWithin: f.phaseChangedWithin == null ? null : posInt(f.phaseChangedWithin, 5),
    num,
    excludeHeld: Boolean(f.excludeHeld),
  };
}

/** Giá trị của một điều kiện số. "Cách mức vô hiệu": mức vô hiệu nằm dưới giá bao nhiêu %; đã thủng thì âm. */
export function numValue(row: ScanRow, key: NumKey): number | null {
  if (key === "invalidate_gap") return row.invalidate_pct == null ? null : -row.invalidate_pct;
  return row[key];
}

function matchNum(x: number | null, c: { op: Op; value: number }) {
  return x != null && (c.op === ">=" ? x >= c.value : x <= c.value);
}

export function matches(row: ScanRow, f: Filters): boolean {
  if (f.excludeHeld && row.held) return false;
  if (f.stages.length && !f.stages.includes(row.stage_group)) return false;
  if (f.statuses.length && (row.stage_status == null || !f.statuses.includes(row.stage_status))) return false;
  if (f.phases.length && (row.phase == null || !f.phases.includes(row.phase))) return false;
  if (f.minConfidence && row.confidence_rank < f.minConfidence) return false;
  if (f.event != null && !row.events.some((e) => e.ago <= f.eventWithin && (f.event === ANY_EVENT || e.kind === f.event))) return false;
  if (f.phaseChangedWithin != null && (row.phase_age == null || row.phase_age > f.phaseChangedWithin)) return false;
  for (const field of NUM_FIELDS) {
    const c = f.num[field.key];
    if (c && !matchNum(numValue(row, field.key), c)) return false;
  }
  return true;
}

const vnNum = (x: number) => new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 }).format(x);

export interface Chip {
  id: string;
  label: string;
  clear: (f: Filters) => Filters;
}

/** Các điều kiện đang dùng, mỗi điều kiện một thẻ có nút bỏ. */
export function activeChips(f: Filters): Chip[] {
  const out: Chip[] = [];
  if (f.stages.length)
    out.push({ id: "stages", label: f.stages.map((s) => STAGE_OPTIONS.find((o) => o.id === s)?.label ?? s).join(", "), clear: (x) => ({ ...x, stages: [] }) });
  if (f.statuses.length)
    out.push({ id: "statuses", label: f.statuses.map((s) => STATUS_OPTIONS.find((o) => o.id === s)?.label ?? s).join(", "), clear: (x) => ({ ...x, statuses: [] }) });
  if (f.phases.length)
    out.push({ id: "phases", label: `Pha ${f.phases.map((p) => (p === "invalid" ? "vô hiệu" : p)).join(", ")}`, clear: (x) => ({ ...x, phases: [] }) });
  if (f.minConfidence)
    out.push({ id: "conf", label: `Tin cậy ≥ ${CONFIDENCE_OPTIONS.find((o) => o.id === f.minConfidence)?.label.toLowerCase()}`, clear: (x) => ({ ...x, minConfidence: 0 }) });
  if (f.event != null)
    out.push({ id: "event", label: `${f.event === ANY_EVENT ? "Có sự kiện" : f.event} trong ${f.eventWithin} phiên`, clear: (x) => ({ ...x, event: null }) });
  if (f.phaseChangedWithin != null)
    out.push({ id: "phaseChanged", label: `Đổi pha trong ${f.phaseChangedWithin} phiên`, clear: (x) => ({ ...x, phaseChangedWithin: null }) });
  for (const field of NUM_FIELDS) {
    const c = f.num[field.key];
    if (!c) continue;
    const value = field.unit === "%" ? fmtPct(c.value) : `${vnNum(c.value)}${field.unit}`;
    out.push({ id: field.key, label: `${field.label} ${c.op === ">=" ? "≥" : "≤"} ${value}`, clear: (x) => ({ ...x, num: { ...x.num, [field.key]: undefined } }) });
  }
  if (f.excludeHeld) out.push({ id: "held", label: "Bỏ mã đang giữ", clear: (x) => ({ ...x, excludeHeld: false }) });
  return out;
}

export type SortKey = "symbol" | "value20" | "rs60" | "sma_fast_pct" | "confirm_pct" | "invalidate_pct" | "confidence_rank" | "phase_age";

export const SORT_OPTIONS: { key: SortKey; dir: 1 | -1; label: string }[] = [
  { key: "value20", dir: -1, label: "GTGD TB20 ↓" },
  { key: "rs60", dir: -1, label: "RS 60 phiên ↓" },
  { key: "sma_fast_pct", dir: -1, label: "So SMA50 ↓" },
  { key: "confirm_pct", dir: 1, label: "Tới xác nhận ↑" },
  { key: "phase_age", dir: 1, label: "Mới đổi pha trước" },
  { key: "symbol", dir: 1, label: "Mã A→Z" },
];

/** Sắp xếp; giá trị trống luôn ở cuối, bất kể chiều. */
export function sortRows(rows: ScanRow[], key: SortKey, dir: 1 | -1): ScanRow[] {
  return [...rows].sort((a, b) => {
    const x = a[key], y = b[key];
    if (x == null || y == null) return x == null ? (y == null ? 0 : 1) : -1;
    if (typeof x === "string") return dir * x.localeCompare(y as string);
    return dir * ((x as number) - (y as number)) || a.symbol.localeCompare(b.symbol);
  });
}
