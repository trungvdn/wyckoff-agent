import type { Metadata, Viewport } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import { Suspense } from "react";
import { Footer } from "@/components/layout/Footer";
import { Header } from "@/components/layout/Header";
import { Sidebar } from "@/components/layout/Sidebar";
import { StatusProvider } from "@/components/layout/StatusContext";
import "./globals.css";

// next/font tải font lúc build và tự host (không gọi Google Fonts lúc chạy)
const plexSans = IBM_Plex_Sans({
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-plex-sans",
  display: "swap",
});
const plexMono = IBM_Plex_Mono({
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "600"],
  variable: "--font-plex-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "Wyckoff Agent", template: "%s · Wyckoff Agent" },
  description: "Phân tích cổ phiếu Việt Nam theo phương pháp Wyckoff: pha, sự kiện, kịch bản và hỏi agent.",
};

export const viewport: Viewport = { themeColor: "#0B1015", colorScheme: "dark" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="vi" className={`${plexSans.variable} ${plexMono.variable}`}>
      <body>
        <StatusProvider>
          <div className="xl:flex">
            <Sidebar />
            <div id="content" className="mx-auto flex max-w-[1384px] min-w-0 flex-1 flex-col gap-4 p-4 sm:gap-5 sm:px-7 sm:pt-6 sm:pb-8">
              <Suspense fallback={<div className="h-11" />}>
                <Header />
              </Suspense>
              {children}
              <Footer />
            </div>
          </div>
        </StatusProvider>
      </body>
    </html>
  );
}
