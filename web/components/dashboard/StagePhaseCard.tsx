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

function Steps({ steps, label }: { steps: PhaseInfo["steps"]; label: string }) {
  return (
    <ol aria-label={label} className="mt-1 grid list-none grid-cols-5 gap-1 p-0">
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

/** Pha theo sơ đồ phân phối: chỉ ghi nhận, chưa có điểm tin cậy và mức giá. */
function DistributionPhase({ phase: d }: { phase: NonNullable<StageInfo["distribution_phase"]> }) {
  return (
    <div className="flex flex-col gap-3 border-t border-line pt-3">
      <div>
        <p className="m-0 text-[13px] text-muted">Nếu là phân phối</p>
        <p className="m-0 text-[22px] leading-tight font-bold tracking-tight">{d.title}</p>
      </div>
      <p className="m-0 leading-relaxed text-fg-2">
        {d.reason}.{d.since ? ` Từ ${fmtDate(d.since)}.` : ""}
      </p>
      <Steps steps={d.steps} label="Tiến trình pha phân phối A đến E" />
      <p className="m-0 text-[13px] text-muted">Chỉ ghi nhận, chưa có điểm tin cậy và mức xác nhận / vô hiệu.</p>
    </div>
  );
}

/** Trong range: giả thuyết giai đoạn và pha theo cả hai sơ đồ. */
function RangeBody({ stage, phase: p, confidence: c }: { stage: StageInfo; phase: PhaseInfo; confidence: Confidence }) {
  const area = p.support != null && p.resistance != null ? ` Vùng ${fmtPrice(p.support)} – ${fmtPrice(p.resistance)}.` : "";
  return (
    <>
      <p className="m-0 text-[13px] text-muted">
        Chưa chốt{stage.prior_stage ? `, sau ${stage.prior_stage}` : ""}. Nhãn chỉ chốt khi range thoát.
      </p>
      <div className="flex flex-col gap-3 border-t border-line pt-3">
        <div className="flex items-end justify-between gap-3">
          <div className="flex-1">
            <p className="m-0 text-[13px] text-muted">Nếu là tích lũy</p>
            <p className="m-0 text-[22px] leading-tight font-bold tracking-tight">{p.title}</p>
          </div>
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
        <Steps steps={p.steps} label="Tiến trình pha tích lũy A đến E" />
        <Factors factors={c.factors} />
      </div>
      {stage.distribution_phase && <DistributionPhase phase={stage.distribution_phase} />}
      {stage.note && <p className="m-0 border-l-2 border-event-dim pl-2.5 text-[13px] leading-relaxed text-fg-2">{stage.note}</p>}
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

/** Markup / Markdown: điều kiện đạt hay chưa, kèm sự kiện hỗ trợ và trạng thái vận động. */
function TrendConditions({ stage: s }: { stage: StageInfo }) {
  const met = s.trend_conditions.filter((c) => c.met).length;
  return (
    <div className="flex flex-col gap-2 border-t border-line pt-3">
      <p className="m-0 text-[13px] text-muted">
        Điều kiện {s.stage}: đạt {met}/{s.trend_conditions.length}
        {s.trend_state ? ` · ${s.trend_state}` : ""}
      </p>
      <ul className="m-0 flex list-none flex-col gap-2 p-0 text-[13px] text-fg-2">
        {s.trend_conditions.map((c) => (
          <li key={c.key} className="grid grid-cols-[40px_minmax(0,1fr)] gap-2">
            <span className={cx("font-mono", c.met ? "text-pos" : "text-muted")}>{c.met ? "Đạt" : "Chưa"}</span>
            <span>
              {c.label} – {c.detail}
            </span>
          </li>
        ))}
      </ul>
      {s.trend_supporting.length > 0 && (
        <p className="m-0 text-[13px] text-muted">Sự kiện hỗ trợ, không bắt buộc: {s.trend_supporting.join(", ")}.</p>
      )}
    </div>
  );
}

const ACC_LEVEL: Record<NonNullable<StageInfo["accumulation"]>["level"], string> = {
  potential: "Ứng viên",
  developing: "Đang hình thành",
  confirmed: "Đã xác nhận",
  rejected: "Đã bác bỏ",
};

/** Mức Accumulation của range hiện tại: bằng chứng theo cung, cầu và cấu trúc; sự kiện không bắt buộc. */
function AccumulationEvidence({ acc }: { acc: NonNullable<StageInfo["accumulation"]> }) {
  return (
    <details className="flex flex-col gap-2 border-t border-line pt-3">
      <summary className="flex min-h-8 cursor-pointer items-center text-[13px] text-muted hover:text-fg">
        {acc.structure_type === "Re-accumulation" ? "Re-accumulation" : "Accumulation"}: {ACC_LEVEL[acc.level]} · {acc.conditions.filter((c) => c.met).length}/{acc.conditions.length} bằng chứng
        {acc.leaning ? ` · nghiêng về ${acc.leaning}` : ""}
      </summary>
      <ul className="m-0 mt-2 flex list-none flex-col gap-2 p-0 text-[13px] text-fg-2">
        {acc.conditions.map((c) => (
          <li key={c.key} className="grid grid-cols-[40px_minmax(0,1fr)] gap-2">
            <span className={cx("font-mono", c.met ? "text-pos" : "text-muted")}>{c.met ? "Đạt" : "Chưa"}</span>
            <span>
              {c.label} – {c.detail}
            </span>
          </li>
        ))}
      </ul>
      {acc.supporting.length > 0 && <p className="mt-2 mb-0 text-[13px] text-muted">Sự kiện làm bằng chứng, không bắt buộc: {acc.supporting.join(", ")}.</p>}
    </details>
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
      {s.view === "trend" && s.trend_conditions.length > 0 && <TrendConditions stage={s} />}
      {!inRange && <p className="m-0 text-[13px] text-muted">{s.reason}.</p>}
      {(s.market.state || s.market.structure) && (
        <p className="m-0 font-mono text-xs text-muted">
          Market State: {s.market.state ?? "chưa xác định"}
          {s.market.structure ? ` · Cấu trúc: ${s.market.structure}` : ""}
        </p>
      )}
      {s.accumulation && <AccumulationEvidence acc={s.accumulation} />}
      {s.last_resolved && (
        <p className="m-0 text-[13px] text-muted">
          Range gần nhất: TR#{s.last_resolved.range_id} là {s.last_resolved.label} ({fmtDate(s.last_resolved.date)}).
        </p>
      )}
    </Card>
  );
}
