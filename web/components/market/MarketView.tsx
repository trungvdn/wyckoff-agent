import { Banner } from "@/components/dashboard/Banner";
import { SetStatus } from "@/components/layout/StatusContext";
import { Card, cx } from "@/components/ui/Card";
import { fmtDate, fmtDateShort, fmtPct2, fmtPrice } from "@/lib/format";
import type { MarketOverview, TrendCondition, TrendKind } from "@/lib/types";
import { MarketChart } from "./MarketChart";

const INDEX_NAME: Record<string, string> = { VNINDEX: "VN-Index", HNXINDEX: "HNX-Index", UPCOMINDEX: "UPCoM-Index" };

const TREND: Record<TrendKind, { label: string; chip: string; points: string; summary: (f: string, s: string) => string }> = {
  uptrend: {
    label: "Xu hướng tăng",
    chip: "bg-pos-soft text-pos",
    points: "3 17 10 10 14 14 21 7",
    summary: (f, s) => `Đóng cửa trên ${f}, ${f} trên ${s} và ${f} đang đi lên.`,
  },
  downtrend: {
    label: "Xu hướng giảm",
    chip: "bg-neg-soft text-neg",
    points: "3 7 10 14 14 10 21 17",
    summary: (f, s) => `Đóng cửa dưới ${f}, ${f} dưới ${s} và ${f} đang đi xuống.`,
  },
  sideways: {
    label: "Đi ngang",
    chip: "bg-raised text-fg-2",
    points: "3 12 21 12",
    summary: () => "Chưa đạt đủ điều kiện của xu hướng tăng hoặc giảm.",
  },
};

const signColor = (x: number | null) => (x == null ? "text-fg" : x < 0 ? "text-neg" : x > 0 ? "text-pos" : "text-fg");

function Summary({ d, name }: { d: MarketOverview; name: string }) {
  const { kind, since, sessions, required_bars: required } = d.trend;
  const t = kind ? TREND[kind] : null;
  const [f, s] = d.sma_periods.map((p) => `SMA${p}`);
  return (
    <Card aria-label={`Tóm tắt ${name}`} className="wide:flex-row wide:flex-wrap wide:items-center wide:gap-x-10">
      <div>
        <h1 className="m-0 text-[13px] font-medium text-muted">{name}</h1>
        <div className="flex flex-wrap items-baseline gap-x-3">
          <span className="font-mono text-[30px] font-semibold tabular-nums sm:text-[32px]">{fmtPrice(d.close)}</span>
          {d.change != null && (
            <span className={cx("font-mono text-sm font-medium tabular-nums sm:text-[15px]", signColor(d.change))}>
              {d.change > 0 ? "+" : ""}{fmtPrice(d.change)} ({fmtPct2(d.change_pct)})
            </span>
          )}
        </div>
      </div>
      <div className="min-w-0 wide:flex-1">
        {t ? (
          <>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
              <span className={cx("inline-flex h-7 items-center gap-1.5 rounded-full px-3 font-semibold", t.chip)}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <polyline points={t.points} />
                </svg>
                {t.label}
              </span>
              <span className="text-[13px] text-muted">từ {fmtDate(since)} · {sessions} phiên</span>
            </div>
            <p className="m-0 mt-2 text-fg-2">{t.summary(f, s)}</p>
          </>
        ) : (
          <p className="m-0 text-fg-2">Chưa đủ dữ liệu để xác định xu hướng: cần ít nhất {required} phiên.</p>
        )}
      </div>
    </Card>
  );
}

function Tile({ title, shortTitle, value, color, note, shortNote }: { title: string; shortTitle: string; value: string; color: string; note: string; shortNote: string }) {
  return (
    <div className="min-w-0 rounded-xl border border-line bg-surface px-3.5 py-3 sm:px-5 sm:py-4">
      <div className="text-[13px] text-muted">
        <span className="sm:hidden">{shortTitle}</span>
        <span className="max-sm:hidden">{title}</span>
      </div>
      <div className={cx("font-mono text-[22px] font-semibold tabular-nums sm:text-2xl", color)}>{value}</div>
      <div className="text-xs text-faint">
        <span className="sm:hidden">{shortNote}</span>
        <span className="max-sm:hidden">{note}</span>
      </div>
    </div>
  );
}

function Tiles({ d }: { d: MarketOverview }) {
  const dd = d.drawdown;
  return (
    <section aria-label="Lợi suất và mức giảm" className="grid grid-cols-2 gap-3 sm:gap-5 wide:grid-cols-4">
      {d.returns.map((r) => (
        <Tile
          key={r.window}
          title={`Lợi suất ${r.window} phiên`}
          shortTitle={`${r.window} phiên`}
          value={fmtPct2(r.pct)}
          color={signColor(r.pct)}
          note={r.pct == null ? "Chưa đủ dữ liệu" : `từ ${fmtPrice(r.from_close)} ngày ${fmtDate(r.from_date)}`}
          shortNote={r.pct == null ? "Chưa đủ dữ liệu" : `từ ${fmtPrice(r.from_close)} · ${fmtDateShort(r.from_date)}`}
        />
      ))}
      <Tile
        title={`Giảm so với đỉnh ${dd.lookback} phiên`}
        shortTitle={`So với đỉnh ${dd.lookback} phiên`}
        value={fmtPct2(dd.pct)}
        color="text-event"
        note={`đỉnh ${fmtPrice(dd.peak)} ngày ${fmtDate(dd.peak_date)} · ${dd.sessions_since} phiên trước`}
        shortNote={`${fmtPrice(dd.peak)} · ${fmtDateShort(dd.peak_date)}`}
      />
    </section>
  );
}

function conditionDetail(c: TrendCondition): string {
  if (c.met) return `${fmtPrice(c.value)} ${c.op} ${fmtPrice(c.threshold)}${c.slope_pct != null ? ` (${fmtPct2(c.slope_pct)})` : ""}`;
  const need = `cần ${c.op} ${fmtPrice(c.threshold)}`;
  if (c.id === "close_fast") return `${need} · còn ${fmtPct2(c.gap_pct)}`;
  if (c.id === "fast_slow") return `${need} · còn ${fmtPrice(c.gap_points)} điểm`;
  return `${need} · đang ${fmtPct2(c.slope_pct)}`;
}

function ConditionsCard({ id, title, items, children }: { id: string; title: string; items: TrendCondition[]; children?: React.ReactNode }) {
  return (
    <Card labelledBy={id} className="flex-1">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id={id} className="m-0 text-sm font-semibold">{title}</h2>
        <span className="flex-none text-[13px] text-muted">đạt {items.filter((c) => c.met).length}/{items.length}</span>
      </div>
      <ul className="m-0 flex list-none flex-col gap-3 p-0">
        {items.map((c) => (
          <li key={c.id} className="grid grid-cols-[18px_1fr] gap-2.5">
            {c.met ? (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" className="mt-px stroke-fg-2" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <polyline points="5 13 10 18 19 7" />
              </svg>
            ) : (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" className="mt-px stroke-faint" strokeWidth="2" aria-hidden="true">
                <circle cx="12" cy="12" r="8" />
              </svg>
            )}
            <div className="min-w-0">
              <div>{c.label}<span className="sr-only">{c.met ? " (đạt)" : " (chưa đạt)"}</span></div>
              <div className="font-mono text-[13px] text-muted tabular-nums">{conditionDetail(c)}</div>
            </div>
          </li>
        ))}
      </ul>
      {children && <div className="border-t border-line pt-3">{children}</div>}
    </Card>
  );
}

const NOTE = "Đây là quy tắc đặt nhãn, chưa phải tín hiệu mua hoặc bán đã kiểm định. Các mức SMA thay đổi theo từng phiên.";

function Conditions({ d }: { d: MarketOverview }) {
  const c = d.conditions;
  const kind = d.trend.kind;
  if (!c || !kind) return null;
  if (kind === "sideways") {
    return (
      <>
        <ConditionsCard id="cond-up" title="Điều kiện xu hướng tăng" items={c.up} />
        <ConditionsCard id="cond-down" title="Điều kiện xu hướng giảm" items={c.down}>
          <p className="m-0 text-xs text-faint">{NOTE}</p>
        </ConditionsCard>
      </>
    );
  }
  const up = kind === "uptrend";
  return (
    <>
      <ConditionsCard id="cond-now" title={up ? "Vì sao là xu hướng tăng" : "Vì sao là xu hướng giảm"} items={up ? c.up : c.down} />
      <ConditionsCard id="cond-reverse" title={up ? "Điều kiện đảo chiều giảm" : "Điều kiện đảo chiều tăng"} items={up ? c.down : c.up}>
        <p className="m-0 text-fg-2">
          <span className="font-semibold text-fg">Mốc gần nhất:</span> đóng cửa {up ? "dưới" : "trên"} {fmtPrice(d.trend.sma_fast)} thì hết xu hướng {up ? "tăng" : "giảm"}, chuyển sang đi ngang.
        </p>
        <p className="m-0 mt-2 text-xs text-faint">{NOTE}</p>
      </ConditionsCard>
    </>
  );
}

/** Trang thị trường: tóm tắt, bốn ô số, biểu đồ ≈2/3 | điều kiện xu hướng. Một cột khi ≤ 1080px. */
export function MarketView({ data: d }: { data: MarketOverview }) {
  const name = INDEX_NAME[d.symbol] ?? d.symbol;
  return (
    <>
      <SetStatus kind="ok" text={`Dữ liệu đến ${fmtDate(d.as_of)}`} />
      <Banner notices={d.notices} warnings={[]} />
      <main className="flex flex-col gap-4 sm:gap-5">
        <Summary d={d} name={name} />
        <Tiles d={d} />
        <div className="grid grid-cols-1 gap-4 sm:gap-5 wide:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <MarketChart data={d} />
          <div className="flex min-w-0 flex-col gap-4 sm:gap-5">
            <Conditions d={d} />
          </div>
        </div>
      </main>
    </>
  );
}
