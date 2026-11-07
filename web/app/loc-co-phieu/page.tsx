import type { Metadata } from "next";
import { ErrorPanel } from "@/components/dashboard/ErrorPanel";
import { ScreenerView } from "@/components/screener/ScreenerView";
import { ApiError, getFilters, getScan } from "@/lib/api";

export const metadata: Metadata = { title: "Lọc cổ phiếu" };

/** /loc-co-phieu: lọc theo kết quả quét đã lưu. Quét ở server (FastAPI), lọc ở trình duyệt. */
export default async function ScreenerPage() {
  const result = await Promise.all([getScan(), getFilters()]).catch((err: unknown) => {
    if (err instanceof ApiError) return err;
    throw err; // lỗi không lường trước -> error.tsx
  });
  if (result instanceof ApiError) {
    const title = result.status === 503 ? "Máy chủ phân tích chưa sẵn sàng" : "Không tải được kết quả quét";
    return <ErrorPanel title={title} message={result.message} />;
  }
  const [scan, saved] = result;
  return <ScreenerView data={scan} saved={saved} />;
}
