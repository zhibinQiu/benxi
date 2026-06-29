import { onMounted, watch } from "vue";
import { useRoute } from "vue-router";
import { cleanupBlockingUiArtifacts } from "../utils/blockingUiCleanup.js";

/** 主布局：挂载与路由切换时清理 Naive 残留遮罩 */
export function useBlockingUiCleanup() {
  const route = useRoute();

  onMounted(() => {
    cleanupBlockingUiArtifacts({ aggressive: true });
  });

  watch(
    () => route.fullPath,
    () => {
      cleanupBlockingUiArtifacts({ aggressive: true });
    },
  );

  function cleanupOnInteraction() {
    cleanupBlockingUiArtifacts();
  }

  return { cleanupOnInteraction };
}
