import type { NextConfig } from "next";

const API_URL = process.env.WYCKOFF_API_URL || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  // Chỉ bật khi build Docker (web/Dockerfile); build thường trên máy phát triển giữ nguyên
  output: process.env.NEXT_OUTPUT_STANDALONE ? "standalone" : undefined,
  // Mặc định rewrite ngắt sau 30 giây, ngắn hơn một lần gọi LLM (tối đa 120 giây, có thể thử lại 1 lần)
  experimental: { proxyTimeout: 250_000 },
  // Trình duyệt gọi /api/* cùng origin; Next chuyển tiếp sang FastAPI (wyckoff/web/app.py)
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "same-origin" },
          { key: "X-Frame-Options", value: "DENY" },
        ],
      },
    ];
  },
};

export default nextConfig;
