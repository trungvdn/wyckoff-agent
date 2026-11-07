"use client";

// Form thêm / sửa / xóa một mã, dùng <dialog> gốc của trình duyệt (khóa focus, phím Esc).
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { cx } from "@/components/ui/Card";
import { ApiError, addHolding, deleteHolding, getQuote, updateHolding } from "@/lib/api";
import { fmtMillion, fmtPrice } from "@/lib/format";
import { SYMBOL_RE } from "@/lib/market";

export interface DialogValue {
  symbol: string;
  quantity: number;
  cost: number;
  bought_on: string;
  close: number | null;
}

/** "2.000" -> 2000. Dấu chấm và khoảng trắng chỉ để ngăn cách hàng nghìn. */
export function parseQuantity(raw: string): number | null {
  const s = raw.replace(/[.\s]/g, "");
  return /^\d+$/.test(s) && Number(s) > 0 ? Number(s) : null;
}

/** "22,40" hoặc "22.4" -> 22.4. Có dấu phẩy thì dấu chấm là ngăn cách hàng nghìn. */
export function parseCost(raw: string): number | null {
  const t = raw.trim();
  const s = t.includes(",") ? t.replace(/\./g, "").replace(",", ".") : t;
  return /^\d+(\.\d+)?$/.test(s) && Number(s) > 0 ? Number(s) : null;
}

const FIELD = "h-11 w-full rounded-lg border border-line-strong bg-sunken px-3 font-mono text-[15px] text-fg outline-none transition-colors focus:border-pos disabled:text-muted";
const LABEL = "flex flex-col gap-1.5 text-[13px] text-muted";

export function HoldingDialog({ initial, onClose, onSaved }: { initial: DialogValue | null; onClose: () => void; onSaved: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const editing = initial !== null;
  const [symbol, setSymbol] = useState(initial?.symbol ?? "");
  const [quantity, setQuantity] = useState(initial ? new Intl.NumberFormat("vi-VN").format(initial.quantity) : "");
  const [cost, setCost] = useState(initial ? fmtPrice(initial.cost) : "");
  const [boughtOn, setBoughtOn] = useState(initial?.bought_on ?? "");
  const [close, setClose] = useState<number | null>(initial?.close ?? null);
  const [symbolError, setSymbolError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const lookup = useRef<AbortController | null>(null);

  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
    return () => lookup.current?.abort();
  }, []);

  /** Rời ô mã: kiểm tra mã và lấy giá đóng cửa gần nhất để đối chiếu. */
  async function lookUp() {
    const s = symbol.trim();
    lookup.current?.abort();
    setClose(null);
    setSymbolError(null);
    if (!s) return;
    if (!SYMBOL_RE.test(s)) {
      setSymbolError("Mã gồm 3–10 ký tự chữ hoặc số.");
      return;
    }
    const ctl = new AbortController();
    lookup.current = ctl;
    try {
      setClose((await getQuote(s, ctl.signal)).close);
    } catch (err) {
      if (err instanceof ApiError) setSymbolError(err.message);
    }
  }

  const q = parseQuantity(quantity);
  const c = parseCost(cost);

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
    const s = symbol.trim();
    if (!SYMBOL_RE.test(s)) return setError("Mã gồm 3–10 ký tự chữ hoặc số.");
    if (q === null) return setError("Số lượng phải là số nguyên lớn hơn 0.");
    if (c === null) return setError("Giá vốn phải lớn hơn 0, tính bằng nghìn đồng.");
    if (!boughtOn) return setError("Chọn ngày mua.");
    const fields = { quantity: q, cost: c, bought_on: boughtOn };
    void run(() => (editing ? updateHolding(s, fields) : addHolding(s, fields)));
  }

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onClose={onClose}
      className="m-auto w-[480px] max-w-[calc(100vw-32px)] rounded-xl border border-line bg-surface p-6 text-sm text-fg backdrop:bg-black/60"
    >
      <h2 id={titleId} className="m-0 text-lg font-semibold">{editing ? `Sửa ${initial.symbol}` : "Thêm mã vào danh mục"}</h2>
      <form onSubmit={submit} noValidate className="mt-4 flex flex-col gap-3.5">
        <label className={LABEL}>
          Mã cổ phiếu
          <input
            value={symbol}
            disabled={editing}
            autoFocus={!editing}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            onBlur={() => void lookUp()}
            maxLength={10}
            spellCheck={false}
            autoCapitalize="characters"
            autoComplete="off"
            placeholder="VD: HPG"
            className={cx(FIELD, "font-semibold uppercase placeholder:font-normal placeholder:text-faint")}
          />
          {symbolError && <span role="alert" className="text-neg">{symbolError}</span>}
        </label>
        <div className="grid grid-cols-2 gap-3">
          <label className={LABEL}>
            Số lượng (cổ phiếu)
            <input value={quantity} onChange={(e) => setQuantity(e.target.value)} inputMode="numeric" autoComplete="off" className={FIELD} />
          </label>
          <label className={LABEL}>
            Giá vốn (nghìn đồng)
            <input value={cost} onChange={(e) => setCost(e.target.value)} inputMode="decimal" autoComplete="off" className={FIELD} />
          </label>
        </div>
        <label className={LABEL}>
          Ngày mua
          <input type="date" value={boughtOn} onChange={(e) => setBoughtOn(e.target.value)} className={cx(FIELD, "[color-scheme:dark]")} />
        </label>
        {(q !== null && c !== null) || close !== null ? (
          <p className="m-0 rounded-lg bg-sunken px-3 py-2.5 text-fg-2">
            {q !== null && c !== null && <>Tổng vốn <span className="font-mono font-semibold">{fmtMillion(q * c * 1000)}</span></>}
            {q !== null && c !== null && close !== null && " · "}
            {close !== null && <>giá đóng cửa gần nhất <span className="font-mono font-semibold">{fmtPrice(close)}</span></>}
          </p>
        ) : null}
        <p className="m-0 text-xs text-faint">Dữ liệu danh mục chỉ lưu trên máy chạy ứng dụng, không đưa vào git.</p>
        {error && <p role="alert" className="m-0 text-neg">{error}</p>}

        {confirmDelete ? (
          <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
            <span className="font-medium">Xóa {symbol} khỏi danh mục?</span>
            <div className="flex gap-2">
              <Button variant="ghost" disabled={saving} onClick={() => setConfirmDelete(false)}>Không</Button>
              <Button
                disabled={saving}
                onClick={() => void run(() => deleteHolding(symbol))}
                className="bg-neg! text-[#2A0B0B]! hover:enabled:opacity-90"
              >
                Xóa
              </Button>
            </div>
          </div>
        ) : (
          <div className="mt-1 flex flex-wrap items-center gap-2">
            {editing && <Button variant="ghost" disabled={saving} onClick={() => setConfirmDelete(true)} className="text-neg">Xóa mã</Button>}
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

