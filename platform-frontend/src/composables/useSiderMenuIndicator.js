import { nextTick, onMounted, onUnmounted, ref, watch } from "vue";

/**
 * 侧栏选中项玻璃指示条 — 单块背景平滑移动，避免每项切换时整页闪烁。
 */
export function useSiderMenuIndicator(wrapRef, { activeKey, collapsed, expandedKeys }) {
  const indicatorStyle = ref({
    opacity: "0",
    transform: "translateY(0px)",
    height: "0px",
  });

  let ro = null;
  let scrollEl = null;

  function measure() {
    const wrap = wrapRef.value;
    if (!wrap) return;

    const selected = wrap.querySelector(
      ".n-menu-item-content.n-menu-item-content--selected",
    );
    if (!selected) {
      indicatorStyle.value = {
        opacity: "0",
        transform: "translateY(0px)",
        height: "0px",
      };
      return;
    }

    const wrapRect = wrap.getBoundingClientRect();
    const itemRect = selected.getBoundingClientRect();
    const top = itemRect.top - wrapRect.top;

    indicatorStyle.value = {
      opacity: "1",
      transform: `translate3d(0, ${top}px, 0)`,
      height: `${itemRect.height}px`,
    };
  }

  function scheduleMeasure() {
    nextTick(() => {
      requestAnimationFrame(measure);
    });
  }

  function bindScrollTarget() {
    if (!wrapRef.value) return;
    const nextScrollEl = wrapRef.value.querySelector(".sider-menu");
    if (nextScrollEl === scrollEl) return;
    scrollEl?.removeEventListener("scroll", scheduleMeasure);
    scrollEl = nextScrollEl;
    scrollEl?.addEventListener("scroll", scheduleMeasure, { passive: true });
  }

  onMounted(() => {
    scheduleMeasure();
    bindScrollTarget();
    ro = new ResizeObserver(() => {
      bindScrollTarget();
      scheduleMeasure();
    });
    if (wrapRef.value) {
      ro.observe(wrapRef.value);
    }
    window.addEventListener("resize", scheduleMeasure, { passive: true });
  });

  onUnmounted(() => {
    ro?.disconnect();
    scrollEl?.removeEventListener("scroll", scheduleMeasure);
    window.removeEventListener("resize", scheduleMeasure);
  });

  watch(activeKey, scheduleMeasure);
  watch(collapsed, scheduleMeasure);
  if (expandedKeys) {
    watch(expandedKeys, scheduleMeasure, { deep: true });
  }

  return { indicatorStyle, refresh: scheduleMeasure };
}
