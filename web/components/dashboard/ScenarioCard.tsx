"use client";

import type { ReactNode } from "react";
import { Card, Eyebrow, cx } from "@/components/ui/Card";
import { fmtDate, fmtInt, fmtPrice } from "@/lib/format";
import type { Level, Target } from "@/lib/types";
import { useExplanation } from "./ExplanationContext";

function Block({ tone, title, children }: { tone: "confirm" | "invalid" | "target"; title: ReactNode; children: ReactNode }) {
  const color = { confirm: "text-pos", invalid: "text-neg", target: "text-event" }[tone];
  return (
    <div className="flex flex-col gap-1 border-t border-line py-3 first:border-t-0 first:pt-0">
      <span className={cx("text-[13px] font-semibold", color)}>{title}</span>
      {children}
    </div>
  );
}

function LevelList({ levels, narratives, empty }: { levels: Level[]; narratives: Map<string, string>; empty: string }) {
  if (!levels.length) return <span className="text-[13px] text-fg-2">{empty}</span>;
  return levels.map((lv) => (
    <div key={lv.id} className="flex flex-col gap-0.5">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-fg">{lv.label}</span>
        <span className="font-mono font-semibold whitespace-nowrap text-fg">{fmtPrice(lv.price)}</span>
      </div>
      <span className="font-mono text-xs wrap-anywhere text-muted">{lv.condition}</span>
      {narratives.has(lv.id) && <span className="text-[13px] text-fg-2">{narratives.get(lv.id)}</span>}
    </div>
  ));
}

function TargetBlock({ t }: { t: Target | null }) {
  return (
    <Block
      tone="target"
      title={
        <>
          Mục tiêu (Nhân–Quả · Point &amp; Figure)
          {t?.provisional && <span className="ml-2 rounded border border-line-strong px-1.5 text-2xs font-medium text-muted">tạm tính</span>}
        </>
      }
    >
      {t ? (
        <>
          <span className="font-mono text-lg font-semibold">
            {t.conservative === t.aggressive ? fmtPrice(t.conservative) : `${fmtPrice(t.conservative)} – ${fmtPrice(t.aggressive)}`}
          </span>
          <span className="font-mono text-xs wrap-anywhere text-muted">
            Đếm {fmtInt(t.columns)} cột từ {fmtDate(t.count_from)} đến {fmtDate(t.count_to)}
            {t.count_to_event && ` (${t.count_to_event})`} · ô {fmtPrice(t.box)} · đảo chiều {t.reversal} ô
          </span>
          <span className="text-[13px] text-fg-2">
            Thận trọng: từ đáy cấu trúc {fmtPrice(t.base_low)}. Tích cực: từ đường đếm {fmtPrice(t.count_line)}. Ước lượng, không phải dự báo.
          </span>
        </>
      ) : (
        <span className="text-[13px] text-fg-2">Chưa đủ điều kiện: cần trading range và pha C trở lên.</span>
      )}
    </Block>
  );
}

/** Điều kiện xác nhận / vô hiệu (mức giá do code tính, diễn giải do agent) và mục tiêu P&F. */
export function ScenarioCard({ levels, target }: { levels: Level[]; target: Target | null }) {
  const { state: ex } = useExplanation();
  const narratives = new Map<string, string>();
  if (ex.status === "ok") {
    for (const s of [...ex.data.confirmation_scenarios, ...ex.data.invalidation_scenarios]) narratives.set(s.level_id, s.narrative);
  }
  return (
    <Card labelledBy="scenario-h">
      <Eyebrow id="scenario-h">Kịch bản</Eyebrow>
      <div className="flex flex-col">
        <Block tone="confirm" title="Xác nhận">
          <LevelList levels={levels.filter((l) => l.type === "confirm")} narratives={narratives} empty="Không có mức xác nhận cho pha hiện tại." />
        </Block>
        <Block tone="invalid" title="Vô hiệu">
          <LevelList levels={levels.filter((l) => l.type === "invalidate")} narratives={narratives} empty="Không có mức vô hiệu cho pha hiện tại." />
        </Block>
        <TargetBlock t={target} />
      </div>
    </Card>
  );
}
