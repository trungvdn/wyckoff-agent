import type { NextConfig } from "next";

const API_URL = process.env.WYCKOFF_API_URL || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  poweredByHeader: false,
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
