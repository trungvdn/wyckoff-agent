"use client";

// Quy tắc bán của một mã, tách chốt lãi và chốt lỗ: bảng trên máy tính, danh sách gọn trong thẻ trên điện thoại.
// Màu: đạt chốt lãi xanh, đạt chốt lỗ đỏ, gần đạt hổ phách. Luôn kèm chữ, không chỉ dựa vào màu.
import { cx } from "@/components/ui/Card";
import { fmtDate, fmtDateShort, fmtPct2, fmtPrice } from "@/lib/format";
import type { HoldingRow, RuleItem } from "@/lib/types";

export type Attention = HoldingRow["attention"];

export function attentionTint(a: Attention): string {
  return a === "loss" ? "bg-neg-soft" : a === "profit" ? "bg-pos-soft" : a === "near" ? "bg-event-soft" : "";
}

const ATTENTION_TEXT = { loss: "Đủ điều kiện chốt lỗ", profit: "Đủ điều kiện chốt lãi", near: "Gần đủ điều kiện chốt" };

function WarnIcon({ className, size = 14 }: { className?: string; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={cx("flex-none", className)}>
      <path d="M12 4 2.8 20h18.4Z" />
      <line x1="12" y1="10" x2="12" y2="14.5" />
      <line x1="12" y1="17.5" x2="12" y2="17.5" />
    </svg>
  );
}

function ReadyIcon({ className, size = 14 }: { className?: string; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" className={cx("flex-none", className)}>
      <path fillRule="evenodd" d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm5 7.4-6.2 7L7 12.7l1.4-1.4 2.3 2.3 4.8-5.5Z" />
    </svg>
  );
}

/** Biểu tượng cạnh mã: dấu tích khi đã đủ điều kiện chốt, tam giác cảnh báo khi chỉ mới gần đạt. */
export function AttentionIcon({ kind }: { kind: Attention }) {
  if (!kind) return null;
  const color = kind === "loss" ? "text-neg" : kind === "profit" ? "text-pos" : "text-event";
  return (
    <span title={ATTENTION_TEXT[kind]} className={cx("inline-flex", color)}>
      {kind === "near" ? <WarnIcon /> : <ReadyIcon />}
      <span className="sr-only">{ATTENTION_TEXT[kind]}</span>
    </span>
  );
}

/** "1/3 đạt"; chưa có quy tắc nào: "Chưa đặt". */
export function ruleCount(r: HoldingRow): { text: string; note: string; color: string } {
  const met = r.rules.filter((x) => x.met);
  if (!r.rules.length) return { text: "Chưa đặt", note: "", color: "text-muted" };
  const parts = [
    r.exit.profit.ready && "đủ điều kiện chốt lãi",
    r.exit.loss.ready && "đủ điều kiện chốt lỗ",
    r.exit.profit.near && "gần chốt lãi",
    r.exit.loss.near && "gần chốt lỗ",
  ].filter(Boolean);
  return { text: `${met.length}/${r.rules.length} đạt`, note: parts.join(", "), color: "text-fg" };
}

/** Nhãn nhỏ trong ô Quy tắc của mã. */
export function RuleBadges({ row }: { row: HoldingRow }) {
  const { profit, loss } = row.exit;
  const base = "inline-flex h-5 items-center gap-1 rounded-full px-2 text-xs font-semibold whitespace-nowrap";
  const nearBadge = cx(base, "border border-event text-event");
  return (
    <>
      {profit.ready && <span className={cx(base, "bg-pos text-on-pos")}><ReadyIcon size={12} />Chốt lãi</span>}
      {loss.ready && <span className={cx(base, "bg-neg text-[#2A0B0B]")}><ReadyIcon size={12} />Chốt lỗ</span>}
      {profit.near && <span className={nearBadge}><WarnIcon size={12} />Gần chốt lãi</span>}
      {loss.near && <span className={nearBadge}><WarnIcon size={12} />Gần chốt lỗ</span>}
    </>
  );
}

const CHIP = "inline-flex h-6 items-center gap-1 rounded-full border px-2.5 text-xs font-semibold whitespace-nowrap";

/** Quy tắc đã đạt chỉ mang màu chốt khi cả nhóm đều đạt; chưa đủ nhóm thì chỉ ghi "Đạt". */
function StatusChip({ rule, groupReady }: { rule: RuleItem; groupReady: boolean }) {
  if (rule.error || rule.note) return <span className={cx(CHIP, "border-line-strong text-muted")}>Chưa tính được</span>;
  if (rule.met) {
    const text = rule.fresh ? "Vừa đạt" : "Đạt";
    if (!groupReady) return <span className={cx(CHIP, "border-muted text-fg")}>{text}</span>;
    return (
      <span className={cx(CHIP, rule.side === "profit" ? "border-pos bg-pos text-on-pos" : "border-neg bg-neg text-[#2A0B0B]")}>
        <ReadyIcon size={13} />{text} {rule.side === "profit" ? "chốt lãi" : "chốt lỗ"}
      </span>
    );
  }
  if (rule.near) return <span className={cx(CHIP, "border-event text-event")}><WarnIcon size={13} />Gần đạt</span>;
  return <span className={cx(CHIP, "border-line-strong text-muted")}>Chưa đạt</span>;
}

/** Nền dòng của một quy tắc. */
function ruleTint(r: RuleItem, groupReady: boolean): string {
  if (r.met) return groupReady ? (r.side === "profit" ? "bg-pos-soft" : "bg-neg-soft") : "";
  return r.near ? "bg-event-soft" : "";
}

function SufficientTag() {
  return <span className="ml-2 inline-flex h-5 items-center rounded border border-line-strong px-1.5 text-xs font-medium whitespace-nowrap text-fg-2">Đạt là đủ</span>;
}

function groupStatus(g: HoldingRow["exit"]["profit"], title: string): { text: string; className: string } {
  if (!g.total) return { text: "chưa có quy tắc", className: "text-muted" };
  const count = `đạt ${g.met}/${g.total}`;
  if (g.ready) {
    const reason = g.by_sufficient && g.met < g.total ? " nhờ quy tắc đạt là đủ" : "";
    return { text: `${count} · ${g.fresh ? "vừa đủ" : "đủ"} điều kiện ${title.toLowerCase()}${reason}`, className: "font-semibold text-fg" };
  }
  if (g.near) return { text: `${count} · gần đủ điều kiện`, className: "font-semibold text-event" };
  const need = g.has_sufficient ? "cần đạt toàn bộ hoặc một quy tắc đạt là đủ" : "cần đạt toàn bộ";
  return { text: `${count} · ${need} để ${title.toLowerCase()}`, className: "text-muted" };
}

function nowText(r: RuleItem): string {
  if (r.now === null) return "—";
  if (r.now_type === "text") return String(r.now);
  return r.now_type === "pct" ? fmtPct2(r.now as number) : fmtPrice(r.now as number);
}

const thresholdText = (r: RuleItem) => r.threshold_text ?? (r.threshold !== null ? fmtPrice(r.threshold) : "—");

function sinceText(r: RuleItem): string {
  if (!r.since) return "—";
  return r.fresh ? fmtDate(r.since) : `${fmtDate(r.since)} · ${r.sessions} phiên`;
}

function MoreButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button type="button" aria-label={label} onClick={onClick} className="inline-grid size-11 flex-none cursor-pointer place-items-center rounded-lg text-muted hover:bg-raised hover:text-fg">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="5" cy="12" r="1.8" /><circle cx="12" cy="12" r="1.8" /><circle cx="19" cy="12" r="1.8" /></svg>
    </button>
  );
}

const GROUPS = [
  { side: "profit", title: "Chốt lãi", color: "text-pos" },
  { side: "loss", title: "Chốt lỗ", color: "text-neg" },
] as const;

const TH = "border-y border-line px-3 py-2 font-medium";
const TD = "border-b border-line px-3 py-1";

function rulesNote(nearPct: number) {
  return `Quy tắc do bạn đặt. Một nhóm đủ điều kiện chốt khi đạt toàn bộ quy tắc trong nhóm, hoặc khi một quy tắc "Đạt là đủ" đạt; quyết định bán thuộc về bạn. "Gần đạt": giá còn cách ngưỡng không quá ${String(nearPct).replace(".", ",")}%, hoặc giai đoạn đang ở mức tiềm năng. "Đạt từ": phiên đầu của chuỗi đạt liên tục đến nay, tính từ ngày mua.`;
}

/** Khối dưới bảng trên máy tính. */
export function RulesPanel({ row, nearPct, onAdd, onEdit }: { row: HoldingRow; nearPct: number; onAdd: () => void; onEdit: (r: RuleItem) => void }) {
  const met = row.rules.filter((x) => x.met).length;
  return (
    <section aria-labelledby="rules-h" className="overflow-hidden rounded-xl border border-line bg-surface max-sm:hidden">
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 px-5 py-3">
        <div className="flex flex-wrap items-baseline gap-x-2.5">
          <h2 id="rules-h" className="m-0 text-sm font-semibold">Quy tắc bán của <span className="font-mono">{row.symbol}</span></h2>
          {row.rules.length > 0 && <span className="text-[13px] text-muted">đạt {met}/{row.rules.length}</span>}
        </div>
        <button type="button" onClick={onAdd} className="h-11 cursor-pointer rounded-lg border border-line-strong px-3.5 font-semibold transition-colors hover:border-muted">
          Thêm quy tắc cho {row.symbol}
        </button>
      </div>
      {row.rules.length === 0 ? (
        <p className="m-0 border-t border-line px-5 py-7 text-center text-fg-2">Chưa đặt quy tắc nào cho {row.symbol}.</p>
      ) : (
        <div className="relative overflow-x-auto">{/* relative: giữ chữ sr-only trong vùng cuộn, không kéo giãn trang */}
          <table className="w-full min-w-[820px] border-collapse text-[13px]">
            <thead>
              <tr className="text-left text-muted">
                <th scope="col" className={cx(TH, "pl-5")}>Quy tắc</th>
                <th scope="col" className={TH}>Trạng thái</th>
                <th scope="col" className={cx(TH, "text-right")}>Hiện tại</th>
                <th scope="col" className={cx(TH, "text-right")}>Ngưỡng</th>
                <th scope="col" className={cx(TH, "text-right")}>Giá còn cách</th>
                <th scope="col" className={TH}>Đạt từ</th>
                <th scope="col" className={cx(TH, "pr-5")}><span className="sr-only">Thao tác</span></th>
              </tr>
            </thead>
            {GROUPS.map((g) => {
              const items = row.rules.filter((r) => r.side === g.side);
              const group = row.exit[g.side];
              const status = groupStatus(group, g.title);
              return (
                <tbody key={g.side}>
                  <tr>
                    <th scope="colgroup" colSpan={7} className={cx("border-b border-line bg-sunken px-5 py-1.5 text-left text-xs font-semibold tracking-[0.04em] uppercase", g.color)}>
                      {g.title}
                      <span className={cx("ml-2 font-normal tracking-normal normal-case", status.className)}>{status.text}</span>
                    </th>
                  </tr>
                  {items.map((r) => (
                    <tr key={r.id} className={ruleTint(r, group.ready)}>
                      <th scope="row" className={cx(TD, "pl-5 text-left font-normal")}>
                        {r.label}
                        {r.sufficient && <SufficientTag />}
                        {r.note && <div className="text-xs text-faint">{r.note}</div>}
                      </th>
                      <td className={TD}><StatusChip rule={r} groupReady={group.ready} /></td>
                      <td className={cx(TD, "text-right", r.now_type !== "text" && "font-mono tabular-nums")}>{nowText(r)}</td>
                      <td className={cx(TD, "text-right", !r.threshold_text && "font-mono tabular-nums")}>{thresholdText(r)}</td>
                      <td className={cx(TD, "text-right font-mono tabular-nums", r.near ? "font-semibold text-event" : "text-muted")}>{r.gap_pct !== null ? fmtPct2(r.gap_pct) : "—"}</td>
                      <td className={cx(TD, "text-muted")}>{sinceText(r)}</td>
                      <td className="border-b border-line py-0 pr-5 pl-1 text-right"><MoreButton label={`Sửa hoặc xóa quy tắc ${r.label} của ${r.symbol}`} onClick={() => onEdit(r)} /></td>
                    </tr>
                  ))}
                </tbody>
              );
            })}
          </table>
        </div>
      )}
      <p className="m-0 px-5 pt-3 pb-3.5 text-xs text-faint">{rulesNote(nearPct)}</p>
    </section>
  );
}

function shortDetail(r: RuleItem): string {
  if (r.note) return r.note;
  if (r.now_type === "text") return r.met ? `từ ${fmtDateShort(r.since)}` : `đang ${r.now}`;
  if (r.met) return `${nowText(r)} · ngưỡng ${thresholdText(r)}${r.fresh ? "" : ` · từ ${fmtDateShort(r.since)}`}`;
  return `ngưỡng ${thresholdText(r)} · ${fmtPct2(r.gap_pct)}`;
}

/** Danh sách mở ngay trong thẻ của mã trên điện thoại. */
export function RulesInline({ row, onAdd, onEdit }: { row: HoldingRow; onAdd: () => void; onEdit: (r: RuleItem) => void }) {
  return (
    <div className="flex flex-col pr-2">
      {row.rules.length === 0 && <p className="m-0 pt-1 text-fg-2">Chưa đặt quy tắc nào cho {row.symbol}.</p>}
      {GROUPS.map((g) => {
        const items = row.rules.filter((r) => r.side === g.side);
        if (!items.length) return null;
        const group = row.exit[g.side];
        const status = groupStatus(group, g.title);
        return (
          <div key={g.side} className="flex flex-col">
            <div className={cx("mt-1.5 text-xs font-semibold tracking-[0.04em] uppercase", g.color)}>
              {g.title}
              <span className={cx("ml-2 font-normal tracking-normal normal-case", status.className)}>{status.text}</span>
            </div>
            {items.map((r) => (
              <div key={r.id} className="grid grid-cols-[1fr_44px] items-center gap-1 border-t border-line pt-2 pb-1 first:mt-1">
                <div className="flex min-w-0 flex-col gap-0.5">
                  <div>{r.label}{r.sufficient && <SufficientTag />}</div>
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] text-muted">
                    <StatusChip rule={r} groupReady={group.ready} />
                    <span className={cx("font-mono tabular-nums", r.near && "text-event")}>{shortDetail(r)}</span>
                  </div>
                </div>
                <MoreButton label={`Sửa hoặc xóa quy tắc ${r.label} của ${r.symbol}`} onClick={() => onEdit(r)} />
              </div>
            ))}
          </div>
        );
      })}
      <button type="button" onClick={onAdd} className="mt-2 h-11 cursor-pointer rounded-lg border border-line-strong font-semibold">Thêm quy tắc cho {row.symbol}</button>
    </div>
  );
}
