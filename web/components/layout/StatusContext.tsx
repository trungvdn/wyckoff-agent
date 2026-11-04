"use client";

// Trạng thái hiển thị ở pill góc phải Header. Header nằm trong layout (giữ nguyên khi đổi khung / tải lại),
// còn trang biết dữ liệu đến ngày nào -> trang đặt trạng thái qua <SetStatus />.
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type StatusState = { kind: "loading" | "ok" | "error"; text: string };

const Ctx = createContext<{ status: StatusState; setStatus: (s: StatusState) => void } | null>(null);

export function StatusProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<StatusState>({ kind: "loading", text: "Đang tải…" });
  return <Ctx.Provider value={{ status, setStatus }}>{children}</Ctx.Provider>;
}

export function useStatus() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useStatus cần nằm trong <StatusProvider>");
  return ctx;
}

export function SetStatus({ kind, text }: StatusState) {
  const { setStatus } = useStatus();
  useEffect(() => setStatus({ kind, text }), [kind, text, setStatus]);
  return null;
}
