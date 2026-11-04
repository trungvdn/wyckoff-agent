"use client";

// Diễn giải của agent (chậm: có thể gọi LLM) tải phía client sau khi dashboard đã hiện.
// Dùng chung cho thẻ Kịch bản (diễn giải từng mức giá) và khung Hỏi Agent (tin nhắn đầu tiên).
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { getExplanation } from "@/lib/api";
import type { Explanation, Timeframe } from "@/lib/types";

export type ExplanationState = { status: "loading" } | { status: "ok"; data: Explanation } | { status: "error"; message: string };

const Ctx = createContext<{ state: ExplanationState; reload: () => void }>({ state: { status: "loading" }, reload: () => {} });

export function ExplanationProvider({ symbol, tf, children }: { symbol: string; tf: Timeframe; children: ReactNode }) {
  const [nonce, setNonce] = useState(0);
  const [result, setResult] = useState<{ key: string; value: ExplanationState }>({ key: "", value: { status: "loading" } });
  const key = `${symbol}|${tf}|${nonce}`;

  useEffect(() => {
    const ctrl = new AbortController();
    getExplanation(symbol, tf, ctrl.signal)
      .then((data) => setResult({ key, value: { status: "ok", data } }))
      .catch((err: Error) => {
        if (err.name !== "AbortError") setResult({ key, value: { status: "error", message: err.message } });
      });
    return () => ctrl.abort();
  }, [symbol, tf, key]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  // Kết quả của khóa cũ (trước khi đổi mã hoặc phân tích lại) coi như đang tải
  const state: ExplanationState = result.key === key ? result.value : { status: "loading" };
  return <Ctx.Provider value={{ state, reload }}>{children}</Ctx.Provider>;
}

export const useExplanation = () => useContext(Ctx);
