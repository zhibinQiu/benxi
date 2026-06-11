import { onMounted, onUnmounted } from "vue";

function prefersReducedMotion() {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false;
}

function detectAdvancedLiquidGlass() {
  const ua = navigator.userAgent || "";
  const isChromium =
    /Chrome|Chromium|Edg|OPR|Brave/i.test(ua) &&
    !/Firefox|Safari/i.test(ua.replace(/Chrome[^\s]*/g, ""));
  if (isChromium) {
    document.documentElement.dataset.liquidAdvanced = "true";
  }
}

/** 驱动 Liquid Glass 全局 CSS 变量：指针位置、轻微 3D 倾斜、滚动垂坠。 */
export function useLiquidGlassMotion() {
  let raf = 0;
  let targetX = 0.5;
  let targetY = 0.38;
  let currentX = 0.5;
  let currentY = 0.38;
  let tiltX = 0;
  let tiltY = 0;
  let drape = 0;

  function lerp(from, to, amount) {
    return from + (to - from) * amount;
  }

  function applyVars() {
    const root = document.documentElement;
    root.style.setProperty("--liquid-x", currentX.toFixed(4));
    root.style.setProperty("--liquid-y", currentY.toFixed(4));
    root.style.setProperty("--liquid-tilt-x", tiltX.toFixed(4));
    root.style.setProperty("--liquid-tilt-y", tiltY.toFixed(4));
    root.style.setProperty("--liquid-drape-offset", `${drape.toFixed(2)}px`);
  }

  function tick() {
    if (document.hidden) {
      raf = requestAnimationFrame(tick);
      return;
    }
    currentX = lerp(currentX, targetX, 0.065);
    currentY = lerp(currentY, targetY, 0.065);
    applyVars();
    raf = requestAnimationFrame(tick);
  }

  function onPointerMove(event) {
    const w = window.innerWidth || 1;
    const h = window.innerHeight || 1;
    targetX = event.clientX / w;
    targetY = event.clientY / h;
    tiltX = (targetX - 0.5) * 2;
    tiltY = (targetY - 0.5) * 2;
  }

  function onScroll() {
    const max = Math.min((window.scrollY || 0) * 0.0025, 0.18);
    drape = max * 14;
    document.documentElement.style.setProperty("--liquid-scroll", max.toFixed(4));
  }

  onMounted(() => {
    detectAdvancedLiquidGlass();
    applyVars();
    onScroll();

    if (prefersReducedMotion()) return;

    window.addEventListener("pointermove", onPointerMove, { passive: true });
    window.addEventListener("scroll", onScroll, { passive: true });
    raf = requestAnimationFrame(tick);
  });

  onUnmounted(() => {
    cancelAnimationFrame(raf);
    window.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("scroll", onScroll);
  });
}
