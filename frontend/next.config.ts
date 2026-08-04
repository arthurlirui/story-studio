import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 开发模式：把 /api/* 代理到 FastAPI 后端（:8000），避免 CORS 预检开销。
  // 生产模式：前端由 FastAPI 静态托管（同源），rewrites 不生效。
  async rewrites() {
    const backend = process.env.BACKEND_URL || "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${backend}/:path*`,
      },
    ];
  },
};

export default nextConfig;
