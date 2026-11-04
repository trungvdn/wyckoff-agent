import type { ComponentPropsWithoutRef, ReactNode } from "react";

function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

type CardProps = ComponentPropsWithoutRef<"section"> & {
  /** id của tiêu đề, dùng cho aria-labelledby */
  labelledBy?: string;
};

/** Khối nội dung chuẩn của dashboard: nền surface, viền, bo 12px, padding 20px (16px trên điện thoại). */
export function Card({ labelledBy, className, children, ...rest }: CardProps) {
  return (
    <section
      aria-labelledby={labelledBy}
      className={cx(
        "relative flex min-w-0 flex-col gap-3 rounded-xl border border-line bg-surface p-4 sm:p-5",
        className,
      )}
      {...rest}
    >
      {children}
    </section>
  );
}

/** Dòng đầu thẻ: tiêu đề (eyebrow) bên trái, phần phụ bên phải; xuống dòng khi hẹp. */
export function CardHeader({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx("flex flex-wrap items-center justify-between gap-3", className)}>{children}</div>;
}

/** Tiêu đề nhỏ in hoa của thẻ. */
export function Eyebrow({ id, children }: { id?: string; children: ReactNode }) {
  return (
    <h2 id={id} className="m-0 text-xs font-semibold tracking-[0.08em] text-muted uppercase">
      {children}
    </h2>
  );
}

export { cx };
