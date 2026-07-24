<script setup>
import { computed } from "vue";
import { documentFileIconMeta } from "../utils/documentFileIcon.js";

const props = defineProps({
  /** 与后端 file_format 对齐的格式码，如 pdf / word */
  format: { type: String, default: "" },
  size: { type: Number, default: 72 },
});

const meta = computed(() => documentFileIconMeta(props.format));
const uid = `dfi-${Math.random().toString(36).slice(2, 10)}`;
</script>

<template>
  <svg
    class="document-file-icon"
    :width="size"
    :height="Math.round(size * 1.22)"
    viewBox="0 0 72 88"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    :aria-label="meta.badge"
    role="img"
  >
    <defs>
      <linearGradient
        :id="`${uid}-paper`"
        x1="12"
        y1="8"
        x2="60"
        y2="80"
        gradientUnits="userSpaceOnUse"
      >
        <stop offset="0%" stop-color="#ffffff" />
        <stop offset="100%" stop-color="#f1f5f9" />
      </linearGradient>
      <linearGradient
        :id="`${uid}-fold`"
        x1="44"
        y1="8"
        x2="64"
        y2="28"
        gradientUnits="userSpaceOnUse"
      >
        <stop offset="0%" stop-color="#e2e8f0" />
        <stop offset="100%" stop-color="#cbd5e1" />
      </linearGradient>
    </defs>
    <!-- 纸张主体 -->
    <path
      d="M14 6h32l18 18v52c0 3.3-2.7 6-6 6H14c-3.3 0-6-2.7-6-6V12c0-3.3 2.7-6 6-6z"
      :fill="`url(#${uid}-paper)`"
      stroke="#cbd5e1"
      stroke-width="1.25"
    />
    <!-- 折角 -->
    <path
      d="M46 6v12c0 3.3 2.7 6 6 6h12L46 6z"
      :fill="`url(#${uid}-fold)`"
      stroke="#cbd5e1"
      stroke-width="1.25"
      stroke-linejoin="round"
    />
    <!-- 格式色带 -->
    <rect
      x="12"
      y="40"
      width="48"
      height="22"
      rx="4"
      :fill="meta.color"
    />
    <text
      x="36"
      y="55.5"
      text-anchor="middle"
      fill="#fff"
      font-size="11"
      font-weight="700"
      font-family="ui-sans-serif, system-ui, -apple-system, sans-serif"
      letter-spacing="0.04em"
    >
      {{ meta.badge }}
    </text>
    <!-- 顶部装饰线 -->
    <rect x="16" y="24" width="22" height="2.5" rx="1.25" :fill="meta.soft" />
    <rect x="16" y="30" width="16" height="2.5" rx="1.25" :fill="meta.soft" />
  </svg>
</template>

<style scoped>
.document-file-icon {
  display: block;
  flex-shrink: 0;
  filter: drop-shadow(0 4px 10px rgba(15, 23, 42, 0.08));
}
</style>
