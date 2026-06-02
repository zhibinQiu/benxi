import { nextTick, onBeforeUnmount, onMounted, ref } from "vue";

/**
 * 根据元素距视口顶部的距离计算可滚动区域高度（避免 flex 链失效时无法滚动）。
 * @param {number} bottomGap 距视口底部的留白 px
 */
export function useBoundedScrollHeight(bottomGap = 12) {
  const anchorRef = ref(null);
  const scrollHeight = ref(400);

  function measure() {
    const el = anchorRef.value;
    if (!el || typeof window === "undefined") return;
    const top = el.getBoundingClientRect().top;
    scrollHeight.value = Math.max(180, Math.floor(window.innerHeight - top - bottomGap));
  }

  let ro = null;

  onMounted(async () => {
    await nextTick();
    measure();
    window.addEventListener("resize", measure);
    if (typeof ResizeObserver !== "undefined") {
      ro = new ResizeObserver(() => measure());
      ro.observe(document.documentElement);
    }
  });

  onBeforeUnmount(() => {
    window.removeEventListener("resize", measure);
    ro?.disconnect();
  });

  return { anchorRef, scrollHeight, remeasure: measure };
}
