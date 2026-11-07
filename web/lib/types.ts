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
  ema_fast: number | null; // EMA ngắn, chu kỳ trong ema_periods
  ema_slow: number | null; // EMA dài
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
  kind: "up" | "down" | "up_potential" | "down_potential" | "range" | "accumulation" | "accumulation_developing" | "accumulation_potential" | "reaccumulation" | "reaccumulation_developing" | "reaccumulation_potential" | "distribution" | "distribution_developing" | "distribution_potential" | "none";
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
  revision_status: RevisionStatus | "developing" | null; // mức chắc chắn của xu hướng hiện tại theo dữ liệu về sau
  trend_conditions: { key: string; label: string; met: boolean; detail: string }[]; // điều kiện của Markup / Markdown hiện tại
  trend_supporting: string[]; // sự kiện hỗ trợ: SOW, LPSY hoặc SOS, LPS; không bắt buộc
  trend_state: string | null; // Markup: Early, Established, Extended, Weakening; không phải pha Wyckoff
  accumulation: {
    level: "potential" | "developing" | "confirmed" | "rejected";
    structure_type: string;
    label: string | null;
    since: string;
    reason: string;
    conditions: { key: string; label: string; met: boolean; detail: string }[];
    supporting: string[]; // sự kiện làm bằng chứng, không bắt buộc
    leaning: string | null; // range sau Markup: nghiêng về Re-accumulation hay Distribution
  } | null; // mức Accumulation / Re-accumulation của range hiện tại
  distribution: StageInfo["accumulation"]; // mức Distribution của range hiện tại, xét song song với Re-accumulation
  market: { state: string | null; structure: string | null; leaning: string | null }; // Market State tách khỏi Market Structure
  evidence: { met: number; total: number; level: "cao" | "trung bình" | "thấp" } | null; // độ đầy đủ của bằng chứng, không phải xác suất
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
  ema_periods: [number, number];
  ema_crosses: { i: number; up: boolean }[]; // phiên EMA ngắn cắt EMA dài
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

// Trang thị trường (wyckoff/market.py: market_overview)
export type TrendKind = "uptrend" | "downtrend" | "sideways";

export interface TrendCondition {
  id: "close_fast" | "fast_slow" | "slope";
  label: string;
  op: ">" | "<";
  met: boolean;
  value: number;
  threshold: number;
  gap_pct: number; // % cần đi thêm để value chạm threshold
  gap_points: number;
  slope_pct: number | null; // chỉ có ở điều kiện "slope"
}

export interface MarketBar {
  t: string;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
  vma: number | null;
  ema_fast: number | null; // chỉ để vẽ
  ema_slow: number | null; // chỉ để vẽ
  sma_fast: number | null;
  sma_slow: number | null;
}

export interface MarketOverview {
  symbol: string;
  as_of: string;
  close: number;
  change: number | null;
  change_pct: number | null;
  trend: {
    kind: TrendKind | null; // null: chưa đủ lịch sử
    since: string | null;
    sessions: number | null;
    sma_fast: number | null;
    sma_slow: number | null;
    required_bars: number;
  };
  conditions: { up: TrendCondition[]; down: TrendCondition[] } | null;
  returns: { window: number; pct: number | null; from_close: number | null; from_date: string | null }[];
  drawdown: { pct: number; peak: number; peak_date: string; sessions_since: number; lookback: number };
  sma_periods: [number, number];
  ema_periods: [number, number];
  volume_ma_period: number;
  bars: MarketBar[];
  trend_segments: { kind: TrendKind; i0: number; i1: number }[];
  notices: string[];
}

// Danh mục (wyckoff/portfolio.py). Giá: nghìn đồng; giá trị: đồng.
export type LevelKind = "support" | "resistance" | "confirm" | "invalidate";

export interface LevelRef {
  kind: LevelKind;
  price: number;
  pct: number;
  breached: boolean;
}

export type HoldingChange =
  | { kind: "stage" | "phase"; from: string; to: string }
  | { kind: "level"; level: LevelKind; price: number; direction: "below" | "above"; close: number; prev_close: number };

export interface AlertPreview {
  text: string;
  as_of: string | null;
  enabled_count: number;
  muted_count: number;
  muted: string[];
  configured: boolean;
}

interface HoldingBase {
  symbol: string;
  alerts_enabled: boolean;
  quantity: number;
  cost: number;
  bought_on: string;
  cost_value: number;
  changes: HoldingChange[] | null; // null: không so được với phiên trước
  rules: RuleItem[];
  exit: { profit: ExitGroup; loss: ExitGroup };
  attention: "loss" | "profit" | "near" | null;
}

export interface HoldingOk extends HoldingBase {
  error: null;
  as_of: string;
  price: number;
  prev_close: number;
  day_pct: number;
  day_value: number;
  value: number;
  pl: number;
  pl_pct: number;
  stage: string;
  phase: string;
  below: LevelRef | null;
  above: LevelRef | null;
}

export interface HoldingError extends HoldingBase {
  error: string;
}

export type HoldingRow = HoldingOk | HoldingError;

export interface Portfolio {
  as_of: string | null;
  summary: { count: number; value: number; cost: number; pl: number; pl_pct: number | null; day: number; day_pct: number | null; rules_total: number; rules_met: number; rules_fresh: number; symbols_with_rules: number; symbols_profit: number; symbols_loss: number; symbols_near: number };
  near_pct: number;
  rows: HoldingRow[];
  rule_catalog: RuleCatalogGroup[];
  notices: string[];
  warnings: string[];
}

export interface HoldingFields {
  quantity: number;
  cost: number;
  bought_on: string;
}

// Quy tắc bán (wyckoff/portfolio.py). Hệ thống chỉ báo đạt hay chưa.
export interface ExitGroup {
  total: number;
  met: number;
  ready: boolean; // đạt toàn bộ quy tắc của nhóm, hoặc có quy tắc "đạt là đủ" đã đạt
  by_sufficient: boolean; // đủ điều kiện nhờ quy tắc "đạt là đủ"
  has_sufficient: boolean;
  fresh: boolean; // vừa đủ điều kiện ở phiên cuối
  near: boolean; // chưa đủ, nhưng mọi quy tắc còn lại đều gần đạt, hoặc có quy tắc "đạt là đủ" gần đạt
}

export interface RuleItem {
  id: number;
  symbol: string;
  kind: string;
  value: number | null;
  side: "profit" | "loss"; // chốt lãi hay chốt lỗ
  sufficient: boolean; // "đạt là đủ": chỉ cần quy tắc này đạt là cả nhóm đủ điều kiện
  near: boolean; // gần đạt
  label: string;
  now: number | string | null;
  now_type: "pct" | "price" | "text";
  threshold: number | null;
  threshold_text: string | null;
  reference: number | null; // giá trị đường trung bình khi quy tắc có mức % so với đường
  met: boolean;
  fresh: boolean; // vừa đạt ở phiên cuối
  since: string | null;
  sessions: number | null;
  gap_pct: number | null;
  note: string | null;
  error: string | null;
}

export interface RuleCatalogGroup {
  group: string;
  kinds: { kind: string; label: string; value_label?: string | null; default_value?: number; value_hint?: string; line?: string; fixed_side?: "profit" | "loss" }[];
}
