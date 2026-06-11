<script setup>
import { onMounted, onUnmounted, ref, computed } from "vue";
import { publicAsset } from "../utils/appBase";

const props = defineProps({
  src: { type: String, default: () => publicAsset("main.mp4") },
  /** 固定铺满视口（App 壳层）；否则相对父容器 absolute */
  fixed: { type: Boolean, default: false }});

const videoRef = ref(null);
const reducedMotion = computed(
  () => window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false
);

function syncPlayback() {
  const el = videoRef.value;
  if (!el || reducedMotion.value) return;
  if (document.hidden) {
    el.pause();
  } else {
    el.play().catch(() => {});
  }
}

onMounted(() => {
  if (reducedMotion.value) return;
  document.addEventListener("visibilitychange", syncPlayback);
  syncPlayback();
});

onUnmounted(() => {
  document.removeEventListener("visibilitychange", syncPlayback);
});
</script>

<template>
  <div
    class="page-video-bg"
    :class="{ 'page-video-bg--fixed': fixed, 'page-video-bg--static': reducedMotion }"
    aria-hidden="true"
  >
    <video
      v-if="!reducedMotion"
      ref="videoRef"
      class="page-video-bg__video"
      autoplay
      muted
      loop
      playsinline
      preload="metadata"
      :src="src"
    />
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

.page-video-bg--static .page-video-bg__overlay {
  background:
    linear-gradient(
      180deg,
      rgba(248, 250, 255, 0.72) 0%,
      rgba(236, 242, 255, 0.82) 100%
    ),
    radial-gradient(ellipse 70% 55% at 18% 12%, rgba(91, 156, 245, 0.14) 0%, transparent 58%);
}

.page-video-bg__video {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center;
}

.page-video-bg__overlay {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(
      180deg,
      rgba(248, 250, 255, 0.42) 0%,
      rgba(241, 245, 255, 0.34) 42%,
      rgba(236, 242, 255, 0.48) 100%
    ),
    radial-gradient(ellipse 70% 55% at 18% 12%, rgba(91, 156, 245, 0.12) 0%, transparent 58%),
    radial-gradient(ellipse 60% 50% at 88% 78%, rgba(139, 92, 246, 0.1) 0%, transparent 55%);
}

html[data-theme="dark"] .page-video-bg__overlay {
  background:
    linear-gradient(
      180deg,
      rgba(8, 10, 20, 0.58) 0%,
      rgba(12, 14, 28, 0.48) 45%,
      rgba(10, 12, 24, 0.62) 100%
    ),
    radial-gradient(ellipse 70% 55% at 18% 12%, rgba(59, 130, 246, 0.16) 0%, transparent 58%),
    radial-gradient(ellipse 60% 50% at 88% 78%, rgba(139, 92, 246, 0.14) 0%, transparent 55%);
}
</style>
