"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { SetStatus } from "@/components/layout/StatusContext";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { DEFAULT_SYMBOL, symbolHref } from "@/lib/market";

/** Trạng thái lỗi chiếm chỗ dashboard: thông báo + Thử lại (+ về mã mặc định). */
export function ErrorPanel({ title, message, onRetry, status = "Không tải được dữ liệu" }: {
  title: string;
  message: string;
  onRetry?: () => void;
  status?: string;
}) {
  const router = useRouter();
  return (
    <>
      <SetStatus kind="error" text={status} />
      <Card className="items-center py-16 text-center">
        <div role="alert" className="flex max-w-xl flex-col items-center gap-3">
          <p className="m-0 text-lg font-semibold">{title}</p>
          <p className="m-0 leading-relaxed text-fg-2">{message}</p>
          <div className="mt-2 flex flex-wrap justify-center gap-2.5">
            <Button variant="ghost" onClick={onRetry ?? (() => router.refresh())}>Thử lại</Button>
            <Link href={symbolHref(DEFAULT_SYMBOL)} className="flex h-11 items-center rounded-lg px-[18px] font-semibold text-pos hover:text-pos-hover">
              Xem {DEFAULT_SYMBOL}
            </Link>
          </div>
        </div>
      </Card>
    </>
  );
}
