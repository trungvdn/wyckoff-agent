"use client";

// Kết quả lọc: bảng từ 640px trở lên, thẻ trên điện thoại. Chỉ mô tả trạng thái, không xếp hạng.
import Link from "next/link";
import { cx } from "@/components/ui/Card";
import { fmtDate, fmtDateShort, fmtPct, fmtPrice, fmtRatio } from "@/lib/format";
import { symbolHref } from "@/lib/market";
import type { SortKey } from "@/lib/screener";
import type { ScanRow } from "@/lib/types";

const vn1 = new Intl.NumberFormat("vi-VN", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
export const fmtValue = (x: number) => `${vn1.format(x)} tỷ`;
const tone = (x: number | null) => (x == null ? "text-muted" : x > 0 ? "text-pos" : x < 0 ? "text-neg" : "text-muted");

function lastEvent(r: ScanRow): string {
  const e = r.events[0];
  return e ? `${e.kind}${e.status === "confirmed" ? "" : "?"} ${fmtDateShort(e.date)}` : "—";
}

function invalidateText(r: ScanRow) {
  if (r.invalidate_pct == null) return <span className="text-muted">—</span>;
  if (r.invalidate_breached) return <span className="text-event">đã thủng</span>;
  return <span className="text-muted">{fmtPct(r.invalidate_pct)}</span>;
}

function phaseLine(r: ScanRow) {
  return r.phase_since && r.phase && "ABCDE".includes(r.phase) ? `${r.phase_title} · từ ${fmtDateShort(r.phase_since)}` : r.phase_title;
}

function Stale({ r, asOf }: { r: ScanRow; asOf: string }) {
  return r.as_of < asOf ? <div className="text-xs text-event">dữ liệu đến {fmtDate(r.as_of)}</div> : null;
}

type Col = { key: SortKey | null; label: string; right?: boolean };
const COLS: Col[] = [
  { key: "symbol", label: "Mã" },
  { key: "phase_age", label: "Giai đoạn · Pha" },
  { key: "confidence_rank", label: "Tin cậy" },
  { key: null, label: "Sự kiện gần nhất" },
  { key: "confirm_pct", label: "Tới xác nhận", right: true },
  { key: "invalidate_pct", label: "Tới vô hiệu", right: true },
  { key: "rs60", label: "RS 60 phiên", right: true },
  { key: "sma_fast_pct", label: "So SMA50", right: true },
  { key: "value20", label: "GTGD TB20", right: true },
];

export function ResultsTable({ rows, asOf, sort, onSort, smaLabel }: {
  rows: ScanRow[];
  asOf: string;
  sort: { key: SortKey; dir: 1 | -1 };
  onSort: (key: SortKey) => void;
  smaLabel: string;
}) {
  const TD = "border-b border-line px-3 py-2.5 align-top";
  return (
    <div className="relative overflow-x-auto max-sm:hidden">
      <table className="w-full min-w-[980px] border-collapse text-[13px]">
        <thead>
          <tr className="text-left text-muted">
            {COLS.map((c, i) => {
              const active = c.key === sort.key;
              const label = c.key === "sma_fast_pct" ? smaLabel : c.label;
              return (
                <th
                  key={c.label}
                  scope="col"
                  aria-sort={active ? (sort.dir === 1 ? "ascending" : "descending") : undefined}
                  className={cx("border-y border-line px-3 py-1 font-medium whitespace-nowrap", c.right && "text-right", i === 0 && "pl-5", i === COLS.length - 1 && "pr-5")}
                >
                  {c.key ? (
                    <button
                      type="button"
                      onClick={() => onSort(c.key as SortKey)}
                      className={cx("h-8 cursor-pointer bg-transparent font-[inherit] hover:text-fg", active ? "font-semibold text-fg" : "text-muted")}
                    >
                      {label}{active ? (sort.dir === 1 ? " ↑" : " ↓") : ""}
                    </button>
                  ) : label}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.symbol} className="hover:bg-raised/40">
              <th scope="row" className={cx(TD, "pl-5 text-left font-normal")}>
                <Link href={symbolHref(r.symbol)} className="font-mono text-sm font-semibold text-fg hover:text-pos-hover">{r.symbol}</Link>
                {r.held && <span className="ml-1.5 rounded bg-raised px-1.5 py-0.5 text-2xs text-fg-2">đang giữ</span>}
                <div className="font-mono text-xs text-muted">{fmtPrice(r.close)}</div>
                <Stale r={r} asOf={asOf} />
              </th>
              <td className={TD}><div>{r.stage}</div><div className="text-muted">{phaseLine(r)}</div></td>
              <td className={cx(TD, r.confidence_rank ? "text-fg" : "text-muted")}>{r.confidence_rank ? r.confidence : "—"}</td>
              <td className={cx(TD, "whitespace-nowrap")}>{lastEvent(r)}</td>
              <td className={cx(TD, "text-right font-mono")}>{r.confirm_pct == null ? <span className="text-muted">—</span> : fmtPct(r.confirm_pct)}</td>
              <td className={cx(TD, "text-right font-mono")}>{invalidateText(r)}</td>
              <td className={cx(TD, "text-right font-mono", tone(r.rs60))}>{fmtPct(r.rs60)}</td>
              <td className={cx(TD, "text-right font-mono", tone(r.sma_fast_pct))}>{fmtPct(r.sma_fast_pct)}</td>
              <td className={cx(TD, "pr-5 text-right font-mono whitespace-nowrap")}>
                <div>{fmtValue(r.value20)}</div>
                <div className="text-xs text-muted">KL ×{fmtRatio(r.vol_ratio)}</div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ResultCards({ rows, asOf }: { rows: ScanRow[]; asOf: string }) {
  return (
    <ul className="m-0 flex list-none flex-col gap-2.5 p-0 sm:hidden">
      {rows.map((r) => (
        <li key={r.symbol} className="flex flex-col gap-1.5 rounded-xl border border-line bg-sunken px-3.5 py-3 text-sm">
          <div className="flex items-baseline gap-2">
            <Link href={symbolHref(r.symbol)} className="font-mono text-[15px] font-semibold text-fg">{r.symbol}</Link>
            <span className="font-mono text-muted">{fmtPrice(r.close)}</span>
            {r.held && <span className="rounded bg-raised px-1.5 py-0.5 text-2xs text-fg-2">đang giữ</span>}
            <span className="ml-auto font-mono">{fmtValue(r.value20)}</span>
          </div>
          <div>{r.stage} <span className="text-muted">· {r.phase_title}</span></div>
          <Stale r={r} asOf={asOf} />
          <div className="grid grid-cols-3 gap-1 text-xs">
            <div><div className="text-muted">Sự kiện</div><div>{lastEvent(r)}</div></div>
            <div><div className="text-muted">Tới xác nhận</div><div className="font-mono">{fmtPct(r.confirm_pct)}</div></div>
            <div><div className="text-muted">RS 60</div><div className={cx("font-mono", tone(r.rs60))}>{fmtPct(r.rs60)}</div></div>
          </div>
        </li>
      ))}
    </ul>
  );
}
