import type { ComponentPropsWithoutRef } from "react";
import { cx } from "./Card";

type Variant = "primary" | "ghost";

const VARIANTS: Record<Variant, string> = {
  primary: "border-0 bg-pos text-on-pos hover:enabled:bg-pos-hover",
  ghost: "border border-line-strong bg-transparent text-fg hover:enabled:border-muted",
};

/** Nút cao 44px (vùng chạm tối thiểu). */
export function Button({
  variant = "primary",
  className,
  type = "button",
  ...rest
}: ComponentPropsWithoutRef<"button"> & { variant?: Variant }) {
  return (
    <button
      type={type}
      className={cx(
        "h-11 cursor-pointer rounded-lg px-[18px] text-sm font-semibold whitespace-nowrap transition-colors duration-150",
        "disabled:cursor-progress disabled:opacity-60",
        VARIANTS[variant],
        className,
      )}
      {...rest}
    />
  );
}
