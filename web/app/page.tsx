import { redirect } from "next/navigation";
import { DEFAULT_SYMBOL, symbolHref } from "@/lib/market";

// "/" -> dashboard của mã mặc định (NEXT_PUBLIC_DEFAULT_SYMBOL, mặc định HPG)
export default function Home() {
  redirect(symbolHref(DEFAULT_SYMBOL));
}
