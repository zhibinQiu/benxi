import { ref, toValue, watch } from "vue";

/**
 * Naive UI Modal 依赖 VLazyTeleport：首次打开后 Teleport 会常驻 body。
 * 须在离场动画结束后卸载 n-modal（v-if），否则遮罩可能残留并挡住页面点击。
 *
 * @param {import('vue').MaybeRefOrGetter<boolean>} showSource
 */
export function useModalLifecycle(showSource) {
  const mounted = ref(false);

  watch(
    () => toValue(showSource),
    (visible) => {
      if (visible) mounted.value = true;
    },
    { immediate: true },
  );

  function onAfterLeave() {
    mounted.value = false;
  }

  return { mounted, onAfterLeave };
}
