<script setup>
import { computed, toRef } from "vue";
import { useTypewriter } from "../composables/useTypewriter";

const props = defineProps({
  lines: { type: Array, default: () => [] },
  tag: { type: String, default: "p" },
  options: { type: Object, default: () => ({}) }});

const linesRef = toRef(props, "lines");
const { displayedText, showCursor } = useTypewriter(linesRef, props.options);

const longestLine = computed(() => {
  const lines = Array.isArray(props.lines) ? props.lines : [];
  return lines.reduce((longest, line) => {
    const text = String(line ?? "");
    return text.length > longest.length ? text : longest;
  }, "");
});
</script>

<template>
  <component :is="tag" class="typewriter-text">
    <span class="typewriter-text__sizer" aria-hidden="true">{{ longestLine }}</span>
    <span class="typewriter-text__content">
      {{ displayedText
      }}<span v-if="showCursor" class="typewriter-text__cursor" aria-hidden="true">▍</span>
    </span>
  </component>
</template>

<style scoped>
.typewriter-text {
  position: relative;
  margin: 0;
}

.typewriter-text__sizer {
  display: block;
  visibility: hidden;
  user-select: none;
  pointer-events: none;
}

.typewriter-text__content {
  position: absolute;
  inset: 0;
}

.typewriter-text__cursor {
  display: inline-block;
  color: var(--platform-accent);
  animation: typewriter-cursor-blink 1s step-end infinite;
  margin-left: 1px;
}

@keyframes typewriter-cursor-blink {
  50% {
    opacity: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .typewriter-text__cursor {
    animation: none;
  }
}
</style>
