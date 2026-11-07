"use client";

// Thông báo Telegram trên trang danh mục: nút chuông bật/tắt theo mã, hộp xem trước rồi gửi.
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState, useTransition } from "react";
import { Button } from "@/components/ui/Button";
import { cx } from "@/components/ui/Card";
import { ApiError, getAlertPreview, sendAlert, setHoldingAlerts } from "@/lib/api";
import type { AlertPreview } from "@/lib/types";

/** Chuông sáng là đang bật; gạch chéo là đã tắt. Luôn có nhãn cho trình đọc màn hình. */
export function AlertToggle({ symbol, enabled }: { symbol: string; enabled: boolean }) {
  const router = useRouter();
  const [, startTransition] = useTransition();
  const [pending, setPending] = useState<boolean | null>(null); // giá trị đang lưu, hiện ngay khi bấm
  const [error, setError] = useState<string | null>(null);
  const on = pending ?? enabled;

  async function toggle() {
    const next = !on;
    setPending(next);
    setError(null);
    try {
      await setHoldingAlerts(symbol, next);
      startTransition(() => router.refresh());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không lưu được");
    } finally {
      setPending(null);
    }
  }

  const label = `${on ? "Tắt" : "Bật"} thông báo của ${symbol}`;
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      title={error ?? (on ? `Đang bật thông báo cho ${symbol}` : `Đã tắt thông báo cho ${symbol}`)}
      onClick={() => void toggle()}
      className={cx(
        "inline-grid size-11 flex-none cursor-pointer place-items-center rounded-lg transition-colors hover:bg-raised",
        error ? "text-neg" : on ? "text-pos" : "text-faint",
      )}
    >
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M6 9a6 6 0 0 1 12 0c0 6 2.5 8 2.5 8h-17S6 15 6 9Z" fill={on ? "currentColor" : "none"} />
        <path d="M10 20.5a2.2 2.2 0 0 0 4 0" />
        {!on && <line x1="3" y1="3" x2="21" y2="21" />}
      </svg>
    </button>
  );
}

/** Xem trước nội dung, bấm Gửi mới gửi. Lấy nội dung lúc mở để đúng với nút chuông vừa đổi. */
export function AlertDialog({ onClose }: { onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [preview, setPreview] = useState<AlertPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);

  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
    const ctl = new AbortController();
    getAlertPreview(ctl.signal)
      .then(setPreview)
      .catch((err: unknown) => {
        if (err instanceof ApiError) setError(err.message);
      });
    return () => ctl.abort();
  }, []);

  async function send() {
    setSending(true);
    setError(null);
    try {
      await sendAlert();
      setSent(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không gửi được. Thử lại sau.");
    } finally {
      setSending(false);
    }
  }

  const canSend = Boolean(preview?.configured && preview.enabled_count > 0) && !sent;

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onClose={onClose}
      className="m-auto w-[520px] max-w-[calc(100vw-32px)] rounded-xl border border-line bg-surface p-6 text-sm text-fg backdrop:bg-black/60"
    >
      <h2 id={titleId} className="m-0 text-lg font-semibold">Gửi thông báo qua Telegram</h2>
      <div className="mt-4 flex flex-col gap-3">
        {!preview && !error && <p className="m-0 text-muted" role="status">Đang lấy nội dung…</p>}
        {preview && (
          <>
            <pre className="m-0 max-h-[50vh] overflow-auto rounded-lg bg-sunken p-3 font-sans text-sm leading-relaxed whitespace-pre-wrap text-fg-2">{preview.text}</pre>
            <p className="m-0 text-xs text-muted">
              Gửi {preview.enabled_count} mã đang bật thông báo{preview.muted_count > 0 && `; bỏ qua ${preview.muted.join(", ")} vì đã tắt`}.
              {" "}Dùng dữ liệu đang có, không làm thay đổi lịch gửi tự động.
            </p>
            {preview.enabled_count === 0 && <p className="m-0 text-event">Không có mã nào đang bật thông báo.</p>}
            {!preview.configured && <p className="m-0 text-event">Chưa cấu hình Telegram: cần TELEGRAM_BOT_TOKEN và TELEGRAM_CHAT_ID trong file .env.</p>}
          </>
        )}
        {error && <p role="alert" className="m-0 text-neg">{error}</p>}
        {sent && <p role="status" className="m-0 font-semibold text-pos">Đã gửi. Kiểm tra Telegram của bạn.</p>}
        <div className="mt-1 flex justify-end gap-2">
          <Button variant="ghost" disabled={sending} onClick={() => ref.current?.close()}>{sent ? "Đóng" : "Hủy"}</Button>
          {!sent && <Button disabled={!canSend || sending} onClick={() => void send()}>{sending ? "Đang gửi…" : "Gửi"}</Button>}
        </div>
      </div>
    </dialog>
  );
}
