<script setup>
import CurveAnimation from "./CurveAnimation.vue";

defineProps({
  clsPrefix: {
    type: String,
    required: true,
  },
  show: {
    type: Boolean,
    default: true,
  },
  strokeWidth: { type: Number, default: 28 },
  stroke: { type: String, default: undefined },
  scale: { type: Number, default: 1 },
  radius: { type: Number, default: 100 },
});
</script>

<template>
  <div
    v-if="show"
    :class="`${clsPrefix}-base-loading platform-base-loading`"
    role="img"
    aria-label="loading"
  >
    <div class="platform-base-loading__inner">
      <CurveAnimation
        preset="rose-three"
        fill
        inline
        :path-steps="160"
        :path-opacity="0.16"
      />
    </div>
  </div>
  <div v-else :class="`${clsPrefix}-base-loading__placeholder`" aria-hidden="true" />
</template>

<style scoped>
.platform-base-loading {
  position: relative;
  line-height: 0;
  width: 1em;
  height: 1em;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  vertical-align: -0.12em;
  color: currentColor;
  flex-shrink: 0;
}

.platform-base-loading__inner {
  width: 1em;
  height: 1em;
}
</style>
