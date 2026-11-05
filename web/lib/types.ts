// Kiểu dữ liệu khớp với view model của FastAPI (wyckoff/web/viewmodel.py, wyckoff/web/app.py).

export type Timeframe = "1D" | "1W";

export interface Bar {
  t: string; // YYYY-MM-DD
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
  vr: number | null; // volume / TB20
  vma: number | null; // TB20 volume
}

export interface ChartEvent {
  kind: string;
  t: string;
  i: number; // vị trí trong `bars`
  price: number;
  above: boolean;
  current: boolean; // thuộc cấu trúc hiện tại
  status: RevisionStatus;
}

export type RevisionStatus = "potential" | "confirmed" | "rejected";

export interface RevisionChange {
  date: string;
  subject: string;
  status: RevisionStatus | "developing";
  reason: string;
}

export interface RangeBox {
  id: number;
  support: number;
  resistance: number;
  i0: number;
  i1: number;
  active: boolean;
  current: boolean;
  context: string;
}

export interface PhaseSegment {
  phase: string; // A-E, "invalid", hoặc "potential" (thoát xuống, chờ xác nhận)
  i0: number;
  i1: number;
}

export interface StageSegment {
  kind: "up" | "down" | "up_potential" | "down_potential" | "range" | "accumulation" | "accumulation_developing" | "none";
  label: string;
  i0: number;
  i1: number;
}

export type StepStatus = "done" | "current" | "pending";

export interface PhaseInfo {
  phase: string | null;
  title: string;
  steps: { id: string; status: StepStatus }[];
  since: string | null;
  reason: string;
  support: number | null;
  resistance: number | null;
  atr: number;
  range_context: string | null;
}

export interface StrengthSignal {
  key: string;
  title: string;
  text: string;
  points: number; // -1 | 0 | +1
}

export interface TrendStrength {
  side: "demand" | "supply";
  level: "mạnh" | "trung bình" | "yếu đi";
  score: number;
  headline: string;
  up_volume_pct: number | null; // tỷ trọng khối lượng phiên tăng
  window: number;
  signals: StrengthSignal[];
  correction: { active: boolean; quality: "light" | "normal" | "heavy" | null; verdict: string };
}

export interface StageInfo {
  view: "range" | "trend" | "transition"; // trong range: có pha; xu hướng: có sức mạnh cung cầu
  stage: string | null; // Markup | Markdown; null khi trong range hoặc chưa có xu hướng
  revision_status: RevisionStatus | null; // mức chắc chắn của xu hướng hiện tại theo dữ liệu về sau
  markdown_conditions: { key: string; label: string; met: boolean; detail: string }[]; // 5 điều kiện xác nhận Markdown
  markdown_supporting: string[]; // SOW, LPSY trong đoạn, chỉ là sự kiện hỗ trợ
  accumulation: {
    level: "potential" | "developing" | "confirmed" | "rejected";
    structure_type: string;
    label: string | null;
    since: string;
    reason: string;
    conditions: { key: string; label: string; met: boolean; detail: string }[];
    supporting: string[]; // sự kiện làm bằng chứng, không bắt buộc
  } | null; // mức Accumulation của range hiện tại
  structure_type: string;
  strength: TrendStrength | null;
  note: string | null; // lưu ý từ kết quả kiểm định khi có pha C trong range
  distribution_phase: {
    phase: string | null;
    title: string;
    steps: { id: string; status: StepStatus }[];
    since: string | null;
    reason: string;
    events: string[];
  } | null; // pha theo sơ đồ phân phối khi đang trong range, chỉ ghi nhận
  title: string;
  since: string | null;
  reason: string;
  prior_stage: string | null;
  candidates: string[]; // giả thuyết khi đang trong range, chưa chốt
  range_id: number | null;
  last_resolved: { range_id: number; label: string; date: string } | null;
}

export interface ConfidenceFactor {
  factor: string;
  points: number;
  evidence: string;
  key: string;
}

export interface Confidence {
  level: "thấp" | "trung bình" | "cao" | "không áp dụng";
  score: number | null;
  factors: ConfidenceFactor[];
}

export interface WyckoffEvent {
  id: string;
  kind: string;
  text: string;
  date: string;
  confirmed_date: string | null;
  close: number;
  vol_ratio: number | null;
  spread_atr: number | null;
  close_pos: number | null;
  status: RevisionStatus;
}

export interface Level {
  id: string;
  type: "confirm" | "invalidate";
  label: string;
  condition: string;
  price: number | null;
}

export interface Target {
  direction: "up" | "down";
  reached: boolean; // giá hiện tại đã đi qua mức thận trọng
  columns: number;
  box: number;
  reversal: number;
  count_from: string;
  count_to: string;
  count_to_event: string | null;
  base_low?: number;
  base_high?: number;
  count_line: number;
  conservative: number;
  aggressive: number;
  provisional: boolean;
}

export interface Analysis {
  symbol: string;
  timeframe: Timeframe;
  as_of: string;
  price_unit: string;
  notices: string[];
  warnings: string[];
  bars: Bar[]; // toàn bộ lịch sử đã phân tích
  view_from: number; // nến đầu tiên của khung nhìn mặc định
  chart_events: ChartEvent[];
  ranges: RangeBox[];
  phase_segments: PhaseSegment[];
  stage_segments: StageSegment[];
  revision_changes: RevisionChange[];
  stage: StageInfo;
  phase: PhaseInfo;
  confidence: Confidence;
  events: WyckoffEvent[];
  levels: Level[];
  target: Target | null;
  target_down: Target | null;
  market: { benchmark: string; trend: string; rs_change_60d_pct: number | null } | null;
}

export interface Scenario {
  level_id: string;
  narrative: string;
}

export interface Explanation {
  source: "llm" | "cache" | "template";
  model: string | null;
  summary: string;
  phase_assessment: string;
  context_assessment: string;
  market_assessment: string;
  confirmation_scenarios: Scenario[];
  invalidation_scenarios: Scenario[];
  risks: string[];
  confidence_explanation: string;
  errors: string[];
}

export interface AskResponse {
  answer: string;
  event_ids: string[];
  source: "llm" | "template";
  model: string | null;
  errors: string[];
}
