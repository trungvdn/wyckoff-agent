"use client";

// Bảng điều kiện lọc, chia nhóm như bản mẫu đã duyệt. Mọi thay đổi áp dụng ngay.
import { useId, useState, type ReactNode } from "react";
import { cx } from "@/components/ui/Card";
import {
  ANY_EVENT, CONFIDENCE_OPTIONS, EVENT_OPTIONS, NUM_FIELDS, PHASE_OPTIONS, STAGE_OPTIONS, STATUS_OPTIONS,
  type Filters, type NumField, type Op,
} from "@/lib/screener";

const SELECT = "h-9 rounded-lg border border-line-strong bg-sunken px-2 text-[13px] text-fg outline-none focus:border-pos";
const NUM_INPUT = "h-9 rounded-lg border bg-sunken px-2 text-right font-mono text-[13px] text-fg outline-none focus:border-pos";

/** "10", "-2,5", "1.234,5" -> số; rỗng -> null; sai -> undefined. */
export function parseNumber(raw: string): number | null | undefined {
  const t = raw.trim().replace(/\s/g, "");
  if (!t) return null;
  const s = t.includes(",") ? t.replace(/\./g, "").replace(",", ".") : t;
  return /^[-+]?\d+(\.\d+)?$/.test(s) ? Number(s) : undefined;
}

const fmtInput = (x: number) => String(x).replace(".", ",");

function Group({ title, children, last }: { title: string; children: ReactNode; last?: boolean }) {
  return (
    <fieldset className={cx("m-0 flex min-w-0 flex-col gap-2.5 border-0 px-4 py-3.5", !last && "border-b border-line")}>
      <legend className="float-left mb-0.5 w-full p-0 text-xs font-semibold tracking-[0.06em] text-muted uppercase">{title}</legend>
      {children}
    </fieldset>
  );
}

function ChipToggle<T extends string>({ options, picked, onChange, label }: {
  options: { id: T; label: string }[];
  picked: T[];
  onChange: (next: T[]) => void;
  label: string;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="text-[13px] text-fg-2">{label}</div>
      <div role="group" aria-label={label} className="flex flex-wrap gap-1.5">
        {options.map((o) => {
          const on = picked.includes(o.id);
          return (
            <button
              key={o.id}
              type="button"
              aria-pressed={on}
              onClick={() => onChange(on ? picked.filter((x) => x !== o.id) : [...picked, o.id])}
              className={cx(
                "h-8 min-w-9 cursor-pointer rounded-full border px-2.5 text-[13px] transition-colors",
                on ? "border-pos bg-pos-soft text-pos-hover" : "border-line-strong text-fg-2 hover:border-muted",
              )}
            >
              {o.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/** Ô số giữ chuỗi đang gõ; chỉ cập nhật bộ lọc khi chuỗi hợp lệ, xóa trắng là bỏ điều kiện. */
function NumberInput({ value, onCommit, label, className, active, placeholder = "—" }: {
  value: number | null;
  onCommit: (x: number | null) => void;
  label: string;
  className?: string;
  active?: boolean; // viền nhấn khi điều kiện đang dùng
  placeholder?: string;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const shown = draft ?? (value == null ? "" : fmtInput(value));
  const bad = draft != null && parseNumber(draft) === undefined;
  return (
    <input
      inputMode="decimal"
      aria-label={label}
      aria-invalid={bad || undefined}
      placeholder={placeholder}
      value={shown}
      onChange={(e) => {
        setDraft(e.target.value);
        const x = parseNumber(e.target.value);
        if (x !== undefined) onCommit(x);
      }}
      onBlur={() => setDraft(null)}
      className={cx(NUM_INPUT, bad ? "border-neg" : (active ?? value != null) ? "border-pos" : "border-line-strong", className)}
    />
  );
}

function NumRow({ field, filters, onChange }: { field: NumField; filters: Filters; onChange: (f: Filters) => void }) {
  const id = useId();
  const c = filters.num[field.key];
  const op: Op = c?.op ?? field.defaultOp;
  const set = (next: { op: Op; value: number | null }) =>
    onChange({ ...filters, num: { ...filters.num, [field.key]: next.value == null ? undefined : { op: next.op, value: next.value } } });
  return (
    <div className="grid grid-cols-[1fr_52px_84px] items-center gap-2 text-[13px] text-fg-2">
      <span id={id}>{field.label}</span>
      <select aria-label={`So sánh ${field.label}`} value={op} onChange={(e) => set({ op: e.target.value as Op, value: c?.value ?? null })} className={cx(SELECT, "px-1")}>
        <option value=">=">≥</option>
        <option value="<=">≤</option>
      </select>
      <NumberInput label={`${field.label} (${field.hint})`} placeholder={field.hint} value={c?.value ?? null} onCommit={(value) => set({ op, value })} />
    </div>
  );
}

export function FilterPanel({ filters, onChange, heldCount }: { filters: Filters; onChange: (f: Filters) => void; heldCount: number }) {
  const set = <K extends keyof Filters>(key: K, value: Filters[K]) => onChange({ ...filters, [key]: value });
  return (
    <>
      <Group title="Cấu trúc Wyckoff">
        <ChipToggle label="Giai đoạn" options={STAGE_OPTIONS} picked={filters.stages} onChange={(v) => set("stages", v)} />
        <ChipToggle label="Trạng thái" options={STATUS_OPTIONS} picked={filters.statuses} onChange={(v) => set("statuses", v)} />
        <ChipToggle label="Pha" options={PHASE_OPTIONS} picked={filters.phases} onChange={(v) => set("phases", v)} />
        <label className="flex items-center justify-between gap-2 text-[13px] text-fg-2">
          Tin cậy tối thiểu
          <select value={filters.minConfidence} onChange={(e) => set("minConfidence", Number(e.target.value))} className={SELECT}>
            {CONFIDENCE_OPTIONS.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
          </select>
        </label>
      </Group>

      <Group title="Sự kiện, thay đổi">
        <div className="flex flex-wrap items-center gap-2 text-[13px] text-fg-2">
          Có
          <select
            aria-label="Sự kiện"
            value={filters.event ?? ""}
            onChange={(e) => set("event", e.target.value || null)}
            className={cx(SELECT, "min-w-0 flex-1", filters.event != null && "border-pos")}
          >
            <option value="">— Không lọc —</option>
            <option value={ANY_EVENT}>Bất kỳ sự kiện</option>
            {EVENT_OPTIONS.map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
          trong
          <NumberInput
            label="Số phiên gần nhất có sự kiện"
            value={filters.eventWithin}
            onCommit={(x) => x != null && x > 0 && set("eventWithin", Math.round(x))}
            active={filters.event != null}
            className="w-12"
          />
          phiên
        </div>
        <label className="flex items-center gap-2 text-[13px] text-fg-2">
          <input
            type="checkbox"
            checked={filters.phaseChangedWithin != null}
            onChange={(e) => set("phaseChangedWithin", e.target.checked ? 5 : null)}
            className="size-[18px] accent-pos"
          />
          Vừa đổi pha trong
          <NumberInput
            label="Số phiên kể từ khi đổi pha"
            value={filters.phaseChangedWithin ?? 5}
            onCommit={(x) => x != null && x > 0 && set("phaseChangedWithin", Math.round(x))}
            active={filters.phaseChangedWithin != null}
            className="w-12"
          />
          phiên
        </label>
      </Group>

      <Group title="Mức giá, xu hướng">
        {NUM_FIELDS.filter((f) => f.group === "price").map((f) => <NumRow key={f.key} field={f} filters={filters} onChange={onChange} />)}
      </Group>

      <Group title="Thanh khoản">
        {NUM_FIELDS.filter((f) => f.group === "liquidity").map((f) => <NumRow key={f.key} field={f} filters={filters} onChange={onChange} />)}
      </Group>

      <Group title="Danh mục" last>
        <label className="flex items-center gap-2 text-[13px] text-fg-2">
          <input type="checkbox" checked={filters.excludeHeld} onChange={(e) => set("excludeHeld", e.target.checked)} className="size-[18px] accent-pos" />
          Bỏ mã đang giữ ({heldCount} mã)
        </label>
      </Group>
    </>
  );
}
