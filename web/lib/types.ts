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
  phase: string; // A-E hoặc "invalid"
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
}

export interface Level {
  id: string;
  type: "confirm" | "invalidate";
  label: string;
  condition: string;
  price: number | null;
}

export interface Target {
  columns: number;
  box: number;
  reversal: number;
  count_from: string;
  count_to: string;
  count_to_event: string | null;
  base_low: number;
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
  phase: PhaseInfo;
  confidence: Confidence;
  events: WyckoffEvent[];
  levels: Level[];
  target: Target | null;
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
