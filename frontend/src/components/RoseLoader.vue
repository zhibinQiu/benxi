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
  /** 覆盖预设的整体旋转周期（ms），越小越快 */
  rotationDuration: {
    type: Number,
    default: undefined,
  },
  /** 覆盖预设的动画周期（ms），越小越快 */
  durationMs: {
    type: Number,
    default: undefined,
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
    :rotation-duration="rotationDuration"
    :duration-ms="durationMs"
  />
</template>

<style scoped>
.rose-loader {
  flex-shrink: 0;
}
</style>
