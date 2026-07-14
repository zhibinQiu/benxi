import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import Components from "unplugin-vue-components/vite";
import { NaiveUiResolver } from "unplugin-vue-components/resolvers";
import { fileURLToPath, URL } from "node:url";

const platformSpinPath = fileURLToPath(
  new URL("./src/components/PlatformSpin.vue", import.meta.url)
);
const platformBaseLoadingPath = fileURLToPath(
  new URL("./src/integrations/naive-base-loading.js", import.meta.url)
);

function naiveUiLoaderAlias() {
  const spinIndex = /naive-ui[\\/]es[\\/]spin[\\/]index\.mjs$/;
  const loadingIndex = /naive-ui[\\/]es[\\/]_internal[\\/]loading[\\/]index\.mjs$/;
  const spinSrc = /naive-ui[\\/]es[\\/]spin[\\/]src[\\/]Spin\.mjs$/;

  return {
    name: "naive-ui-loader-alias",
    enforce: "pre",
    resolveId(source, importer) {
      if (!importer) return null;
      const from = importer.replace(/\\/g, "/");
      if (source === "./src/Spin.mjs" && spinIndex.test(from)) {
        return platformSpinPath;
      }
      if (
        source === "./src/Loading.mjs" &&
        (loadingIndex.test(from) || spinSrc.test(from))
      ) {
        return platformBaseLoadingPath;
      }
      return null;
    },
  };
}

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

/** 打包时通过环境变量 VITE_MOBILE_API_BASE 指定后端地址 */
const MOBILE_API_BASE = (process.env.VITE_MOBILE_API_BASE || "").trim() || "http://127.0.0.1:18000";

export default defineConfig({
  base: "/",
  resolve: {
    alias: {
      "naive-ui/es/spin/src/Spin.mjs": platformSpinPath,
      "naive-ui/es/_internal/loading/src/Loading.mjs": platformBaseLoadingPath,
    },
  },
  define: {
    "import.meta.env.VITE_API_BASE": JSON.stringify(MOBILE_API_BASE),
  },
  plugins: [
    naiveUiLoaderAlias(),
    vue(),
    Components({
      resolvers: [platformNaiveResolver(), NaiveUiResolver()],
      dts: false,
    }),
  ],
  build: {
    outDir: "dist-mobile",
    target: "es2020",
    sourcemap: false,
    cssCodeSplit: true,
    rollupOptions: {
      input: "/index.mobile.html",
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return;
          if (id.includes("echarts")) return "echarts";
          if (id.includes("mermaid")) return "mermaid";
          if (id.includes("pdfjs-dist")) return "pdfjs";
          if (id.includes("mammoth")) return "mammoth";
          if (id.includes("@vicons")) return "vicons";
          if (id.includes("marked")) return "markdown";
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
});
