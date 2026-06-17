<script setup>
import { computed } from "vue";
import CurveAnimation from "./CurveAnimation.vue";

const props = defineProps({
  size: {
    type: [Number, String],
    default: "md",
  },
  rotate: {
    type: Boolean,
    default: true,
  },
  label: {
    type: String,
    default: "加载中",
  },
});

const SIZE_MAP = {
  xs: 22,
  sm: 36,
  md: 56,
  lg: 88,
};

const pixelSize = computed(() => {
  if (typeof props.size === "number") return props.size;
  return SIZE_MAP[props.size] ?? SIZE_MAP.md;
});
</script>

<template>
  <CurveAnimation
    class="rose-loader"
    preset="rose-three"
    :size="pixelSize"
    :rotate="rotate"
    :label="label"
  />
</template>

<style scoped>
.rose-loader {
  flex-shrink: 0;
}
</style>
