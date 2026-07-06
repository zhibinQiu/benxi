<script setup>
import { computed } from "vue";
import CurveAnimation from "./CurveAnimation.vue";
import { prefersReducedMotion } from "../utils/mediaQuery.js";

const props = defineProps({
  /** 固定铺满视口（App 壳层）；否则相对父容器 absolute */
  fixed: { type: Boolean, default: false },
  /** 非首页时使用单层曲线，降低 RAF / SVG 内存占用 */
  lite: { type: Boolean, default: false },
});

const reducedMotion = computed(() => prefersReducedMotion());

const ALL_CURVE_LAYERS = [
  {
    className: "page-video-bg__curve--primary",
    phaseOffset: 0,
    intensity: 0.92,
  },
  {
    className: "page-video-bg__curve--secondary",
    phaseOffset: 1500,
    intensity: 0.72,
  },
  {
    className: "page-video-bg__curve--tertiary",
    phaseOffset: 2900,
    intensity: 0.62,
  },
];

const curveLayers = computed(() => (props.lite ? ALL_CURVE_LAYERS.slice(0, 1) : ALL_CURVE_LAYERS));
</script>

<template>
  <div
    class="page-video-bg"
    :class="{ 'page-video-bg--fixed': fixed, 'page-video-bg--static': reducedMotion }"
    aria-hidden="true"
  >
    <div v-if="!reducedMotion" class="page-video-bg__curves">
      <div
        v-for="(layer, index) in curveLayers"
        :key="index"
        class="page-video-bg__curve"
        :class="layer.className"
      >
        <CurveAnimation
          preset="rose-four"
          fill
          background
          pause-when-hidden
          :phase-offset="layer.phaseOffset"
          :intensity="layer.intensity"
          :path-opacity="0.1"
          :path-steps="props.lite ? 120 : 160"
        />
      </div>
    </div>
    <div class="page-video-bg__overlay" />
  </div>
</template>

<style scoped>
.page-video-bg {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  overflow: hidden;
}

.page-video-bg--fixed {
  position: fixed;
  inset: 0;
  z-index: 0;
}

.page-video-bg__curves {
  position: absolute;
  inset: 0;
}

.page-video-bg__curve {
  position: absolute;
  transform: translate(-50%, -50%);
  opacity: var(--page-curve-opacity, 0.46);
  filter: saturate(132%) hue-rotate(6deg);
}

.page-video-bg__curve--primary {
  top: 44%;
  left: 50%;
  width: min(58vmin, 744px);
  height: min(58vmin, 744px);
  --page-curve-opacity: 0.5;
}

.page-video-bg__curve--secondary {
  top: 16%;
  left: 80%;
  width: min(38vmin, 480px);
  height: min(38vmin, 480px);
  --page-curve-opacity: 0.34;
}

.page-video-bg__curve--tertiary {
  top: 78%;
  left: 16%;
  width: min(32vmin, 408px);
  height: min(32vmin, 408px);
  --page-curve-opacity: 0.28;
}

.page-video-bg--static .page-video-bg__overlay {
  background:
    linear-gradient(
      180deg,
      color-mix(in srgb, var(--platform-bg-base) 72%, white) 0%,
      color-mix(in srgb, var(--platform-accent-soft) 82%, white) 100%
    ),
    radial-gradient(
      ellipse 70% 55% at 18% 12%,
      color-mix(in srgb, var(--platform-accent) 14%, transparent) 0%,
      transparent 58%
    );
}

.page-video-bg__overlay {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(
      180deg,
      color-mix(in srgb, var(--platform-bg-base) 42%, white) 0%,
      color-mix(in srgb, var(--platform-accent-soft) 34%, white) 42%,
      color-mix(in srgb, var(--platform-accent-soft-2) 48%, white) 100%
    ),
    radial-gradient(
      ellipse 70% 55% at 18% 12%,
      color-mix(in srgb, var(--platform-accent) 12%, transparent) 0%,
      transparent 58%
    ),
    radial-gradient(ellipse 60% 50% at 88% 78%, color-mix(in srgb, var(--platform-accent-secondary) 16%, transparent) 0%, transparent 55%);
}

html[data-theme="dark"] .page-video-bg__overlay {
  background:
    linear-gradient(
      180deg,
      rgba(8, 10, 20, 0.58) 0%,
      rgba(12, 14, 28, 0.48) 45%,
      rgba(10, 12, 24, 0.62) 100%
    ),
    radial-gradient(
      ellipse 70% 55% at 18% 12%,
      color-mix(in srgb, var(--platform-accent) 14%, transparent) 0%,
      transparent 58%
    ),
    radial-gradient(ellipse 60% 50% at 88% 78%, color-mix(in srgb, var(--platform-accent-secondary) 20%, transparent) 0%, transparent 55%);
}

html[data-theme="dark"] .page-video-bg--static .page-video-bg__overlay {
  background:
    linear-gradient(
      180deg,
      rgba(8, 10, 20, 0.72) 0%,
      rgba(12, 14, 28, 0.82) 100%
    ),
    radial-gradient(
      ellipse 70% 55% at 18% 12%,
      color-mix(in srgb, var(--platform-accent) 14%, transparent) 0%,
      transparent 58%
    );
}

@media (prefers-reduced-motion: reduce) {
  .page-video-bg__curve {
    display: none;
  }
}
</style>
