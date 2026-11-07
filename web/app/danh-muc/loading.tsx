import { SetStatus } from "@/components/layout/StatusContext";
import { PortfolioBarLoading } from "@/components/portfolio/PortfolioView";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";

// Khung giữ chỗ cùng bố cục với PortfolioView
export default function Loading() {
  return (
    <>
      <SetStatus kind="loading" text="Đang tải danh mục…" />
      <PortfolioBarLoading />
      <main aria-busy="true" className="flex flex-col gap-4 sm:gap-5">
        <div className="grid grid-cols-2 gap-3 sm:gap-5 wide:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Card key={i}>
              <Skeleton />
              <Skeleton className="h-7 w-2/3" />
            </Card>
          ))}
        </div>
        <Card><Skeleton /><Skeleton /></Card>
        <Card><Skeleton /><Skeleton /><Skeleton /><Skeleton /><Skeleton /></Card>
      </main>
    </>
  );
}
