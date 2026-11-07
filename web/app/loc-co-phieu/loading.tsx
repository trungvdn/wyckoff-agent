import { SetStatus } from "@/components/layout/StatusContext";
import { ScreenerBarLoading } from "@/components/screener/ScreenerView";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";

// Khung giữ chỗ cùng bố cục với ScreenerView
export default function Loading() {
  return (
    <>
      <SetStatus kind="loading" text="Đang tải kết quả quét…" />
      <ScreenerBarLoading />
      <main aria-busy="true" className="flex flex-col gap-4 wide:flex-row wide:gap-5">
        <Card className="wide:w-[310px] wide:flex-none"><Skeleton /><Skeleton /><Skeleton /></Card>
        <Card className="flex-1"><Skeleton /><Skeleton /><Skeleton /><Skeleton /><Skeleton /></Card>
      </main>
    </>
  );
}
