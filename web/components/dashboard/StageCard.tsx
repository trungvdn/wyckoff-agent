import { Card, Eyebrow } from "@/components/ui/Card";
import { fmtDate } from "@/lib/format";
import type { StageInfo } from "@/lib/types";

/** Giai đoạn Wyckoff và loại cấu trúc. Trong range chỉ hiện giả thuyết; nhãn chốt khi range thoát, không phải dự báo. */
export function StageCard({ stage: s }: { stage: StageInfo }) {
  return (
    <Card labelledBy="stage-h">
      <Eyebrow id="stage-h">Giai đoạn</Eyebrow>
      <p className="m-0 text-[22px] leading-tight font-bold tracking-tight sm:text-[26px]">{s.title}</p>
      <p className="m-0 font-mono text-xs text-muted">{s.structure_type}</p>
      {s.candidates.length > 0 && (
        <p className="m-0 leading-relaxed text-fg-2">
          Giả thuyết: <span className="font-semibold">{s.candidates.join(" hoặc ")}</span>. Nhãn chỉ chốt khi range thoát.
        </p>
      )}
      <p className="m-0 leading-relaxed text-fg-2">
        {s.reason}.{s.since ? ` Từ ${fmtDate(s.since)}.` : ""}
      </p>
      {s.last_resolved && (
        <p className="m-0 text-[13px] text-muted">
          Range gần nhất đã chốt: TR#{s.last_resolved.range_id} là {s.last_resolved.label} ({fmtDate(s.last_resolved.date)}).
        </p>
      )}
    </Card>
  );
}
