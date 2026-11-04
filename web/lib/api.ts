// Gọi API FastAPI. Trên server: gọi thẳng WYCKOFF_API_URL. Trên trình duyệt: đường dẫn tương đối /api/*
// được next.config.ts chuyển tiếp (rewrite) sang FastAPI, nên không cần CORS.
import type { Analysis, AskResponse, Explanation, Timeframe } from "./types";

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
