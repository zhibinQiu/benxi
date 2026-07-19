<script setup>
import { onBeforeUnmount, ref, watch } from "vue";
import { NText } from "naive-ui";

const props = defineProps({
  stream: { type: Object, default: null },
  active: { type: Boolean, default: false },
  height: { type: Number, default: 72 },
  placeholder: { type: String, default: "" },
});

const emit = defineEmits(["level"]);

const canvasRef = ref(null);
const wrapRef = ref(null);
let audioContext = null;
let analyser = null;
let sourceNode = null;
let rafId = null;

function readAccentColors() {
  const el = wrapRef.value || document.documentElement;
  const styles = getComputedStyle(el);
  return {
    accent: styles.getPropertyValue("--platform-accent").trim() || "#0a6bff",
    accentSecondary:
      styles.getPropertyValue("--platform-accent-secondary").trim() || "#3b82ff",
    accentPressed:
      styles.getPropertyValue("--platform-accent-pressed").trim() || "#004ac2",
    idle: styles.getPropertyValue("--platform-border-strong").trim() || "rgba(0,0,0,0.09)",
    midLine: styles.getPropertyValue("--platform-accent-border-soft").trim() || "rgba(10,107,255,0.15)",
  };
}

function teardown() {
  if (rafId) {
    cancelAnimationFrame(rafId);
    rafId = null;
  }
  if (sourceNode) {
    try {
      sourceNode.disconnect();
    } catch {
      /* ignore */
    }
    sourceNode = null;
  }
  if (audioContext) {
    audioContext.close().catch(() => {});
    audioContext = null;
  }
  analyser = null;
}

function computeRms(data) {
  let sum = 0;
  for (let i = 0; i < data.length; i++) {
    const v = (data[i] - 128) / 128;
    sum += v * v;
  }
  return Math.sqrt(sum / data.length);
}

function drawFrame() {
  const canvas = canvasRef.value;
  if (!canvas || !analyser) return;
  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth;
  const h = canvas.clientHeight;
  if (w <= 0 || h <= 0) {
    rafId = requestAnimationFrame(drawFrame);
    return;
  }
  if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  const buf = new Uint8Array(analyser.fftSize);
  analyser.getByteTimeDomainData(buf);
  const rms = computeRms(buf);
  emit("level", rms);

  const colors = readAccentColors();
  ctx.clearRect(0, 0, w, h);
  const mid = h / 2;
  const barCount = Math.floor(w / 3);
  const step = Math.floor(buf.length / barCount);

  for (let i = 0; i < barCount; i++) {
    let peak = 0;
    const start = i * step;
    for (let j = 0; j < step; j++) {
      const v = Math.abs((buf[start + j] - 128) / 128);
      if (v > peak) peak = v;
    }
    const barH = Math.max(2, peak * h * 0.9);
    const x = i * 3;
    if (props.active) {
      const grad = ctx.createLinearGradient(0, mid - barH, 0, mid + barH);
      grad.addColorStop(0, colors.accentSecondary);
      grad.addColorStop(0.5, colors.accent);
      grad.addColorStop(1, colors.accentPressed);
      ctx.fillStyle = grad;
    } else {
      ctx.fillStyle = colors.idle;
    }
    ctx.fillRect(x, mid - barH / 2, 2, barH);
  }

  ctx.strokeStyle = props.active ? colors.midLine : colors.idle;
  ctx.beginPath();
  ctx.moveTo(0, mid);
  ctx.lineTo(w, mid);
  ctx.stroke();

  rafId = requestAnimationFrame(drawFrame);
}

function setup(stream) {
  teardown();
  if (!stream) return;
  audioContext = new AudioContext();
  if (audioContext.state === "suspended") {
    void audioContext.resume();
  }
  analyser = audioContext.createAnalyser();
  analyser.fftSize = 2048;
  analyser.smoothingTimeConstant = 0.82;
  sourceNode = audioContext.createMediaStreamSource(stream);
  sourceNode.connect(analyser);
  drawFrame();
}

watch(
  () => props.stream,
  (s) => {
    if (s && props.active) setup(s);
    else teardown();
  },
  { immediate: true }
);

watch(
  () => props.active,
  (on) => {
    if (on && props.stream) setup(props.stream);
    else if (!on) teardown();
  }
);

onBeforeUnmount(teardown);
</script>

<template>
  <div ref="wrapRef" class="wave-wrap" :class="{ active }">
    <canvas ref="canvasRef" class="wave-canvas" :style="{ height: `${height}px` }" />
    <n-text v-if="!active && placeholder" depth="3" class="wave-placeholder">{{ placeholder }}</n-text>
  </div>
</template>

<style scoped>
.wave-wrap {
  position: relative;
  width: 100%;
  border-radius: var(--platform-radius-sm, 9px);
  background:
    linear-gradient(
      180deg,
      color-mix(in srgb, var(--platform-accent) 4%, transparent) 0%,
      color-mix(in srgb, var(--platform-accent) 8%, transparent) 100%
    );
  border: 1px solid var(--platform-accent-border-soft);
  overflow: hidden;
}
.wave-wrap.active {
  border-color: var(--platform-accent-border);
  box-shadow: inset 0 0 24px color-mix(in srgb, var(--platform-accent) 8%, transparent);
}
.wave-canvas {
  display: block;
  width: 100%;
}
.wave-placeholder {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--platform-font-size-sm, 12px);
  pointer-events: none;
}
.wave-wrap.active .wave-placeholder {
  display: none;
}
</style>
