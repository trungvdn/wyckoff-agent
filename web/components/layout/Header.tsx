"use client";

import Link from "next/link";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState, useTransition, type FormEvent } from "react";
import { cx } from "@/components/ui/Card";
import { MARKET_HREF, PORTFOLIO_HREF, SYMBOL_RE, TIMEFRAMES, UNSUPPORTED_TF_HINT, normalizeSymbol, parseTimeframe, symbolHref } from "@/lib/market";
import type { Timeframe } from "@/lib/types";
import { useStatus } from "./StatusContext";

function TickerForm({ current, tf }: { current: string; tf: Timeframe }) {
  const router = useRouter();
  const { setStatus } = useStatus();
  const [value, setValue] = useState(current);
  const [, startTransition] = useTransition();

  function submit(e: FormEvent) {
    e.preventDefault();
    const s = value.trim().toUpperCase();
    if (!SYMBOL_RE.test(s)) {
      setStatus({ kind: "error", text: "Mã gồm 3–10 ký tự chữ hoặc số" });
      return;
    }
    if (s === current) return;
    startTransition(() => router.push(symbolHref(s, tf)));
  }

  return (
    <form
      role="search"
      autoComplete="off"
      onSubmit={submit}
      className="flex h-11 w-full items-center gap-2.5 rounded-lg border border-line-strong bg-surface pr-1 pl-3.5 transition-colors focus-within:border-pos sm:w-[340px]"
    >
      <label htmlFor="ticker" className="text-[13px] text-muted">Mã</label>
      <input
        id="ticker"
        value={value}
        onChange={(e) => setValue(e.target.value.toUpperCase())}
        maxLength={10}
        spellCheck={false}
        autoCapitalize="characters"
        placeholder="VD: HPG"
        aria-describedby="ticker-hint"
        className="h-10 min-w-0 flex-1 border-0 bg-transparent font-mono text-[15px] font-semibold uppercase outline-none placeholder:font-normal placeholder:text-faint"
      />
      <button type="submit" aria-label="Phân tích mã" className="grid size-10 cursor-pointer place-items-center rounded-md text-muted hover:bg-raised hover:text-fg">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          <circle cx="11" cy="11" r="7" />
          <line x1="20" y1="20" x2="16" y2="16" />
        </svg>
      </button>
      <span id="ticker-hint" className="sr-only">Nhập mã rồi nhấn Enter. Mã DEMO dùng dữ liệu tổng hợp.</span>
    </form>
  );
}

function TimeframeNav({ symbol, tf }: { symbol: string; tf: Timeframe }) {
  const seg = "flex h-11 min-w-0 items-center justify-center rounded-lg border px-2 text-sm font-medium transition-colors sm:min-w-16 sm:px-4";
  return (
    <nav aria-label="Khung thời gian" className="grid grid-cols-4 gap-2 sm:flex">
      {TIMEFRAMES.map((t) =>
        t.supported ? (
          <Link
            key={t.id}
            href={symbolHref(symbol, t.id as Timeframe)}
            aria-current={t.id === tf ? "page" : undefined}
            className={cx(
              seg,
              t.id === tf ? "border-pos bg-pos font-semibold text-on-pos" : "border-line-strong bg-surface text-fg hover:border-muted",
            )}
          >
            {t.label}
          </Link>
        ) : (
          <button key={t.id} type="button" disabled title={UNSUPPORTED_TF_HINT} className={cx(seg, "cursor-not-allowed border-dashed border-line-strong bg-surface text-faint")}>
            {t.label}
          </button>
        ),
      )}
    </nav>
  );
}

export function StatusPill() {
  const { status } = useStatus();
  const dot = { loading: "bg-event motion-safe:animate-blink", ok: "bg-pos", error: "bg-neg" }[status.kind];
  return (
    <div role="status" className="flex min-h-8 items-center gap-2 self-start rounded-full border border-line-strong px-3 text-[13px] text-muted sm:ml-auto sm:self-auto">
      <span className={cx("size-2 flex-none rounded-full", dot)} />
      <span>{status.text}</span>
    </div>
  );
}

/** Thanh trên nội dung: ô mã (trừ trang thị trường), khung thời gian (chỉ ở trang cổ phiếu), trạng thái. Đọc mã / khung từ URL. */
export function Header() {
  const params = useParams<{ symbol?: string }>();
  const search = useSearchParams();
  const pathname = usePathname();
  if (pathname === PORTFOLIO_HREF) return null; // trang danh mục tự có hàng tiêu đề, gồm pill trạng thái
  const symbol = params.symbol ? normalizeSymbol(params.symbol) : "";
  const tf = parseTimeframe(search.get("tf") ?? undefined);
  return (
    <header className="flex flex-col items-stretch gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:gap-4">
      {pathname !== MARKET_HREF && <TickerForm key={symbol} current={symbol} tf={tf} />} {/* key: đặt lại ô nhập khi đổi mã (kể cả Back / Forward) */}
      {symbol && <TimeframeNav symbol={symbol} tf={tf} />}
      <StatusPill />
    </header>
  );
}
