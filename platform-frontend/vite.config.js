import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5174,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      // 同源代理 KnowFlow Web UI（阶段 2 SSO），见 docs/zh/development/doc-platform.md
      "/ragflow-ui": {
        target: "http://127.0.0.1:9380",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/ragflow-ui/, ""),
      },
      // 设计系统 — 页面与 /ai/_next 静态资源须同源反代（智能问数、双碳问答）
      "/ai": {
        target: process.env.DESIGN_SYSTEM_UPSTREAM || "http://172.19.134.45:40001",
        changeOrigin: true,
      },
      "/design-system-ui": {
        target: process.env.DESIGN_SYSTEM_UPSTREAM || "http://172.19.134.45:40001",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/design-system-ui/, ""),
      },
      // 智能预测 Streamlit
      "/smart-forecast-ui": {
        target: process.env.SMART_FORECAST_UPSTREAM || "http://127.0.0.1:8501",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/smart-forecast-ui/, ""),
        ws: true,
      },
    },
  },
});
