"use client";

// Form thêm / sửa / xóa một quy tắc bán. Xem trước trạng thái bằng API, chưa lưu gì cho tới khi bấm Lưu.
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { cx } from "@/components/ui/Card";
import { ApiError, addRule, deleteRule, previewRule, updateRule } from "@/lib/api";
import { fmtPct2, fmtPrice } from "@/lib/format";
import type { RuleCatalogGroup, RuleItem } from "@/lib/types";
import { parseCost } from "./HoldingDialog";

/** "-4", "−4,5" hoặc "-4%" -> số; chỉ nhận 0 hoặc số âm. */
export function parseOffset(raw: string): number | null {
  const s = raw.trim().replace("−", "-").replace("%", "").replace(",", ".").trim();
  if (!/^-?\d+(\.\d+)?$/.test(s)) return null;
  const n = Number(s);
  return n <= 0 && n > -100 ? n || 0 : null;
}

const FIELD = "h-11 w-full rounded-lg border border-line-strong bg-sunken px-3 text-[15px] text-fg outline-none transition-colors focus:border-pos disabled:text-muted";
const LABEL = "flex flex-col gap-1.5 text-[13px] text-muted";

function Preview({ item, cost, line }: { item: RuleItem; cost: number | null; line?: string }) {
  const status = item.met ? `đạt${item.since ? ` từ ${item.since.split("-").reverse().join("/")}` : ""}` : "chưa đạt";
  const mono = "font-mono font-semibold tabular-nums";
  if (item.note) return <p className="m-0 rounded-lg bg-sunken px-3 py-2.5 text-fg-2">{item.note}.</p>;
  return (
    <div className="flex flex-col gap-0.5 rounded-lg bg-sunken px-3 py-2.5 text-fg-2">
      {item.threshold_text ? (
        <div>Cần giai đoạn <span className="font-semibold">{item.threshold_text}</span></div>
      ) : (
        <div>
          {item.now_type === "pct" && cost !== null && <>Giá vốn <span className={mono}>{fmtPrice(cost)}</span> → </>}
          {line && item.reference !== null && <>{line} <span className={mono}>{fmtPrice(item.reference)}</span> → </>}
          ngưỡng giá <span className={mono}>{fmtPrice(item.threshold)}</span>
        </div>
      )}
      <div>
        Hiện tại{" "}
        <span className={item.now_type === "text" ? "font-semibold" : mono}>
          {item.now_type === "text" ? item.now : item.now_type === "pct" ? fmtPct2(item.now as number) : fmtPrice(item.now as number)}
        </span>
        : <span className="font-semibold">{status}</span>
        {item.gap_pct !== null && <>, giá còn cách <span className={mono}>{fmtPct2(item.gap_pct)}</span></>}
      </div>
    </div>
  );
}

export function RuleDialog({ symbols, symbol: initialSymbol, rule, catalog, costOf, onClose, onSaved }: {
  symbols: string[];
  symbol: string;
  rule: RuleItem | null;
  catalog: RuleCatalogGroup[];
  costOf: (symbol: string) => number | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const editing = rule !== null;
  const [symbol, setSymbol] = useState(initialSymbol);
  const [kind, setKind] = useState(rule?.kind ?? catalog[0]?.kinds[0]?.kind ?? "");
  const defaultOf = (k: string) => {
    const v = catalog.flatMap((g) => g.kinds).find((x) => x.kind === k)?.default_value;
    return v === undefined ? "" : String(v);
  };
  const [raw, setRaw] = useState(rule?.value != null ? String(rule.value).replace(".", ",") : defaultOf(kind));
  const [sideRaw, setSide] = useState<RuleItem["side"]>(rule?.side ?? "loss");
  const [sufficient, setSufficient] = useState(rule?.sufficient ?? false);
  const [preview, setPreview] = useState<{ key: string; item: RuleItem | null; error: string | null } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const def = catalog.flatMap((g) => g.kinds).find((k) => k.kind === kind);
  const needsValue = def?.value_label != null;
  const isOffset = def?.default_value !== undefined;
  const value = !needsValue ? null : isOffset ? parseOffset(raw) : parseCost(raw);
  const ready = !needsValue || value !== null;
  const side = def?.fixed_side ?? sideRaw;
  const key = `${symbol}|${kind}|${value}`;

  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
  }, []);

  useEffect(() => {
    if (!ready) return;
    const ctl = new AbortController();
    const timer = setTimeout(() => {
      previewRule(symbol, kind, value, ctl.signal)
        .then((item) => setPreview({ key, item, error: null }))
        .catch((err: unknown) => {
          if (err instanceof ApiError) setPreview({ key, item: null, error: err.message });
        });
    }, 250);
    return () => {
      clearTimeout(timer);
      ctl.abort();
    };
  }, [key, ready, symbol, kind, value]);

  async function run(action: () => Promise<unknown>) {
    setSaving(true);
    setError(null);
    try {
      await action();
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không lưu được. Thử lại sau.");
      setSaving(false);
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!ready) return setError(isOffset ? "Nhập 0 hoặc số âm, ví dụ -4 là đóng cửa dưới đường 4%." : "Nhập một số lớn hơn 0.");
    void run(() => (rule ? updateRule(rule.id, kind, value, side, sufficient) : addRule(symbol, kind, value, side, sufficient)));
  }

  const shown = preview?.key === key && ready ? preview : null;

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onClose={onClose}
      className="m-auto w-[480px] max-w-[calc(100vw-32px)] rounded-xl border border-line bg-surface p-6 text-sm text-fg backdrop:bg-black/60"
    >
      <h2 id={titleId} className="m-0 text-lg font-semibold">{editing ? `Sửa quy tắc của ${rule.symbol}` : "Thêm quy tắc bán"}</h2>
      <form onSubmit={submit} noValidate className="mt-4 flex flex-col gap-3.5">
        <label className={LABEL}>
          Mã trong danh mục
          <select value={symbol} disabled={editing} onChange={(e) => setSymbol(e.target.value)} className={`${FIELD} font-mono font-semibold [color-scheme:dark]`}>
            {symbols.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
        <label className={LABEL}>
          Loại quy tắc
          <select value={kind} onChange={(e) => {
              setKind(e.target.value);
              setRaw(defaultOf(e.target.value)); // đơn vị mỗi loại mỗi khác nên không giữ số cũ
              setError(null);
            }} className={`${FIELD} [color-scheme:dark]`}>
            {catalog.map((g) => (
              <optgroup key={g.group} label={g.group}>
                {g.kinds.map((k) => <option key={k.kind} value={k.kind}>{k.label}</option>)}
              </optgroup>
            ))}
          </select>
        </label>
        <fieldset className="m-0 flex flex-col gap-1.5 border-0 p-0">
          <legend className="mb-1.5 p-0 text-[13px] text-muted">Quy tắc này dùng để</legend>
          <div className="grid grid-cols-2 gap-2">
            {(["profit", "loss"] as const).map((s) => (
              <label
                key={s}
                className={cx(
                  "flex h-11 items-center justify-center gap-2 rounded-lg border font-semibold transition-colors",
                  side === s ? (s === "profit" ? "border-pos bg-pos-soft text-pos" : "border-neg bg-neg-soft text-neg") : "border-line-strong text-fg-2",
                  def?.fixed_side ? "cursor-not-allowed" : "cursor-pointer",
                  def?.fixed_side && side !== s && "opacity-50",
                )}
              >
                <input type="radio" name="rule-side" value={s} checked={side === s} disabled={Boolean(def?.fixed_side)} onChange={() => setSide(s)} className="sr-only" />
                {s === "profit" ? "Chốt lãi" : "Chốt lỗ"}
              </label>
            ))}
          </div>
        </fieldset>
        <label className="flex cursor-pointer items-start gap-2.5 rounded-lg border border-line-strong px-3 py-2.5">
          <input type="checkbox" checked={sufficient} onChange={(e) => setSufficient(e.target.checked)} className="mt-0.5 size-[18px] flex-none accent-pos" />
          <span className="flex flex-col">
            <span className="font-semibold">Đạt là đủ</span>
            <span className="text-xs text-muted">Chỉ cần quy tắc này đạt là đủ điều kiện {side === "profit" ? "chốt lãi" : "chốt lỗ"}, bất kể các quy tắc khác trong nhóm.</span>
          </span>
        </label>
        {needsValue && (
          <label className={LABEL}>
            {def?.value_label}
            <input value={raw} onChange={(e) => { setRaw(e.target.value); setError(null); }} inputMode="decimal" autoComplete="off" className={`${FIELD} font-mono`} />
            {def?.value_hint && <span className="text-xs text-faint">{def.value_hint}</span>}
          </label>
        )}
        {shown?.item && <Preview item={shown.item} cost={costOf(symbol)} line={def?.line} />}
        {shown?.error && <p className="m-0 rounded-lg bg-sunken px-3 py-2.5 text-event">{shown.error}</p>}
        <p className="m-0 text-xs text-faint">Tính theo giá đóng cửa. Hệ thống chỉ báo đạt hay chưa, quyết định bán thuộc về bạn.</p>
        {error && <p role="alert" className="m-0 text-neg">{error}</p>}

        {confirmDelete && rule ? (
          <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
            <span className="font-medium">Xóa quy tắc này?</span>
            <div className="flex gap-2">
              <Button variant="ghost" disabled={saving} onClick={() => setConfirmDelete(false)}>Không</Button>
              <Button disabled={saving} onClick={() => void run(() => deleteRule(rule.id))} className="bg-neg! text-[#2A0B0B]! hover:enabled:opacity-90">Xóa</Button>
            </div>
          </div>
        ) : (
          <div className="mt-1 flex flex-wrap items-center gap-2">
            {editing && <Button variant="ghost" disabled={saving} onClick={() => setConfirmDelete(true)} className="text-neg">Xóa quy tắc</Button>}
            <div className="ml-auto flex gap-2">
              <Button variant="ghost" disabled={saving} onClick={() => ref.current?.close()}>Hủy</Button>
              <Button type="submit" disabled={saving}>{saving ? "Đang lưu…" : "Lưu"}</Button>
            </div>
          </div>
        )}
      </form>
    </dialog>
  );
}
