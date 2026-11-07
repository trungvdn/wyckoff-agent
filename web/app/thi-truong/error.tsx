"use client";

import { useEffect } from "react";
import { ErrorPanel } from "@/components/dashboard/ErrorPanel";

// Lỗi không lường trước khi dựng trang (lỗi API có thông báo đã được page.tsx hiển thị tại chỗ)
export default function MarketError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => console.error(error), [error]);
  return (
    <ErrorPanel
      title="Đã có lỗi khi hiển thị trang thị trường"
      message={error.digest ? `Mã lỗi: ${error.digest}` : error.message}
      onRetry={reset}
    />
  );
}
