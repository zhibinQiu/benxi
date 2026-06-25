import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import Components from "unplugin-vue-components/vite";
import { NaiveUiResolver } from "unplugin-vue-components/resolvers";
import { fileURLToPath, URL } from "node:url";

const APP_BASE = process.env.VITE_BASE_PATH || "/ai/";
/** Docker dev：compose.dev 中设 VITE_DEV_API_TARGET=http://api:8000 */
const API_TARGET = process.env.VITE_DEV_API_TARGET || "http://127.0.0.1:8000";
/** 容器内 process.env 有时进不了 import.meta.env，开发模式在此显式注入 */
const VITE_API_BASE =
  (process.env.VITE_API_BASE || "").trim() ||
  (process.env.NODE_ENV === "production" ? "/ai" : "http://127.0.0.1:18000");

const platformSpinPath = fileURLToPath(
  new URL("./src/components/PlatformSpin.vue", import.meta.url)
);

/** 设计系统内嵌路径（须与 platform EMBED 配置一致，且勿与平台前端路由冲突） */
const DESIGN_SYSTEM_PATH_RE =
  /^\/ai\/(?:smart-data-query|retrieval|_next)(?:\/|$)/;

function isDesignSystemProxyPath(url) {
  const pathname = (url || "").split("?")[0];
  if (pathname.startsWith("/ai/api")) return false;
  return DESIGN_SYSTEM_PATH_RE.test(pathname);
}

/** NSpin 统一替换为 Rose Three；其余 naive-ui 组件按需解析 */
function platformNaiveResolver() {
  return {
    type: "component",
    resolve: (name) => {
      if (name === "NSpin") {
        return { name: "default", from: platformSpinPath, as: "NSpin" };
      }
    },
  };
}

export default defineConfig({
  base: APP_BASE,
  resolve: {
    alias: {
      // 显式 `import { NSpin } from "naive-ui"` 也走玫瑰加载动画
      "naive-ui/es/spin/src/Spin.mjs": platformSpinPath,
      "naive-ui/es/_internal/loading/src/Loading.mjs": fileURLToPath(
        new URL("./src/integrations/naive-base-loading.js", import.meta.url)
      ),
    },
  },
  define: {
    "import.meta.env.VITE_API_BASE": JSON.stringify(VITE_API_BASE),
  },
  plugins: [
    vue(),
    Components({
      resolvers: [platformNaiveResolver(), NaiveUiResolver()],
      dts: false,
    }),
  ],
  build: {
    target: "es2020",
    cssCodeSplit: true,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return;
          if (id.includes("echarts")) return "echarts";
          if (id.includes("mermaid")) return "mermaid";
          if (id.includes("pdfjs-dist")) return "pdfjs";
          if (id.includes("mammoth")) return "mammoth";
          if (id.includes("@vicons")) return "vicons";
          if (id.includes("marked")) return "markdown";
          // Vue + naive-ui 须同 chunk，否则 Rollup 会生成 vue-vendor ↔ naive-ui 循环引用（TDZ 崩溃）
          if (
            id.includes("naive-ui") ||
            id.includes("/vue/") ||
            id.includes("vue-router") ||
            id.includes("@vue/") ||
            id.includes("vueuc") ||
            id.includes("vooks") ||
            id.includes("seemly") ||
            id.includes("@css-render") ||
            id.includes("treemate") ||
            id.includes("evtd")
          ) {
            return "vue-vendor";
          }
        },
      },
    },
  },
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
      "/api": {
        target: API_TARGET,
        changeOrigin: true,
        timeout: 0,
        proxyTimeout: 0,
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
