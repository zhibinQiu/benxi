import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

const APP_BASE = process.env.VITE_BASE_PATH || "/ai/";

/** 设计系统内嵌路径（须与 platform EMBED 配置一致，且勿与平台前端路由冲突） */
const DESIGN_SYSTEM_PATH_RE =
  /^\/ai\/(?:smart-data-query|retrieval|_next)(?:\/|$)/;

function isDesignSystemProxyPath(url) {
  const pathname = (url || "").split("?")[0];
  if (pathname.startsWith("/ai/api")) return false;
  return DESIGN_SYSTEM_PATH_RE.test(pathname);
}

export default defineConfig({
  base: APP_BASE,
  plugins: [vue()],
  server: {
    port: 40005,
    proxy: {
      // 平台 API（网关统一 /ai/api → 后端 /api）
      "/ai/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/ai/, ""),
      },
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      // 同源代理 KnowFlow Web UI（阶段 2 SSO），见 docs/zh/development/doc-platform.md
      // 同源反代 KnowFlow，并在 HTML 注入 platform-branding（见 embed-proxy/knowflow）
      "/ragflow-ui": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/ragflow-ui/, "/api/v1/embed-proxy/knowflow"),
      },
      // 设计系统 — 仅反代内嵌子路径；其余 /ai/* 由 Vite 平台前端处理
      "/ai": {
        target: process.env.DESIGN_SYSTEM_UPSTREAM || "http://172.19.134.45:40001",
        changeOrigin: true,
        bypass(req) {
          if (!isDesignSystemProxyPath(req.url)) {
            return req.url;
          }
        },
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
