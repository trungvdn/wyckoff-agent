import Link from "next/link";
import { SetStatus } from "@/components/layout/StatusContext";
import { Card } from "@/components/ui/Card";
import { DEFAULT_SYMBOL, symbolHref } from "@/lib/market";

export default function NotFound() {
  return (
    <>
      <SetStatus kind="error" text="Không tìm thấy trang" />
      <Card className="items-center py-16 text-center">
        <p className="m-0 text-lg font-semibold">Không tìm thấy trang</p>
        <p className="m-0 max-w-xl leading-relaxed text-fg-2">
          Mã cổ phiếu gồm 3–10 ký tự chữ hoặc số, ví dụ HPG. Nhập mã ở ô phía trên hoặc mở mã mặc định.
        </p>
        <Link href={symbolHref(DEFAULT_SYMBOL)} className="mt-2 flex h-11 items-center rounded-lg bg-pos px-[18px] font-semibold text-on-pos hover:bg-pos-hover">
          Xem {DEFAULT_SYMBOL}
        </Link>
      </Card>
    </>
  );
}
