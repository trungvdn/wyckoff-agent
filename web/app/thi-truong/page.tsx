import type { Metadata } from "next";
import { ErrorPanel } from "@/components/dashboard/ErrorPanel";
import { MarketView } from "@/components/market/MarketView";
import { ApiError, getMarket } from "@/lib/api";

export const metadata: Metadata = { title: "Thị trường" };

/** /thi-truong: xu hướng, lợi suất và mức giảm của chỉ số. Mọi số liệu tính ở server (FastAPI). */
export default async function MarketPage() {
  const result = await getMarket().catch((err: unknown) => {
    if (err instanceof ApiError) return err;
    throw err; // lỗi không lường trước -> error.tsx
  });
  if (result instanceof ApiError) {
    const title = result.status === 503 ? "Máy chủ phân tích chưa sẵn sàng" : "Không tải được dữ liệu thị trường";
    return <ErrorPanel title={title} message={result.message} />;
  }
  return <MarketView data={result} />;
}
