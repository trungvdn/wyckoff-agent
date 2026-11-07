"use client";

// Trang danh mục: tổng quan, thay đổi so với hôm qua, bảng các mã (thẻ trên điện thoại), form thêm / sửa.
// Mọi con số lấy từ API; giao diện chỉ định dạng và sắp xếp.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState, useTransition } from "react";
import { Banner } from "@/components/dashboard/Banner";
import { StatusPill } from "@/components/layout/Header";
import { SetStatus } from "@/components/layout/StatusContext";
import { Button } from "@/components/ui/Button";
import { Card, cx } from "@/components/ui/Card";
import { fmtDate, fmtInt, fmtMillion, fmtPct2, fmtPrice } from "@/lib/format";
import { symbolHref } from "@/lib/market";
import type { HoldingChange, HoldingOk, HoldingRow, LevelKind, LevelRef, Portfolio } from "@/lib/types";
import { HoldingDialog, type DialogValue } from "./HoldingDialog";

const signColor = (x: number | null | undefined) => (x == null || x === 0 ? "text-muted" : x < 0 ? "text-neg" : "text-pos");
const isOk = (r: HoldingRow): r is HoldingOk => r.error === null;

const LEVEL_NAME: Record<LevelKind, string> = { support: "hỗ trợ", resistance: "kháng cự", confirm: "mức xác nhận", invalidate: "mức vô hiệu" };

/** Tên mức trong bảng. Hỗ trợ nằm trên giá (hoặc kháng cự nằm dưới giá) nghĩa là giá đã ra khỏi range đó. */
function levelTitle(l: LevelRef, side: "below" | "above"): string {
  if (l.kind === "invalidate") return l.breached ? "Vô hiệu (đã thủng)" : "Vô hiệu";
  if (l.kind === "confirm") return "Xác nhận";
  if (l.kind === "support") return side === "above" ? "Hỗ trợ của range cũ" : "Hỗ trợ";
  return side === "below" ? "Kháng cự của range cũ" : "Kháng cự";
}

function LevelCell({ level, side }: { level: LevelRef | null; side: "below" | "above" }) {
  if (!level) return <><div className="text-muted">Chưa có mức</div><div className="font-mono">—</div></>;
  return (
    <>
      <div className={level.breached ? "text-event" : "text-muted"}>{levelTitle(level, side)}</div>
      <div className="font-mono tabular-nums">{fmtPrice(level.price)} · {fmtPct2(level.pct)}</div>
    </>
  );
}

function changeText(c: HoldingChange) {
  const num = (x: number) => <span className="font-mono tabular-nums">{fmtPrice(x)}</span>;
  if (c.kind !== "level") return <>{c.kind === "stage" ? "Giai đoạn" : "Pha"} đổi từ {c.from} sang {c.to}.</>;
  return <>Đóng cửa {num(c.close)}, {c.direction === "below" ? "xuống dưới" : "lên trên"} {LEVEL_NAME[c.level]} {num(c.price)} (hôm qua {num(c.prev_close)}).</>;
}

function SummaryTile({ title, value, note, color, noteMono }: { title: string; value: string; note: string; color?: string; noteMono?: boolean }) {
  return (
    <div className="min-w-0 rounded-xl border border-line bg-surface px-3.5 py-3 sm:px-5 sm:py-4">
      <div className="text-[13px] text-muted">{title}</div>
      <div className={cx("font-mono text-[22px] font-semibold tabular-nums sm:text-2xl", color)}>{value}</div>
      <div className={cx("text-xs", noteMono ? "font-mono tabular-nums" : "", color ?? "text-faint")}>{note}</div>
    </div>
  );
}

function Changes({ rows }: { rows: HoldingRow[] }) {
  const changed = rows.filter((r) => r.changes?.length);
  const compared = rows.filter((r) => r.changes !== null).length;
  return (
    <Card labelledBy="changes-h" className="gap-2.5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h2 id="changes-h" className="m-0 text-sm font-semibold">Thay đổi so với hôm qua</h2>
        <span className="text-[13px] text-muted">
          {changed.length} mã có thay đổi · {compared - changed.length} mã giữ nguyên
          {compared < rows.length && ` · ${rows.length - compared} mã chưa so được`}
        </span>
      </div>
      {changed.length > 0 && (
        <ul className="m-0 flex list-none flex-col gap-2 p-0">
          {changed.flatMap((r) => r.changes!.map((c, i) => (
            <li key={`${r.symbol}-${i}`} className="grid grid-cols-[56px_1fr] gap-2">
              <Link href={symbolHref(r.symbol)} className="font-mono font-semibold hover:text-pos-hover">{r.symbol}</Link>
              <span className="text-fg-2">{changeText(c)}</span>
            </li>
          )))}
        </ul>
      )}
    </Card>
  );
}

type SortKey = "symbol" | "day" | "pl";

function sortRows(rows: HoldingRow[], key: SortKey | null, desc: boolean): HoldingRow[] {
  if (!key) return rows; // thứ tự của server: mã có thay đổi trước, rồi theo giá trị
  const dir = desc ? -1 : 1;
  const num = (r: HoldingRow) => (isOk(r) ? (key === "day" ? r.day_pct : r.pl_pct) : null);
  return [...rows].sort((a, b) => {
    if (key === "symbol") return dir * a.symbol.localeCompare(b.symbol);
    const [x, y] = [num(a), num(b)];
    if (x === null || y === null) return x === y ? 0 : x === null ? 1 : -1; // mã lỗi luôn ở cuối
    return dir * (x - y);
  });
}

function MoreButton({ symbol, onClick }: { symbol: string; onClick: () => void }) {
  return (
    <button type="button" aria-label={`Sửa hoặc xóa ${symbol}`} onClick={onClick} className="inline-grid size-11 flex-none cursor-pointer place-items-center rounded-lg text-muted hover:bg-raised hover:text-fg">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="5" cy="12" r="1.8" /><circle cx="12" cy="12" r="1.8" /><circle cx="19" cy="12" r="1.8" /></svg>
    </button>
  );
}

const TH = "border-y border-line px-3 py-2 font-medium";
const TD = "border-b border-line px-3 py-2.5 align-top";

function HoldingsTable({ rows, onEdit }: { rows: HoldingRow[]; onEdit: (r: HoldingRow) => void }) {
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean } | null>(null);
  const sorted = useMemo(() => sortRows(rows, sort?.key ?? null, sort?.desc ?? false), [rows, sort]);

  function header(key: SortKey, label: string, right = false) {
    const active = sort?.key === key;
    return (
      <th scope="col" aria-sort={active ? (sort.desc ? "descending" : "ascending") : "none"} className={cx(TH, right && "text-right", key === "symbol" && "pl-5")}>
        <button
          type="button"
          onClick={() => setSort((s) => (s?.key === key ? { key, desc: !s.desc } : { key, desc: key !== "symbol" }))}
          className={cx("inline-flex cursor-pointer items-center gap-1 font-medium hover:text-fg", active && "text-fg")}
        >
          {label}
          <span aria-hidden="true" className="w-2.5">{active ? (sort.desc ? "↓" : "↑") : ""}</span>
        </button>
      </th>
    );
  }

  return (
    <div className="overflow-x-auto max-sm:hidden">
      <table className="w-full min-w-[940px] border-collapse text-[13px]">
        <thead>
          <tr className="text-left text-muted">
            {header("symbol", "Mã")}
            <th scope="col" className={cx(TH, "text-right")}>SL · Giá vốn</th>
            {header("day", "Giá · Trong phiên", true)}
            {header("pl", "Lãi/lỗ", true)}
            <th scope="col" className={TH}>Giai đoạn · Pha</th>
            <th scope="col" className={TH}>Mức dưới giá</th>
            <th scope="col" className={TH}>Mức trên giá</th>
            <th scope="col" className={cx(TH, "pr-5")}><span className="sr-only">Thao tác</span></th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr key={r.symbol}>
              <th scope="row" className={cx(TD, "pl-5 text-left font-normal")}>
                <Link href={symbolHref(r.symbol)} className="font-mono text-sm font-semibold hover:text-pos-hover">{r.symbol}</Link>
                <div className="text-xs text-faint">mua {fmtDate(r.bought_on)}</div>
              </th>
              <td className={cx(TD, "text-right font-mono tabular-nums")}>
                <div>{fmtInt(r.quantity)}</div>
                <div className="text-muted">{fmtPrice(r.cost)}</div>
              </td>
              {isOk(r) ? (
                <>
                  <td className={cx(TD, "text-right font-mono tabular-nums")}>
                    <div>{fmtPrice(r.price)}</div>
                    <div className={signColor(r.day_pct)}>{fmtPct2(r.day_pct)}</div>
                  </td>
                  <td className={cx(TD, "text-right font-mono tabular-nums", signColor(r.pl))}>
                    <div className="font-semibold">{fmtMillion(r.pl, true)}</div>
                    <div>{fmtPct2(r.pl_pct)}</div>
                  </td>
                  <td className={TD}>
                    <div>{r.stage}</div>
                    <div className="text-muted">{r.phase}</div>
                  </td>
                  <td className={TD}><LevelCell level={r.below} side="below" /></td>
                  <td className={TD}><LevelCell level={r.above} side="above" /></td>
                </>
              ) : (
                <td colSpan={5} className={cx(TD, "text-event")}>Không tải được dữ liệu: {r.error}</td>
              )}
              <td className="border-b border-line py-1 pr-5 pl-1 text-right align-middle"><MoreButton symbol={r.symbol} onClick={() => onEdit(r)} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function HoldingCards({ rows, onEdit }: { rows: HoldingRow[]; onEdit: (r: HoldingRow) => void }) {
  return (
    <div className="flex flex-col gap-3 sm:hidden">
      {rows.map((r) => (
        <article key={r.symbol} className="flex flex-col gap-1.5 rounded-xl border border-line bg-surface py-2 pr-1.5 pl-3.5">
          <div className="flex items-center justify-between gap-2">
            <Link href={symbolHref(r.symbol)} className="flex min-h-11 items-center font-mono text-base font-semibold">{r.symbol}</Link>
            <div className="flex items-center gap-1">
              {isOk(r) && <span className={cx("font-mono text-[13px] font-semibold tabular-nums", signColor(r.pl))}>{fmtMillion(r.pl, true)} · {fmtPct2(r.pl_pct)}</span>}
              <MoreButton symbol={r.symbol} onClick={() => onEdit(r)} />
            </div>
          </div>
          <div className="flex justify-between gap-2 pr-2 font-mono text-[13px] text-muted tabular-nums">
            <span>{fmtInt(r.quantity)} × {fmtPrice(r.cost)}</span>
            {isOk(r) && <span>{fmtPrice(r.price)} <span className={signColor(r.day_pct)}>{fmtPct2(r.day_pct)}</span></span>}
          </div>
          {isOk(r) ? (
            <>
              <div className="pr-2 text-fg-2">{r.stage} · {r.phase}</div>
              <div className="grid grid-cols-2 gap-2 pr-2 pb-1 text-[13px]">
                <div><LevelCell level={r.below} side="below" /></div>
                <div><LevelCell level={r.above} side="above" /></div>
              </div>
            </>
          ) : (
            <div className="pr-2 pb-1 text-event">Không tải được dữ liệu: {r.error}</div>
          )}
        </article>
      ))}
    </div>
  );
}

function PageBar({ showStatus, children }: { showStatus: boolean; children?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <h1 className="m-0 w-full text-lg font-semibold sm:w-auto">Danh mục nắm giữ</h1>
      {showStatus && <StatusPill />}
      {children}
    </div>
  );
}

export function PortfolioBarLoading() {
  return <PageBar showStatus />;
}

export function PortfolioView({ data }: { data: Portfolio }) {
  const router = useRouter();
  const [, startTransition] = useTransition();
  const [dialog, setDialog] = useState<{ value: DialogValue | null } | null>(null);
  const s = data.summary;

  const addButton = (label: string, className?: string) => (
    <Button onClick={() => setDialog({ value: null })} className={className}>{label}</Button>
  );
  const edit = (r: HoldingRow) => setDialog({
    value: { symbol: r.symbol, quantity: r.quantity, cost: r.cost, bought_on: r.bought_on, close: isOk(r) ? r.price : null },
  });
  const form = dialog && (
    <HoldingDialog
      key={dialog.value?.symbol ?? "new"}
      initial={dialog.value}
      onClose={() => setDialog(null)}
      onSaved={() => {
        setDialog(null);
        startTransition(() => router.refresh());
      }}
    />
  );

  if (data.rows.length === 0) {
    return (
      <>
        <SetStatus kind="ok" text="Chưa có mã" />
        <PageBar showStatus={false} />
        <Card className="items-center gap-3 py-16 text-center">
          <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="text-faint">
            <rect x="3" y="8" width="18" height="12" rx="2" />
            <path d="M9 8V6a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2" />
          </svg>
          <h2 className="m-0 text-lg font-semibold">Chưa có mã nào trong danh mục</h2>
          <p className="m-0 max-w-[460px] text-fg-2">Thêm mã, số lượng, giá vốn và ngày mua để theo dõi lãi/lỗ, giai đoạn, pha và khoảng cách tới các mức giá.</p>
          {addButton("Thêm mã đầu tiên", "mt-1")}
        </Card>
        {form}
      </>
    );
  }

  return (
    <>
      <SetStatus kind="ok" text={data.as_of ? `Dữ liệu đến ${fmtDate(data.as_of)}` : "Không tải được dữ liệu"} />
      <PageBar showStatus>{addButton("Thêm mã", "max-sm:ml-auto")}</PageBar>
      <Banner notices={data.notices} warnings={data.warnings} />
      <main className="flex flex-col gap-4 sm:gap-5">
        <section aria-label="Tổng quan danh mục" className="grid grid-cols-2 gap-3 sm:gap-5 wide:grid-cols-4">
          <SummaryTile title="Giá trị hiện tại" value={fmtMillion(s.value)} note={`${s.count} mã`} />
          <SummaryTile title="Tổng vốn" value={fmtMillion(s.cost)} note="theo giá vốn đã nhập" />
          <SummaryTile title="Lãi/lỗ tạm tính" value={fmtMillion(s.pl, true)} note={fmtPct2(s.pl_pct)} color={signColor(s.pl)} noteMono />
          <SummaryTile title="Thay đổi trong phiên" value={fmtMillion(s.day, true)} note={fmtPct2(s.day_pct)} color={signColor(s.day)} noteMono />
        </section>
        <Changes rows={data.rows} />
        <section aria-labelledby="holdings-h" className="flex flex-col gap-3 overflow-hidden sm:gap-0 sm:rounded-xl sm:border sm:border-line sm:bg-surface">
          <h2 id="holdings-h" className="m-0 text-sm font-semibold sm:px-5 sm:pt-4 sm:pb-3">Các mã đang giữ</h2>
          <HoldingsTable rows={data.rows} onEdit={edit} />
          <HoldingCards rows={data.rows} onEdit={edit} />
          <p className="m-0 text-xs text-faint sm:px-5 sm:pt-3 sm:pb-3.5">Lãi/lỗ chưa tính phí và thuế. Mức vô hiệu chỉ cho biết cấu trúc không còn hiệu lực, chưa phải tín hiệu bán đã kiểm chứng.</p>
        </section>
      </main>
      {form}
    </>
  );
}
