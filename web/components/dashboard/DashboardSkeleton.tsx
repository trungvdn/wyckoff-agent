import { Card, Eyebrow } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";

/** Khung giữ chỗ cùng bố cục với Dashboard, hiện ngay khi điều hướng (app/co-phieu/[symbol]/loading.tsx). */
export function DashboardSkeleton() {
  return (
    <>
      <main aria-busy="true" className="grid grid-cols-1 gap-4 sm:gap-5 wide:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Card>
          <Eyebrow>Biểu đồ giá &amp; khối lượng</Eyebrow>
          <Skeleton className="h-[400px] sm:h-[480px] wide:h-[540px]" />
        </Card>
        <div className="flex min-w-0 flex-col gap-4 sm:gap-5">
          <Card>
            <Eyebrow>Pha hiện tại</Eyebrow>
            <Skeleton className="h-[26px] w-3/5" />
            <Skeleton />
            <Skeleton />
          </Card>
          <Card className="flex-1">
            <Eyebrow>Sự kiện đã nhận diện</Eyebrow>
            <Skeleton />
            <Skeleton />
            <Skeleton />
          </Card>
        </div>
      </main>
      <div className="grid grid-cols-1 gap-4 sm:gap-5 wide:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)]">
        <Card>
          <Eyebrow>Kịch bản</Eyebrow>
          <Skeleton />
          <Skeleton />
        </Card>
        <Card>
          <Eyebrow>Hỏi Agent</Eyebrow>
          <Skeleton className="h-20" />
        </Card>
      </div>
    </>
  );
}
