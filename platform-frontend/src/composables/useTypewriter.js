import { onMounted, onUnmounted, ref, unref, watch } from "vue";
import { prefersReducedMotion, subscribeMediaQuery } from "../utils/mediaQuery.js";

/**
 * 逐字打字机效果，支持多行轮播；单行可通过 loopSingle 循环；尊重 prefers-reduced-motion。
 */
export function useTypewriter(linesSource, options = {}) {
  const {
    charDelay = 42,
    pauseAfterLine = 2600,
    eraseDelay = 24,
    pauseBetweenLines = 320,
    rotate = true,
    loopSingle = false,
  } = options;

  const displayedText = ref("");
  const showCursor = ref(true);
  const reducedMotion = ref(false);

  let timer = null;
  let lineIndex = 0;
  let charIndex = 0;
  let phase = "typing";
  let active = true;

  function getLines() {
    const raw = unref(linesSource);
    return Array.isArray(raw) ? raw.filter(Boolean) : [];
  }

  function clearTimer() {
    if (timer != null) {
      clearTimeout(timer);
      timer = null;
    }
  }

  function schedule(fn, delay) {
    clearTimer();
    timer = setTimeout(fn, delay);
  }

  function tick() {
    if (!active) return;

    const lines = getLines();
    if (!lines.length) {
      displayedText.value = "";
      showCursor.value = false;
      return;
    }

    if (reducedMotion.value) {
      displayedText.value = lines[0];
      showCursor.value = false;
      return;
    }

    const line = lines[lineIndex] ?? "";
    const shouldRotate = rotate && (lines.length > 1 || loopSingle);

    if (phase === "typing") {
      if (charIndex < line.length) {
        charIndex += 1;
        displayedText.value = line.slice(0, charIndex);
        schedule(tick, charDelay);
        return;
      }
      if (!shouldRotate) {
        showCursor.value = true;
        return;
      }
      phase = "pause";
      schedule(tick, pauseAfterLine);
      return;
    }

    if (phase === "pause") {
      phase = "erasing";
      tick();
      return;
    }

    if (phase === "erasing") {
      if (charIndex > 0) {
        charIndex -= 1;
        displayedText.value = line.slice(0, charIndex);
        schedule(tick, eraseDelay);
        return;
      }
      lineIndex = (lineIndex + 1) % lines.length;
      phase = "typing";
      schedule(tick, pauseBetweenLines);
    }
  }

  function restart() {
    clearTimer();
    lineIndex = 0;
    charIndex = 0;
    phase = "typing";
    displayedText.value = "";
    showCursor.value = true;

    const lines = getLines();
    if (!lines.length) return;

    if (reducedMotion.value) {
      displayedText.value = lines[0];
      showCursor.value = false;
      return;
    }

    tick();
  }

  let unsubscribeMotion = null;

  function onMotionPreferenceChange() {
    reducedMotion.value = prefersReducedMotion();
    restart();
  }

  onMounted(() => {
    reducedMotion.value = prefersReducedMotion();
    unsubscribeMotion = subscribeMediaQuery("(prefers-reduced-motion: reduce)", onMotionPreferenceChange);
    restart();
  });

  onUnmounted(() => {
    active = false;
    clearTimer();
    unsubscribeMotion?.();
  });

  watch(() => getLines(), restart, { deep: true });

  return { displayedText, showCursor, reducedMotion };
}
