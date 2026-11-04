import { Card, Eyebrow, cx } from "@/components/ui/Card";
import { fmtDate, fmtPrice } from "@/lib/format";
import type { Confidence, PhaseInfo, StageInfo, StepStatus, TrendStrength } from "@/lib/types";

const PILL = "inline-flex h-[26px] items-center rounded-full border px-2.5 text-[13px] font-semibold whitespace-nowrap";

const CONFIDENCE_STYLE: Record<string, string> = {
  cao: "text-pos border-pos-dim",
  "trung bình": "text-event border-event-dim",
  thấp: "text-neg border-neg-dim",
};

const STEP_BAR: Record<StepStatus, string> = { done: "before:bg-pos-dim", current: "before:bg-pos", pending: "before:bg-pending" };
const STEP_SR: Record<StepStatus, string> = { done: " (đã qua)", current: "", pending: " (chưa tới)" };

function Steps({ steps }: { steps: PhaseInfo["steps"] }) {
  return (
    <ol aria-label="Tiến trình pha A đến E" className="mt-1 grid list-none grid-cols-5 gap-1 p-0">
      {steps.map((s) => (
        <li
          key={s.id}
          aria-current={s.status === "current" ? "step" : undefined}
          className={cx(
            "flex flex-col gap-1.5 font-mono text-xs before:h-2 before:rounded-[2px] before:content-['']",
            STEP_BAR[s.status],
            s.status === "current" ? "font-semibold text-pos" : "text-muted",
          )}
        >
          {s.status === "current" ? `${s.id} · hiện tại` : s.id}
          <span className="sr-only">{STEP_SR[s.status]}</span>
        </li>
      ))}
    </ol>
  );
}

function Factors({ factors }: { factors: Confidence["factors"] }) {
  if (!factors.length) return null;
  return (
    <details className="group">
      <summary className="flex min-h-8 cursor-pointer items-center text-[13px] text-muted hover:text-fg">Các yếu tố tin cậy</summary>
      <ul className="mt-2 flex list-none flex-col gap-1.5 p-0 text-[13px] text-fg-2">
        {factors.map((f) => (
          <li key={`${f.key}-${f.factor}`} className="grid grid-cols-[32px_minmax(0,1fr)] gap-2">
            <span className={cx("text-right font-mono", f.points > 0 ? "text-pos" : f.points < 0 ? "text-neg" : "text-muted")}>
              {f.points > 0 ? "+" : ""}
              {f.points}
            </span>
            <span>
              {f.factor} – {f.evidence}
            </span>
          </li>
        ))}
      </ul>
    </details>
  );
}

/** Trong range: giả thuyết giai đoạn và pha hiện tại. */
function RangeBody({ stage, phase: p, confidence: c }: { stage: StageInfo; phase: PhaseInfo; confidence: Confidence }) {
  const area = p.support != null && p.resistance != null ? ` Vùng ${fmtPrice(p.support)} – ${fmtPrice(p.resistance)}.` : "";
  return (
    <>
      <p className="m-0 text-[13px] text-muted">
        Chưa chốt{stage.prior_stage ? `, sau ${stage.prior_stage}` : ""}. Nhãn chỉ chốt khi range thoát.
      </p>
      <div className="flex flex-col gap-3 border-t border-line pt-3">
        <div className="flex items-end justify-between gap-3">
          <p className="m-0 flex-1 text-[22px] leading-tight font-bold tracking-tight">{p.title}</p>
          <div className="flex flex-col items-end gap-1">
            <span className={cx(PILL, CONFIDENCE_STYLE[c.level] ?? "border-line-strong text-muted")}>
              {c.score == null ? "Tin cậy: không áp dụng" : `Tin cậy ${c.level}`}
            </span>
            {c.score != null && (
              <span className="font-mono text-xs text-muted">
                điểm {c.score > 0 ? "+" : ""}
                {c.score} · thang quy tắc
              </span>
            )}
          </div>
        </div>
        <p className="m-0 leading-relaxed text-fg-2">
          {p.reason}.{p.since ? ` Từ ${fmtDate(p.since)}.` : ""}
          {area}
        </p>
        <Steps steps={p.steps} />
        <p className="m-0 text-[13px] text-muted">Pha và điểm tin cậy tính theo sơ đồ tích lũy; sơ đồ pha phân phối chưa có.</p>
        <Factors factors={c.factors} />
      </div>
    </>
  );
}

/** Thanh tỷ trọng khối lượng phiên tăng / phiên giảm. */
function VolumeBalance({ up, window }: { up: number; window: number }) {
  const down = 100 - up;
  const pct = (x: number) => `${Math.round(x)}%`;
  return (
    <div className="flex flex-col gap-1.5">
      <div
        role="img"
        aria-label={`Khối lượng ${window} phiên: phiên tăng ${pct(up)}, phiên giảm ${pct(down)}`}
        className="flex h-2 gap-0.5 overflow-hidden rounded-[2px]"
      >
        <span className="bg-pos" style={{ width: `${up}%` }} />
        <span className="bg-neg" style={{ width: `${down}%` }} />
      </div>
      <div aria-hidden="true" className="flex justify-between font-mono text-xs text-muted">
        <span>Phiên tăng {pct(up)}</span>
        <span>{window} phiên</span>
        <span>Phiên giảm {pct(down)}</span>
      </div>
    </div>
  );
}

/** Markup / Markdown: sức mạnh cung cầu và nhịp điều chỉnh, không hiện pha. */
function TrendBody({ strength: s }: { strength: TrendStrength }) {
  return (
    <>
      <p className="m-0 leading-relaxed text-fg-2">{s.correction.verdict}</p>
      {s.up_volume_pct != null && <VolumeBalance up={s.up_volume_pct} window={s.window} />}
      <ul className="m-0 flex list-none flex-col gap-2 p-0 text-[13px] text-fg-2">
        {s.signals
          .filter((sig) => sig.key !== "correction")
          .map((sig) => (
            <li key={sig.key} className="grid grid-cols-[72px_minmax(0,1fr)] gap-2">
              <span className="text-muted">{sig.title}</span>
              <span>{sig.text}</span>
            </li>
          ))}
      </ul>
      <p className="m-0 text-[13px] text-muted">Mô tả hiện trạng theo quy tắc, chưa kiểm định bằng backtest.</p>
    </>
  );
}

function strengthStyle(s: TrendStrength): string {
  if (s.level === "trung bình") return "text-event border-event-dim";
  const favorsBuyers = (s.side === "demand") === (s.level === "mạnh");
  return favorsBuyers ? "text-pos border-pos-dim" : "text-neg border-neg-dim";
}

/** Giai đoạn và pha trong một thẻ. Nội dung theo trạng thái: trong range có pha; Markup / Markdown có sức mạnh cung cầu. */
export function StagePhaseCard({ stage: s, phase, confidence }: { stage: StageInfo; phase: PhaseInfo; confidence: Confidence }) {
  const inRange = s.view === "range";
  return (
    <Card labelledBy="stage-h">
      <Eyebrow id="stage-h">Giai đoạn và pha</Eyebrow>
      <div className="flex items-start justify-between gap-3">
        <p className={cx("m-0 flex-1 leading-tight font-bold tracking-tight", inRange ? "text-lg sm:text-xl" : "text-[22px] sm:text-[26px]")}>
          {s.title}
        </p>
        {s.strength && <span className={cx(PILL, strengthStyle(s.strength))}>{s.strength.headline}</span>}
      </div>
      {!inRange && (
        <p className="m-0 font-mono text-xs text-muted">
          {s.structure_type}
          {s.since ? ` · từ ${fmtDate(s.since)}` : ""}
        </p>
      )}
      {inRange && <RangeBody stage={s} phase={phase} confidence={confidence} />}
      {s.view === "trend" && s.strength && <TrendBody strength={s.strength} />}
      {!inRange && <p className="m-0 text-[13px] text-muted">{s.reason}.</p>}
      {s.last_resolved && (
        <p className="m-0 text-[13px] text-muted">
          Range gần nhất đã chốt: TR#{s.last_resolved.range_id} là {s.last_resolved.label} ({fmtDate(s.last_resolved.date)}).
        </p>
      )}
    </Card>
  );
}
