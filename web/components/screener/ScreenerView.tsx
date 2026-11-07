"use client";

// Trang Lọc cổ phiếu: bảng điều kiện bên trái (từ 1081px; nhỏ hơn thì mở dạng hộp thoại), kết quả bên phải.
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useId, useMemo, useRef, useState, useTransition } from "react";
import { StatusPill } from "@/components/layout/Header";
import { SetStatus } from "@/components/layout/StatusContext";
import { Button } from "@/components/ui/Button";
import { cx } from "@/components/ui/Card";
import { ApiError, deleteFilter } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { EMPTY_FILTERS, SORT_OPTIONS, activeChips, matches, normalizeFilters, sortRows, type Filters, type SortKey } from "@/lib/screener";
import type { SavedFilter, ScanData } from "@/lib/types";
import { FilterPanel } from "./FilterPanel";
import { ResultCards, ResultsTable } from "./ResultsTable";
import { SaveFilterDialog } from "./SaveFilterDialog";
import { RescanButton, ScanProgressCard, useScanJob } from "./ScanControls";

const FILTER_ICON = (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M3 5h18l-7 8v6l-4 2v-8Z" />
  </svg>
);
const SAVE_ICON = (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M5 3h11l3 3v15H5Z" />
    <path d="M8 3v5h7V3" />
  </svg>
);
const SELECT = "h-11 min-w-0 rounded-lg border border-line-strong bg-surface px-2.5 text-sm text-fg outline-none focus:border-pos";
const NEW_FILTER = "";

function PageBar({ children }: { children?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <h1 className="m-0 w-full text-lg font-semibold sm:w-auto">Lọc cổ phiếu</h1>
      {children}
    </div>
  );
}

export function ScreenerBarLoading() {
  return <PageBar><StatusPill /></PageBar>;
}

/** Hộp điều kiện cho màn hình hẹp: toàn màn hình trên điện thoại, nút xem kết quả ở đáy. */
function FilterSheet({ count, active, onClear, onClose, children }: {
  count: number;
  active: number;
  onClear: () => void;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
  }, []);
  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onClose={onClose}
      className="m-0 h-dvh max-h-none w-full max-w-none bg-surface p-0 text-sm text-fg backdrop:bg-black/60 sm:m-auto sm:h-[min(820px,calc(100dvh-32px))] sm:w-[420px] sm:rounded-xl sm:border sm:border-line"
    >
      <div className="flex h-full flex-col">
        <div className="flex items-center gap-2 border-b border-line py-2 pr-2 pl-4">
          <h2 id={titleId} className="m-0 text-base font-semibold">Điều kiện <span className="font-normal text-muted">· {active} đang dùng</span></h2>
          <button type="button" disabled={!active} onClick={onClear} className="ml-auto h-9 cursor-pointer rounded-lg px-2 text-[13px] text-muted hover:text-fg disabled:cursor-default disabled:opacity-50">
            Xóa hết
          </button>
          <button type="button" aria-label="Đóng" onClick={() => ref.current?.close()} className="grid size-11 cursor-pointer place-items-center rounded-lg text-fg-2 hover:bg-raised">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true"><line x1="6" y1="6" x2="18" y2="18" /><line x1="18" y1="6" x2="6" y2="18" /></svg>
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
        <div className="border-t border-line p-4">
          <Button className="w-full" onClick={() => ref.current?.close()}>Xem {count} mã</Button>
        </div>
      </div>
    </dialog>
  );
}

export function ScreenerView({ data, saved: initialSaved }: { data: ScanData; saved: SavedFilter[] }) {
  const router = useRouter();
  const [, startTransition] = useTransition();
  const [saved, setSaved] = useState(initialSaved);
  const [selectedId, setSelectedId] = useState<number | null>(initialSaved[0]?.id ?? null);
  const [filters, setFilters] = useState<Filters>(() => (initialSaved[0] ? normalizeFilters(initialSaved[0].filters) : EMPTY_FILTERS));
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "value20", dir: -1 });
  const [saving, setSaving] = useState(false);
  const [sheet, setSheet] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const onDone = useCallback(() => startTransition(() => router.refresh()), [router]);
  const job = useScanJob(data.job, onDone);
  // Chỉ báo dừng / lỗi của lượt quét vừa kết thúc khi đang mở trang, không phải lượt cũ
  const [initialFinished] = useState(data.job.finished);
  const justFinished = !job.progress.running && job.progress.finished !== initialFinished;

  const selected = saved.find((f) => f.id === selectedId) ?? null;
  const chips = activeChips(filters);
  const rows = useMemo(() => sortRows(data.rows.filter((r) => matches(r, filters)), sort.key, sort.dir), [data.rows, filters, sort]);
  const asOf = data.as_of;
  const stale = asOf ? data.rows.filter((r) => r.as_of < asOf).length : 0;
  const smaLabel = `So SMA${data.sma_periods[0]}`;

  function pick(id: string) {
    if (id === NEW_FILTER) {
      setSelectedId(null);
      setFilters(EMPTY_FILTERS);
      return;
    }
    const f = saved.find((x) => x.id === Number(id));
    if (f) {
      setSelectedId(f.id);
      setFilters(normalizeFilters(f.filters));
    }
  }

  async function remove() {
    if (!selected || !window.confirm(`Xóa bộ lọc “${selected.name}”?`)) return;
    try {
      await deleteFilter(selected.id);
      setSaved((xs) => xs.filter((x) => x.id !== selected.id));
      setSelectedId(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không xóa được bộ lọc.");
    }
  }

  function onSort(key: SortKey) {
    setSort((s) => (s.key === key ? { key, dir: s.dir === 1 ? -1 : 1 } : { key, dir: SORT_OPTIONS.find((o) => o.key === key)?.dir ?? -1 }));
  }

  const panelHeader = (
    <div className="flex items-center justify-between border-b border-line px-4 py-2">
      <span className="font-semibold">Điều kiện <span className="font-normal text-muted">· {chips.length} đang dùng</span></span>
      <button type="button" disabled={!chips.length} onClick={() => setFilters(EMPTY_FILTERS)} className="h-9 cursor-pointer rounded-lg px-2 text-[13px] text-muted hover:text-fg disabled:cursor-default disabled:opacity-50">
        Xóa hết
      </button>
    </div>
  );
  const panel = <FilterPanel filters={filters} onChange={setFilters} heldCount={data.held.length} />;
  const saveButton = (
    <Button onClick={() => setSaving(true)} className="inline-flex flex-1 items-center justify-center gap-2">{SAVE_ICON}Lưu bộ lọc</Button>
  );

  return (
    <>
      <SetStatus
        kind={job.progress.running ? "loading" : asOf ? "ok" : "error"}
        text={job.progress.running ? "Đang quét thị trường…" : asOf ? `Quét phiên ${fmtDate(asOf)} · ${data.rows.length} mã` : "Chưa có lượt quét"}
      />
      <PageBar>
        <label className="flex min-w-0 items-center gap-2 max-sm:w-full">
          <span className="text-[13px] whitespace-nowrap text-muted max-sm:sr-only">Bộ lọc đã lưu</span>
          <select value={selectedId ?? NEW_FILTER} onChange={(e) => pick(e.target.value)} className={cx(SELECT, "flex-1 sm:w-[240px] sm:flex-none")}>
            {saved.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
            <option value={NEW_FILTER}>— Bộ lọc mới —</option>
          </select>
          {selected && (
            <button type="button" aria-label={`Xóa bộ lọc ${selected.name}`} title="Xóa bộ lọc đã lưu" onClick={() => void remove()} className="grid size-11 flex-none cursor-pointer place-items-center rounded-lg text-faint hover:bg-raised hover:text-neg">
              <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" /></svg>
            </button>
          )}
        </label>
        <StatusPill />
        <RescanButton busy={job.progress.running} onStart={() => void job.start()} />
      </PageBar>

      {job.progress.running && <ScanProgressCard progress={job.progress} onStop={() => void job.stop()} />}
      {justFinished && job.progress.error && <p role="alert" className="m-0 text-neg">Lượt quét lỗi: {job.progress.error}</p>}
      {justFinished && job.progress.stopped && <p role="status" className="m-0 text-muted">Đã dừng lượt quét; bảng vẫn là kết quả của lượt trước.</p>}
      {(job.error || error) && <p role="alert" className="m-0 text-neg">{job.error ?? error}</p>}

      <main className="flex flex-col gap-4 wide:flex-row wide:items-start wide:gap-5">
        <form aria-label="Điều kiện lọc" onSubmit={(e) => e.preventDefault()} className="flex flex-col rounded-xl border border-line bg-surface max-wide:hidden wide:w-[310px] wide:flex-none">
          {panelHeader}
          {panel}
          <div className="flex border-t border-line p-4">{saveButton}</div>
        </form>

        <div className="flex gap-2 wide:hidden">
          <Button onClick={() => setSheet(true)} className="inline-flex flex-1 items-center justify-center gap-2 sm:flex-none">
            {FILTER_ICON}Điều kiện · {chips.length}
          </Button>
          <Button variant="ghost" onClick={() => setSaving(true)} className="inline-flex items-center gap-2">{SAVE_ICON}Lưu</Button>
        </div>

        <section aria-labelledby="results-title" className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-line bg-surface max-sm:border-0 max-sm:bg-transparent">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2 py-3.5 sm:px-5">
            <h2 id="results-title" className="m-0 text-sm font-semibold">
              <span className="font-mono text-base">{rows.length}</span> mã khớp
              {chips.length > 0 && <span className="font-normal text-muted"> / {data.rows.length}</span>}
            </h2>
            {chips.length > 0 && (
              <ul aria-label="Điều kiện đang dùng" className="m-0 flex list-none flex-wrap gap-1.5 p-0">
                {chips.map((c) => (
                  <li key={c.id} className="inline-flex h-7 items-center gap-1 rounded-full border border-pos-dim bg-pos-soft pr-1 pl-2.5 text-xs text-pos-hover">
                    {c.label}
                    <button type="button" aria-label={`Bỏ điều kiện ${c.label}`} onClick={() => setFilters(c.clear(filters))} className="grid size-[22px] cursor-pointer place-items-center rounded-full hover:bg-pos-dim">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" aria-hidden="true"><line x1="6" y1="6" x2="18" y2="18" /><line x1="18" y1="6" x2="6" y2="18" /></svg>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <select
              aria-label="Sắp xếp"
              value={`${sort.key}:${sort.dir}`}
              onChange={(e) => {
                const [key, dir] = e.target.value.split(":");
                setSort({ key: key as SortKey, dir: Number(dir) as 1 | -1 });
              }}
              className={cx(SELECT, "ml-auto h-9 text-[13px] sm:hidden")}
            >
              {SORT_OPTIONS.map((o) => <option key={o.key} value={`${o.key}:${o.dir}`}>{o.label}</option>)}
              {!SORT_OPTIONS.some((o) => o.key === sort.key && o.dir === sort.dir) && <option value={`${sort.key}:${sort.dir}`}>Đang sắp xếp theo cột</option>}
            </select>
          </div>

          {!asOf ? (
            <div className="flex flex-col items-start gap-3 border-t border-line px-5 py-8 text-fg-2 max-sm:px-0">
              <p className="m-0">Chưa có lượt quét nào. Bấm “Quét lại” để phân tích mọi mã trong dữ liệu, hoặc chạy <code className="font-mono">python scripts/scan_market.py</code>.</p>
            </div>
          ) : rows.length === 0 ? (
            <div className="flex flex-col items-start gap-3 border-t border-line px-5 py-8 text-fg-2 max-sm:px-0">
              <p className="m-0">Không có mã nào khớp mọi điều kiện. Thử bỏ bớt điều kiện.</p>
              <Button variant="ghost" onClick={() => setFilters(EMPTY_FILTERS)}>Xóa hết điều kiện</Button>
            </div>
          ) : (
            <>
              <ResultsTable rows={rows} asOf={asOf} sort={sort} onSort={onSort} smaLabel={smaLabel} />
              <ResultCards rows={rows} asOf={asOf} />
            </>
          )}

          <div className="flex flex-col gap-1.5 px-5 pt-3 pb-3.5 text-xs text-faint max-sm:px-0">
            {data.notices.map((n) => <p key={n} className="m-0">{n}</p>)}
            {stale > 0 && <p className="m-0 text-event">{stale} mã có dữ liệu cũ hơn phiên {fmtDate(asOf)}: bấm “Quét lại” để cập nhật giá.</p>}
            {data.failed.length > 0 && (
              <p className="m-0">Không quét được: {data.failed.map((f) => `${f.symbol} (${f.reason})`).join("; ")}.</p>
            )}
            <p className="m-0">
              Kết quả chỉ mô tả trạng thái theo bộ lọc bạn đặt, không xếp hạng và không phải khuyến nghị. Bộ phát hiện range chưa vượt được
              kiểm định placebo (điều tra H8). “Tới vô hiệu” âm là mức vô hiệu nằm dưới giá; “đã thủng” là giá đã ở dưới mức đó.
            </p>
          </div>
        </section>
      </main>

      {sheet && (
        <FilterSheet count={rows.length} active={chips.length} onClear={() => setFilters(EMPTY_FILTERS)} onClose={() => setSheet(false)}>
          {panel}
        </FilterSheet>
      )}
      {saving && (
        <SaveFilterDialog
          filters={filters}
          summary={chips.map((c) => c.label)}
          current={selected}
          onClose={() => setSaving(false)}
          onSaved={(f) => {
            setSaved((xs) => [...xs.filter((x) => x.id !== f.id), f].sort((a, b) => a.name.localeCompare(b.name, "vi")));
            setSelectedId(f.id);
          }}
        />
      )}
    </>
  );
}
