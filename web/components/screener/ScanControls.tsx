"use client";

// Nút "Quét lại" và thanh tiến độ. Bảng cũ vẫn hiện trong lúc quét; quét xong thì tải lại trang.
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { ApiError, getScanStatus, startScan, stopScan } from "@/lib/api";
import type { ScanProgress } from "@/lib/types";

const POLL_MS = 1000;

function eta(s: number | null) {
  if (s == null) return "đang ước tính thời gian";
  if (s < 60) return "còn dưới 1 phút";
  return `còn khoảng ${Math.round(s / 60)} phút`;
}

export function RescanButton({ busy, onStart, className }: { busy: boolean; onStart: () => void; className?: string }) {
  return (
    <Button variant="ghost" disabled={busy} onClick={onStart} className={`inline-flex items-center gap-2 ${className ?? ""}`}>
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="text-pos">
        <path d="M20 11a8 8 0 1 0-2.3 5.7" />
        <polyline points="20 4 20 11 13 11" />
      </svg>
      Quét lại
    </Button>
  );
}

/** Theo dõi một lượt quét: bắt đầu, hỏi tiến độ mỗi giây, gọi `onDone` khi lượt quét kết thúc. */
export function useScanJob(initial: ScanProgress, onDone: (p: ScanProgress) => void) {
  const [progress, setProgress] = useState<ScanProgress>(initial);
  const [error, setError] = useState<string | null>(null);
  const done = useRef(onDone);
  useEffect(() => {
    done.current = onDone;
  }, [onDone]);

  useEffect(() => {
    if (!progress.running) return;
    const ctl = new AbortController();
    const t = setTimeout(() => {
      getScanStatus(ctl.signal)
        .then((p) => {
          setProgress(p);
          if (!p.running) done.current(p);
        })
        .catch((err: unknown) => {
          if (err instanceof ApiError) setError(err.message);
        });
    }, POLL_MS);
    return () => {
      clearTimeout(t);
      ctl.abort();
    };
  }, [progress]);

  async function start() {
    setError(null);
    try {
      setProgress(await startScan());
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setProgress(await getScanStatus()); // lượt quét khác đang chạy: theo dõi lượt đó
      } else {
        setError(err instanceof ApiError ? err.message : "Không bắt đầu quét được.");
      }
    }
  }

  async function stop() {
    try {
      setProgress(await stopScan());
    } catch {
      /* lượt quét vừa kết thúc */
    }
  }

  return { progress, error, start, stop };
}

export function ScanProgressCard({ progress, onStop }: { progress: ScanProgress; onStop: () => void }) {
  const pct = progress.total ? Math.round((progress.done / progress.total) * 100) : 0;
  const [stopping, setStopping] = useState(false);
  return (
    <div role="status" className="flex flex-col gap-2.5 rounded-xl border border-line bg-surface p-4">
      <div className="flex items-center gap-2">
        <span className="font-semibold">{stopping ? "Đang dừng…" : "Đang quét"}</span>
        <span className="ml-auto font-mono text-fg-2">{progress.done} / {progress.total || "…"}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-sunken" aria-hidden="true">
        <div className="h-full bg-pos transition-[width] duration-500" style={{ width: `${pct}%` }} />
      </div>
      <div className="text-[13px] text-muted">
        {progress.waiting ?? <>Cập nhật giá và phân tích từng mã · {eta(progress.eta_s)}{progress.current && <> · đang làm <span className="font-mono text-fg-2">{progress.current}</span></>}</>}
      </div>
      {progress.failed.length > 0 && (
        <div className="text-[13px] text-event">{progress.failed.length} mã có lỗi, sẽ ghi rõ trong kết quả.</div>
      )}
      <div className="flex justify-end">
        <Button variant="ghost" disabled={stopping} onClick={() => { setStopping(true); onStop(); }} className="h-10">Dừng</Button>
      </div>
    </div>
  );
}
