import type { Metadata } from "next";
import { ErrorPanel } from "@/components/dashboard/ErrorPanel";
import { PortfolioView } from "@/components/portfolio/PortfolioView";
import { ApiError, getPortfolio } from "@/lib/api";

export const metadata: Metadata = { title: "Danh mục" };

/** /danh-muc: các mã đang giữ. Mọi số liệu tính ở server (FastAPI), dữ liệu lưu cục bộ. */
export default async function PortfolioPage() {
  const result = await getPortfolio().catch((err: unknown) => {
    if (err instanceof ApiError) return err;
    throw err; // lỗi không lường trước -> error.tsx
  });
  if (result instanceof ApiError) {
    const title = result.status === 503 ? "Máy chủ phân tích chưa sẵn sàng" : "Không tải được danh mục";
    return <ErrorPanel title={title} message={result.message} />;
  }
  return <PortfolioView data={result} />;
}
