import { nextTick, onMounted, onUnmounted, ref, watch } from "vue";

/** 与 sider-menu.css 中指示条 inset 保持一致 */
function readMenuGlassInset(contentEl) {
  const collapsed = contentEl.classList.contains("n-menu-item-content--collapsed");
  if (collapsed) {
    return { top: 1, right: 6, bottom: 1, left: 6 };
  }
  return { top: 1, right: 4, bottom: 1, left: 0 };
}

/**
 * 侧栏选中玻璃指示条 — 固定左右边距，仅纵向滑动；点击时立即跟随，避免等路由后再动。
 */
export function useSiderMenuIndicator(wrapRef, { activeKey, collapsed, expandedKeys }) {
  const indicatorStyle = ref({
    opacity: "0",
    transform: "translate3d(0, 0, 0)",
    height: "0px",
  });

  let ro = null;
  let scrollEl = null;
  let measureRaf = 0;

  function applyIndicatorFromContent(contentEl) {
    const wrap = wrapRef.value;
    if (!wrap || !contentEl) return;

    const inset = readMenuGlassInset(contentEl);
    const wrapRect = wrap.getBoundingClientRect();
    const itemRect = contentEl.getBoundingClientRect();
    const top = itemRect.top - wrapRect.top + inset.top;
    const height = itemRect.height - inset.top - inset.bottom;

    indicatorStyle.value = {
      opacity: height > 0 ? "1" : "0",
      transform: `translate3d(0, ${Math.round(top)}px, 0)`,
      height: `${Math.max(0, Math.round(height))}px`,
    };
  }

  function measure() {
    const wrap = wrapRef.value;
    if (!wrap) return;

    const selected = wrap.querySelector(
      ".n-menu-item-content.n-menu-item-content--selected",
    );
    if (!selected) {
      indicatorStyle.value = {
        opacity: "0",
        transform: "translate3d(0, 0, 0)",
        height: "0px",
      };
      return;
    }

    applyIndicatorFromContent(selected);
  }

  function scheduleMeasure() {
    if (measureRaf) cancelAnimationFrame(measureRaf);
    measureRaf = requestAnimationFrame(() => {
      measureRaf = 0;
      measure();
    });
  }

  function moveIndicatorToContent(contentEl) {
    if (measureRaf) {
      cancelAnimationFrame(measureRaf);
      measureRaf = 0;
    }
    applyIndicatorFromContent(contentEl);
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
    nextTick(scheduleMeasure);
    bindScrollTarget();
    ro = new ResizeObserver(scheduleMeasure);
    if (wrapRef.value) {
      ro.observe(wrapRef.value);
    }
    window.addEventListener("resize", scheduleMeasure, { passive: true });
  });

  onUnmounted(() => {
    if (measureRaf) cancelAnimationFrame(measureRaf);
    ro?.disconnect();
    scrollEl?.removeEventListener("scroll", scheduleMeasure);
    window.removeEventListener("resize", scheduleMeasure);
  });

  watch(activeKey, scheduleMeasure);
  watch(collapsed, scheduleMeasure);
  if (expandedKeys) {
    watch(expandedKeys, scheduleMeasure, { deep: true });
  }

  return { indicatorStyle, refresh: scheduleMeasure, moveIndicatorToContent };
}
