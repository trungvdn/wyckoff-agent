import { Card, Eyebrow, cx } from "@/components/ui/Card";
import { fmtDate, fmtPrice } from "@/lib/format";
import type { Confidence, PhaseInfo, StepStatus } from "@/lib/types";

const LEVEL_STYLE: Record<string, string> = {
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

/** Pha hiện tại: tên pha, mức tin cậy theo quy tắc (không phải %), tiến trình A–E, các yếu tố. */
export function PhaseCard({ phase: p, confidence: c }: { phase: PhaseInfo; confidence: Confidence }) {
  const desc = p.phase
    ? `${p.reason}.${p.since ? ` Từ ${fmtDate(p.since)}.` : ""}${
        p.support != null && p.resistance != null ? ` Vùng ${fmtPrice(p.support)} – ${fmtPrice(p.resistance)}.` : ""
      }`
    : "Chưa nhận diện được trading range hay climax nào trong dữ liệu.";
  return (
    <Card labelledBy="phase-h">
      <Eyebrow id="phase-h">Pha hiện tại</Eyebrow>
      <div className="flex items-end justify-between gap-3">
        <p className="m-0 flex-1 text-[22px] leading-tight font-bold tracking-tight sm:text-[26px]">{p.title}</p>
        <div className="flex flex-col items-end gap-1">
          <span className={cx("inline-flex h-[26px] items-center rounded-full border px-2.5 text-[13px] font-semibold whitespace-nowrap", LEVEL_STYLE[c.level] ?? "border-line-strong text-muted")}>
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
      <p className="m-0 leading-relaxed text-fg-2">{desc}</p>
      <Steps steps={p.steps} />
      <p className="m-0 text-[13px] text-muted">Pha và điểm tin cậy tính theo sơ đồ tích lũy.</p>
      <Factors factors={c.factors} />
    </Card>
  );
}
