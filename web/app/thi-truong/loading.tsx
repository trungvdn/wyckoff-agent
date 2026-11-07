import { SetStatus } from "@/components/layout/StatusContext";
import { Card, Eyebrow } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";

// Khung giữ chỗ cùng bố cục với MarketView
export default function Loading() {
  return (
    <>
      <SetStatus kind="loading" text="Đang tải dữ liệu thị trường…" />
      <main aria-busy="true" className="flex flex-col gap-4 sm:gap-5">
        <Card>
          <Skeleton className="h-9 w-48" />
          <Skeleton className="h-7 w-3/5" />
        </Card>
        <div className="grid grid-cols-2 gap-3 sm:gap-5 wide:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Card key={i}>
              <Skeleton />
              <Skeleton className="h-7 w-2/3" />
            </Card>
          ))}
        </div>
        <div className="grid grid-cols-1 gap-4 sm:gap-5 wide:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <Card>
            <Eyebrow>Biểu đồ ngày</Eyebrow>
            <Skeleton className="h-[420px] sm:h-[500px] wide:h-[560px]" />
          </Card>
          <div className="flex min-w-0 flex-col gap-4 sm:gap-5">
            <Card className="flex-1"><Skeleton /><Skeleton /><Skeleton /></Card>
            <Card className="flex-1"><Skeleton /><Skeleton /><Skeleton /></Card>
          </div>
        </div>
      </main>
    </>
  );
}
