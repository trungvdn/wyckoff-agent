import { DashboardSkeleton } from "@/components/dashboard/DashboardSkeleton";
import { SetStatus } from "@/components/layout/StatusContext";

// Hiện ngay khi điều hướng sang mã / khung khác, trong lúc server chạy phân tích
export default function Loading() {
  return (
    <>
      <SetStatus kind="loading" text="Đang phân tích…" />
      <DashboardSkeleton />
    </>
  );
}
