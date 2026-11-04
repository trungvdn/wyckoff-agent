import { cx } from "./Card";

/** Khối giữ chỗ khi đang tải (shimmer; tắt khi người dùng chọn giảm chuyển động). */
export function Skeleton({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cx(
        "block rounded-md bg-linear-to-r from-raised via-line to-raised bg-size-[200%_100%] motion-safe:animate-shimmer",
        className ?? "my-1.5 h-3.5",
      )}
    />
  );
}
