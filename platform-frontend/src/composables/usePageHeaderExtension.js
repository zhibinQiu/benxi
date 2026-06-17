/** KeepAlive 页面 Teleport 到顶栏：失活时禁用，避免多页操作条叠在一起 */

import { nextTick, onActivated, onDeactivated, onMounted, ref } from "vue";

export function usePageHeaderExtension() {
  const headerExtensionActive = ref(false);

  function activateHeaderExtension() {
    headerExtensionActive.value = true;
  }

  onMounted(() => {
    nextTick(activateHeaderExtension);
  });

  onActivated(() => {
    nextTick(activateHeaderExtension);
  });

  onDeactivated(() => {
    headerExtensionActive.value = false;
  });

  return { headerExtensionActive };
}
