/** KeepAlive 页面 Teleport 到顶栏：失活时禁用，避免多页操作条叠在一起 */

import { onActivated, onDeactivated, ref } from "vue";

export function usePageHeaderExtension() {
  const headerExtensionActive = ref(true);

  onActivated(() => {
    headerExtensionActive.value = true;
  });

  onDeactivated(() => {
    headerExtensionActive.value = false;
  });

  return { headerExtensionActive };
}
