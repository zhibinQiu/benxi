import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

const APP_BASE = process.env.VITE_BASE_PATH || "/ai/";
/** Docker dev：compose.dev 中设 VITE_DEV_API_TARGET=http://api:8000 */
const API_TARGET = process.env.VITE_DEV_API_TARGET || "http://127.0.0.1:8000";
/** 容器内 process.env 有时进不了 import.meta.env，开发模式在此显式注入 */
const VITE_API_BASE =
  (process.env.VITE_API_BASE || "").trim() ||
  (process.env.NODE_ENV === "production" ? "/ai" : "http://127.0.0.1:18000");

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
  define: {
    "import.meta.env.VITE_API_BASE": JSON.stringify(VITE_API_BASE),
  },
  plugins: [vue()],
  server: {
    host: "0.0.0.0",
    port: 40005,
    proxy: {
      // 平台 API（网关统一 /ai/api → 后端 /api）
      "/ai/api": {
        target: API_TARGET,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/ai/, ""),
        timeout: 0,
        proxyTimeout: 0,
      },
      // 须在宽泛 /api 之前，避免 KnowFlow 管理 API 被平台路由吞掉
      "/api/knowflow": {
        target: API_TARGET,
        changeOrigin: true,
        timeout: 120000,
        proxyTimeout: 120000,
        rewrite: (path) => `/api/v1/embed-proxy/knowflow${path}`,
      },
      "/api": {
        target: API_TARGET,
        changeOrigin: true,
        timeout: 0,
        proxyTimeout: 0,
      },
      // 同源代理 KnowFlow Web UI（embed-proxy SSO），见 docs/zh/operations/network-topology.md
      // 同源反代 KnowFlow，并在 HTML 注入 platform-branding（见 embed-proxy/knowflow）
      "/ragflow-ui": {
        target: API_TARGET,
        changeOrigin: true,
        timeout: 120000,
        proxyTimeout: 120000,
        rewrite: (path) => path.replace(/^\/ragflow-ui/, "/api/v1/embed-proxy/knowflow"),
      },
      // KnowFlow SPA 内 /v1/* API（与 /ragflow-ui 静态资源同源，避免 iframe 跨端口）
      "/v1": {
        target: API_TARGET,
        changeOrigin: true,
        timeout: 120000,
        proxyTimeout: 120000,
        rewrite: (path) => `/api/v1/embed-proxy/knowflow${path}`,
      },
      // 设计系统内嵌子路径（勿用宽泛 /ai，否则会吞掉 /ai/api）
      "/ai/smart-data-query": {
        target: process.env.DESIGN_SYSTEM_UPSTREAM || "http://172.19.134.45:40001",
        changeOrigin: true,
      },
      "/ai/retrieval": {
        target: process.env.DESIGN_SYSTEM_UPSTREAM || "http://172.19.134.45:40001",
        changeOrigin: true,
      },
      "/ai/_next": {
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
