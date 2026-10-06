// Vite 设置。开发时网页在 http://localhost:5173，/api 的请求由 Vite 转给 FastAPI（127.0.0.1:8000）。
// 这样浏览器只看到一个网址（同一个 origin），SameSite=Strict 的登录 cookie 才会被带上。
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    // 只在自己电脑上用：不要改成 0.0.0.0（网页里有病人资料）
    host: "localhost",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
  build: {
    // 上线的网页不附上 source map（不需要把原始码送给浏览器）
    sourcemap: false,
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});
