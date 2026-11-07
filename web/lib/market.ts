// Quy ước dùng chung giữa server và client: mã cổ phiếu, khung thời gian, đường dẫn.
import type { Timeframe } from "./types";

export const SYMBOL_RE = /^[A-Z0-9]{3,10}$/;
export const DEFAULT_SYMBOL = process.env.NEXT_PUBLIC_DEFAULT_SYMBOL || "HPG";
export const MARKET_HREF = "/thi-truong";
export const PORTFOLIO_HREF = "/danh-muc";
export const STOCKS_HREF = "/co-phieu";
export const SCREENER_HREF = "/loc-co-phieu";

export const TIMEFRAMES: { id: string; label: string; supported: boolean }[] = [
  { id: "15m", label: "15 phút", supported: false },
  { id: "1H", label: "Giờ", supported: false },
  { id: "1D", label: "Ngày", supported: true },
  { id: "1W", label: "Tuần", supported: true },
];

export const UNSUPPORTED_TF_HINT = "Chưa hỗ trợ: chưa có dữ liệu trong ngày và ngưỡng hiệu chỉnh";

export function parseTimeframe(raw: string | string[] | undefined): Timeframe {
  return raw === "1W" ? "1W" : "1D";
}

export function normalizeSymbol(raw: string): string {
  return decodeURIComponent(raw).trim().toUpperCase();
}

export function symbolHref(symbol: string, tf: Timeframe = "1D"): string {
  return tf === "1D" ? `/co-phieu/${symbol}` : `/co-phieu/${symbol}?tf=${tf}`;
}
