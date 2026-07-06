import { onMounted } from "vue";
import { cleanupBlockingUiArtifacts } from "../utils/blockingUiCleanup.js";

/**
 * 壳层浮层兜底：仅在 MainLayout 挂载时执行一次。
 * 路由切换清理由 router.afterEach 统一负责，业务页禁止散落调用 cleanup。
 */
export function useBlockingUiCleanup() {
  onMounted(() => {
    cleanupBlockingUiArtifacts({ aggressive: true });
  });
}
