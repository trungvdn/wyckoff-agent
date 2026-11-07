"use client";

import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { cx } from "@/components/ui/Card";
import { MARKET_HREF, PORTFOLIO_HREF, STOCKS_HREF } from "@/lib/market";

const ICON = { width: 18, height: 18, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true } as const;

function NavItem({ href, active, icon, children }: { href: string; active: boolean; icon: ReactNode; children: ReactNode }) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cx(
        "flex h-11 items-center justify-center gap-2 rounded-lg px-3 transition-colors xl:justify-start xl:gap-3",
        active ? "bg-pos-soft font-semibold text-pos-hover" : "font-medium text-fg-2 hover:bg-raised hover:text-fg",
      )}
    >
      <span className="flex max-sm:hidden">{icon}</span>
      {children}
    </Link>
  );
}

/** Menu trang: cột trái khi rộng từ 1280px, dưới mức đó thành logo và hai tab ở đầu trang. */
export function Sidebar() {
  const pathname = usePathname();
  const { symbol } = useParams<{ symbol?: string }>();
  return (
    <aside className="flex flex-col gap-3 border-line bg-sunken p-4 sm:px-7 sm:pt-6 sm:pb-0 xl:sticky xl:top-0 xl:h-screen xl:w-[220px] xl:flex-none xl:gap-6 xl:border-r xl:px-4 xl:py-6">
      <a
        href={symbol ? "#ask-question" : "#content"}
        className="absolute top-2 -left-[9999px] z-10 rounded-lg bg-pos px-3 py-2 text-on-pos focus:left-2"
      >
        {symbol ? "Bỏ qua tới ô hỏi agent" : "Bỏ qua tới nội dung"}
      </a>
      <Link href="/" className="flex min-h-11 items-center gap-2.5 rounded-md text-pos xl:px-2" aria-label="Wyckoff Agent – trang chủ">
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <polyline points="3 17 9 11 13 15 21 7" />
          <polyline points="15 7 21 7 21 13" />
        </svg>
        <span className="text-[19px] font-bold tracking-tight text-fg">Wyckoff Agent</span>
      </Link>
      <nav aria-label="Trang" className="grid grid-cols-3 gap-1 sm:max-w-[480px] xl:max-w-none xl:grid-cols-1">
        <NavItem
          href={MARKET_HREF}
          active={pathname === MARKET_HREF}
          icon={<svg {...ICON}><line x1="4" y1="20" x2="20" y2="20" /><polyline points="4 15 9 10 13 13 20 6" /></svg>}
        >
          Thị trường
        </NavItem>
        <NavItem
          href={PORTFOLIO_HREF}
          active={pathname === PORTFOLIO_HREF}
          icon={<svg {...ICON}><rect x="3" y="8" width="18" height="12" rx="2" /><path d="M9 8V6a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2" /></svg>}
        >
          Danh mục
        </NavItem>
        <NavItem
          href={STOCKS_HREF}
          active={pathname.startsWith(STOCKS_HREF)}
          icon={<svg {...ICON}><line x1="7" y1="3" x2="7" y2="21" /><rect x="4" y="7" width="6" height="9" rx="1" /><line x1="17" y1="3" x2="17" y2="21" /><rect x="14" y="10" width="6" height="7" rx="1" /></svg>}
        >
          Cổ phiếu
        </NavItem>
      </nav>
    </aside>
  );
}
