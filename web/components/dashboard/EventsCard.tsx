import { Card, CardHeader, Eyebrow, cx } from "@/components/ui/Card";
import { fmtDate, fmtDateShort, fmtRatio } from "@/lib/format";
import type { RevisionChange, WyckoffEvent } from "@/lib/types";

const STATUS_LABEL: Record<RevisionChange["status"], string> = { potential: "Tiềm năng", developing: "Đang hình thành", confirmed: "Xác nhận", rejected: "Bác bỏ" };
const STATUS_STYLE: Record<RevisionChange["status"], string> = { potential: "text-event", developing: "text-event", confirmed: "text-pos", rejected: "text-neg" };

function StatusTag({ status }: { status: RevisionChange["status"] }) {
  return <span className={cx("font-mono text-xs whitespace-nowrap", STATUS_STYLE[status])}>{STATUS_LABEL[status]}</span>;
}

/** Sự kiện của cấu trúc hiện tại, mỗi dòng kèm trạng thái và bằng chứng định lượng; kèm các lần đánh giá lại gần nhất. */
export function EventsCard({ events, changes }: { events: WyckoffEvent[]; changes: RevisionChange[] }) {
  return (
    <Card labelledBy="events-h" className="flex-1">
      <CardHeader>
        <Eyebrow id="events-h">Sự kiện đã nhận diện</Eyebrow>
        {events.length > 0 && <span className="font-mono text-xs text-muted">{events.length} sự kiện</span>}
      </CardHeader>
      <ol className="m-0 flex list-none flex-col p-0">
        {events.length === 0 && (
          <li className="border-t border-line py-3 text-[13px] text-muted">Chưa có sự kiện nào thuộc cấu trúc hiện tại.</li>
        )}
        {events.map((e) => (
          <li key={e.id} className={cx("grid grid-cols-[64px_minmax(0,1fr)] gap-3 border-t border-line py-[11px]", e.status === "rejected" && "opacity-60")}>
            <span className="font-mono text-[13px] font-semibold wrap-anywhere text-event">{e.kind}</span>
            <div className="flex min-w-0 flex-col gap-1">
              <div className="flex justify-between gap-2">
                <span className="text-fg">{e.text}</span>
                <span className="font-mono text-xs whitespace-nowrap text-muted">{fmtDate(e.date)}</span>
              </div>
              <span className="font-mono text-xs text-muted">
                <StatusTag status={e.status} /> · KL {fmtRatio(e.vol_ratio)}× TB20 · biên độ {fmtRatio(e.spread_atr)}× ATR · đóng cửa {fmtRatio(e.close_pos)}
                {e.confirmed_date && e.confirmed_date !== e.date && ` · xác nhận ${fmtDateShort(e.confirmed_date)}`}
              </span>
            </div>
          </li>
        ))}
      </ol>
      {changes.length > 0 && (
        <details className="border-t border-line pt-3">
          <summary className="flex min-h-8 cursor-pointer items-center text-[13px] text-muted hover:text-fg">Đánh giá lại gần đây</summary>
          <ul className="mt-2 flex list-none flex-col gap-2 p-0 text-[13px] text-fg-2">
            {changes.map((c) => (
              <li key={`${c.date}-${c.subject}-${c.status}`} className="flex flex-col gap-0.5">
                <span className="flex justify-between gap-2">
                  <span className="text-fg">{c.subject}</span>
                  <StatusTag status={c.status} />
                </span>
                <span className="text-muted">
                  {fmtDate(c.date)}{c.reason ? `: ${c.reason}` : ""}
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-2 mb-0 text-[13px] text-muted">Nhãn trên biểu đồ được sửa theo dữ liệu về sau. Backtest và điểm tin cậy không dùng các nhãn sửa lại này.</p>
        </details>
      )}
    </Card>
  );
}
