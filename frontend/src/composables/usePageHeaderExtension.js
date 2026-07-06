/** KeepAlive 页面 Teleport 到顶栏：失活时禁用，避免多页操作条叠在一起 */

import { onActivated, onDeactivated, onMounted, ref } from "vue";

export function usePageHeaderExtension() {
  const headerExtensionActive = ref(false);

  onMounted(() => {
    headerExtensionActive.value = true;
  });

  onActivated(() => {
    headerExtensionActive.value = true;
  });

  onDeactivated(() => {
    headerExtensionActive.value = false;
  });

  return { headerExtensionActive };
}
