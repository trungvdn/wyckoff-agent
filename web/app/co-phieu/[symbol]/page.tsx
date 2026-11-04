import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";
import { Dashboard } from "@/components/dashboard/Dashboard";
import { ErrorPanel } from "@/components/dashboard/ErrorPanel";
import { ApiError, getAnalysis } from "@/lib/api";
import { SYMBOL_RE, normalizeSymbol, parseTimeframe, symbolHref } from "@/lib/market";

type Props = {
  params: Promise<{ symbol: string }>;
  searchParams: Promise<{ tf?: string | string[] }>;
};

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const symbol = normalizeSymbol((await params).symbol);
  return SYMBOL_RE.test(symbol) ? { title: symbol } : {};
}

/** /co-phieu/HPG (khung ngày) và /co-phieu/HPG?tf=1W (khung tuần). Phân tích chạy trên server (FastAPI). */
export default async function StockPage({ params, searchParams }: Props) {
  const raw = (await params).symbol;
  const symbol = normalizeSymbol(raw);
  const { tf: tfRaw } = await searchParams;
  const tf = parseTimeframe(tfRaw);

  if (!SYMBOL_RE.test(symbol)) notFound();
  // Một URL chuẩn cho mỗi mã / khung: chữ hoa, bỏ ?tf=1D và tf không hợp lệ
  if (raw !== symbol || (tfRaw !== undefined && tfRaw !== "1W")) redirect(symbolHref(symbol, tf));

  const result = await getAnalysis(symbol, tf).catch((err: unknown) => {
    if (err instanceof ApiError) return err;
    throw err; // lỗi không lường trước -> error.tsx
  });
  if (result instanceof ApiError) {
    const title = result.status === 503 ? "Máy chủ phân tích chưa sẵn sàng" : `Không phân tích được ${symbol}`;
    return <ErrorPanel title={title} message={result.message} />;
  }
  // key: đổi mã / khung -> dựng lại toàn bộ (xóa lịch sử chat, diễn giải cũ)
  return <Dashboard key={`${symbol}-${tf}`} data={result} />;
}
