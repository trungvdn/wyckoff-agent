"use client";

// Lưu bộ lọc hiện tại: đặt tên, hoặc ghi đè bộ lọc đang chọn.
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { ApiError, saveFilter } from "@/lib/api";
import type { Filters } from "@/lib/screener";
import type { SavedFilter } from "@/lib/types";

export function SaveFilterDialog({ filters, summary, current, onClose, onSaved }: {
  filters: Filters;
  summary: string[];
  current: SavedFilter | null;
  onClose: () => void;
  onSaved: (saved: SavedFilter) => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [name, setName] = useState(current?.name ?? "");
  const [overwrite, setOverwrite] = useState(current != null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setError("Cần đặt tên cho bộ lọc.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      onSaved(await saveFilter(trimmed, filters, overwrite && current ? current.id : undefined));
      ref.current?.close();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không lưu được. Thử lại sau.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onClose={onClose}
      className="m-auto w-[440px] max-w-[calc(100vw-32px)] rounded-xl border border-line bg-surface p-6 text-sm text-fg backdrop:bg-black/60"
    >
      <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3.5">
        <h2 id={titleId} className="m-0 text-lg font-semibold">Lưu bộ lọc</h2>
        <label className="flex flex-col gap-1.5 text-[13px] text-fg-2">
          Tên
          <input
            autoFocus
            maxLength={60}
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="h-11 rounded-lg border border-line-strong bg-sunken px-3 text-[15px] text-fg outline-none focus:border-pos"
          />
        </label>
        <p className="m-0 text-[13px] text-muted">
          {summary.length ? `Lưu ${summary.length} điều kiện: ${summary.join(" · ")}` : "Chưa có điều kiện nào: bộ lọc sẽ hiện mọi mã."}
        </p>
        {current && (
          <label className="flex items-center gap-2 text-[13px] text-fg-2">
            <input type="checkbox" checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)} className="size-[18px] accent-pos" />
            Ghi đè bộ lọc “{current.name}”
          </label>
        )}
        {error && <p role="alert" className="m-0 text-neg">{error}</p>}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" disabled={saving} onClick={() => ref.current?.close()}>Hủy</Button>
          <Button type="submit" disabled={saving}>{saving ? "Đang lưu…" : "Lưu"}</Button>
        </div>
      </form>
    </dialog>
  );
}
