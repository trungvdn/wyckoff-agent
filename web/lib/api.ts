// Gọi API FastAPI. Trên server: gọi thẳng WYCKOFF_API_URL. Trên trình duyệt: đường dẫn tương đối /api/*
// được next.config.ts chuyển tiếp (rewrite) sang FastAPI, nên không cần CORS.
import type { Analysis, AskResponse, Explanation, HoldingFields, MarketOverview, Portfolio, RuleItem, Timeframe } from "./types";

export const API_URL = process.env.WYCKOFF_API_URL || "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, { ...init, headers: { Accept: "application/json", ...init?.headers } });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") throw err;
    throw new ApiError("Không kết nối được máy chủ phân tích. Kiểm tra `python serve.py` đã chạy chưa.", 503);
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    let msg = body?.detail;
    if (Array.isArray(msg)) msg = msg.map((d: { msg: string }) => d.msg).join("; ");
    throw new ApiError(msg || `Lỗi máy chủ (${res.status})`, res.status);
  }
  return body as T;
}

const base = () => (typeof window === "undefined" ? API_URL : "");
const enc = encodeURIComponent;

export function getAnalysis(symbol: string, tf: Timeframe, opts: { refresh?: boolean; signal?: AbortSignal } = {}) {
  const q = `tf=${tf}${opts.refresh ? "&refresh=true" : ""}`;
  return request<Analysis>(`${base()}/api/analysis/${enc(symbol)}?${q}`, { cache: "no-store", signal: opts.signal });
}

export function getMarket() {
  return request<MarketOverview>(`${base()}/api/market`, { cache: "no-store" });
}

export function getPortfolio() {
  return request<Portfolio>(`${base()}/api/portfolio`, { cache: "no-store" });
}

const jsonBody = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export function addHolding(symbol: string, fields: HoldingFields) {
  return request<unknown>(`${base()}/api/portfolio`, jsonBody("POST", { symbol, ...fields }));
}

export function updateHolding(symbol: string, fields: HoldingFields) {
  return request<unknown>(`${base()}/api/portfolio/${enc(symbol)}`, jsonBody("PUT", fields));
}

export function deleteHolding(symbol: string) {
  return request<unknown>(`${base()}/api/portfolio/${enc(symbol)}`, { method: "DELETE" });
}

export function addRule(symbol: string, kind: string, value: number | null, side: RuleItem["side"], sufficient: boolean) {
  return request<unknown>(`${base()}/api/rules`, jsonBody("POST", { symbol, kind, value, side, sufficient }));
}

export function updateRule(id: number, kind: string, value: number | null, side: RuleItem["side"], sufficient: boolean) {
  return request<unknown>(`${base()}/api/rules/${id}`, jsonBody("PUT", { kind, value, side, sufficient }));
}

export function deleteRule(id: number) {
  return request<unknown>(`${base()}/api/rules/${id}`, { method: "DELETE" });
}

export function previewRule(symbol: string, kind: string, value: number | null, signal?: AbortSignal) {
  const q = new URLSearchParams({ symbol, kind, ...(value === null ? {} : { value: String(value) }) });
  return request<RuleItem>(`${base()}/api/rules/preview?${q}`, { cache: "no-store", signal });
}

export function getQuote(symbol: string, signal?: AbortSignal) {
  return request<{ symbol: string; close: number; as_of: string }>(`${base()}/api/quote/${enc(symbol)}`, { cache: "no-store", signal });
}

export function getExplanation(symbol: string, tf: Timeframe, signal?: AbortSignal) {
  return request<Explanation>(`${base()}/api/explanation/${enc(symbol)}?tf=${tf}`, { cache: "no-store", signal });
}

export function ask(symbol: string, tf: Timeframe, question: string) {
  return request<AskResponse>(`${base()}/api/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbol, timeframe: tf, question }),
  });
}
