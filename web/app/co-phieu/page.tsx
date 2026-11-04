import { redirect } from "next/navigation";
import { DEFAULT_SYMBOL, symbolHref } from "@/lib/market";

// "/co-phieu" (thiếu mã) -> mã mặc định
export default function StocksIndex() {
  redirect(symbolHref(DEFAULT_SYMBOL));
}
