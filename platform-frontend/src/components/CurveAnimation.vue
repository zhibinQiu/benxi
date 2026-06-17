<script setup>
import { computed, onMounted, onUnmounted, ref, useId, watch } from "vue";
import {
  buildCurvePath,
  curveConfigForBackground,
  curveConfigForInline,
  curveConfigForSize,
  getCurveDetailScale,
  getCurveParticle,
  getCurveRotation,
} from "../utils/curveAnimation.js";

const props = defineProps({
  preset: {
    type: String,
    default: "rose-three",
  },
  size: {
    type: Number,
    default: 88,
  },
  fill: {
    type: Boolean,
    default: false,
  },
  background: {
    type: Boolean,
    default: false,
  },
  inline: {
    type: Boolean,
    default: false,
  },
  rotate: {
    type: Boolean,
    default: true,
  },
  pathOpacity: {
    type: Number,
    default: 0.22,
  },
  pathSteps: {
    type: Number,
    default: 480,
  },
  phaseOffset: {
    type: Number,
    default: 0,
  },
  pauseWhenHidden: {
    type: Boolean,
    default: false,
  },
  intensity: {
    type: Number,
    default: 1,
  },
  label: {
    type: String,
    default: "",
  },
});

const rootRef = ref(null);
const measuredSize = ref(props.size);
const groupRef = ref(null);
const pathRef = ref(null);
const particleRefs = ref([]);

const gradientId = `curve-anim-${useId().replace(/:/g, "")}`;
const effectiveSize = computed(() => (props.fill ? measuredSize.value : props.size));

const animationConfig = computed(() => {
  const resolver = props.background
    ? curveConfigForBackground
    : props.inline
      ? curveConfigForInline
      : curveConfigForSize;
  return {
    ...resolver(props.preset, effectiveSize.value),
    rotate: props.rotate,
  };
});

let frameId = 0;
let startedAt = 0;
let reducedMotion = false;
let paused = false;
let resizeObserver = null;

function setParticleRef(node, index) {
  if (node) particleRefs.value[index] = node;
}

function measureSize() {
  if (!props.fill || !rootRef.value) return;
  const rect = rootRef.value.getBoundingClientRect();
  const next = Math.round(Math.max(rect.width, rect.height));
  if (next > 0) measuredSize.value = next;
}

function render(now) {
  if (!groupRef.value || !pathRef.value || paused) return;

  const time = now - startedAt + props.phaseOffset;
  const config = animationConfig.value;
  const progress = reducedMotion ? 0.18 : (time % config.durationMs) / config.durationMs;
  const detailScale = reducedMotion ? 0.72 : getCurveDetailScale(time, config);

  groupRef.value.setAttribute(
    "transform",
    reducedMotion ? "" : `rotate(${getCurveRotation(time, config)} 50 50)`
  );
  pathRef.value.setAttribute("d", buildCurvePath(detailScale, config, props.pathSteps));

  particleRefs.value.forEach((node, index) => {
    if (!node) return;
    const particle = getCurveParticle(index, progress, detailScale, config);
    node.setAttribute("cx", particle.x.toFixed(2));
    node.setAttribute("cy", particle.y.toFixed(2));
    node.setAttribute("r", particle.radius.toFixed(2));
    const opacity = reducedMotion ? 0.72 : particle.opacity * props.intensity;
    node.setAttribute("opacity", Math.min(1, opacity).toFixed(3));
  });

  if (!reducedMotion) {
    frameId = requestAnimationFrame(render);
  }
}

function startLoop() {
  if (frameId) cancelAnimationFrame(frameId);
  particleRefs.value = [];
  startedAt = performance.now();
  frameId = requestAnimationFrame(render);
}

function stopLoop() {
  if (frameId) {
    cancelAnimationFrame(frameId);
    frameId = 0;
  }
}

function onVisibilityChange() {
  if (!props.pauseWhenHidden) return;
  paused = document.hidden;
  if (paused) {
    stopLoop();
    return;
  }
  startLoop();
}

watch(effectiveSize, () => {
  if (reducedMotion) return;
  startLoop();
});

onMounted(() => {
  reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  measureSize();

  if (props.fill && rootRef.value && typeof ResizeObserver !== "undefined") {
    resizeObserver = new ResizeObserver(measureSize);
    resizeObserver.observe(rootRef.value);
  }

  if (props.pauseWhenHidden) {
    document.addEventListener("visibilitychange", onVisibilityChange);
    paused = document.hidden;
  }

  if (!paused) startLoop();
});

onUnmounted(() => {
  stopLoop();
  resizeObserver?.disconnect();
  if (props.pauseWhenHidden) {
    document.removeEventListener("visibilitychange", onVisibilityChange);
  }
});
</script>

<template>
  <div
    ref="rootRef"
    class="curve-animation"
    :class="{ 'curve-animation--fill': fill }"
    :style="fill ? undefined : { width: `${size}px`, height: `${size}px` }"
    :role="label ? 'status' : undefined"
    :aria-label="label || undefined"
    aria-hidden="true"
  >
    <svg viewBox="0 0 100 100" fill="none">
      <defs>
        <linearGradient :id="gradientId" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="var(--platform-loader-gradient-start)" />
          <stop offset="52%" stop-color="var(--platform-loader-gradient-mid)" />
          <stop offset="100%" stop-color="var(--platform-loader-gradient-end)" />
        </linearGradient>
      </defs>
      <g ref="groupRef">
        <path
          ref="pathRef"
          stroke="var(--platform-loader-path)"
          :stroke-width="animationConfig.strokeWidth"
          stroke-linecap="round"
          stroke-linejoin="round"
          :opacity="pathOpacity"
        />
        <circle
          v-for="(_, index) in animationConfig.particleCount"
          :key="index"
          :ref="(node) => setParticleRef(node, index)"
          :fill="`url(#${gradientId})`"
        />
      </g>
    </svg>
  </div>
</template>

<style scoped>
.curve-animation {
  flex-shrink: 0;
  display: grid;
  place-items: center;
  color: var(--platform-loader-color);
}

.curve-animation--fill {
  width: 100%;
  height: 100%;
}

.curve-animation svg {
  width: 100%;
  height: 100%;
  overflow: visible;
  display: block;
}
</style>
