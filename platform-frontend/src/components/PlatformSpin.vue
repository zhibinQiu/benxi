<script setup>
import { computed, onBeforeUnmount, ref, useSlots, watch } from "vue";
import RoseLoader from "./RoseLoader.vue";

defineOptions({
  name: "Spin",
  inheritAttrs: false,
});

const props = defineProps({
  show: {
    type: Boolean,
    default: true,
  },
  spinning: {
    type: Boolean,
    default: undefined,
  },
  size: {
    type: [String, Number],
    default: "medium",
  },
  description: {
    type: String,
    default: undefined,
  },
  contentClass: {
    type: String,
    default: undefined,
  },
  contentStyle: {
    type: [Object, String],
    default: undefined,
  },
  delay: {
    type: Number,
    default: undefined,
  },
  rotate: {
    type: Boolean,
    default: true,
  },
  stroke: { type: String, default: undefined },
  strokeWidth: { type: Number, default: undefined },
  radius: { type: Number, default: undefined },
  scale: { type: Number, default: undefined },
});

const slots = useSlots();
const hasDefaultSlot = computed(() => Boolean(slots.default));

const compitableShow = computed(() =>
  props.spinning !== undefined ? props.spinning : props.show
);

const active = ref(false);
let delayTimer = null;

function syncActive(show) {
  if (delayTimer) {
    clearTimeout(delayTimer);
    delayTimer = null;
  }
  if (!show) {
    active.value = false;
    return;
  }
  if (props.delay) {
    delayTimer = window.setTimeout(() => {
      active.value = true;
    }, props.delay);
    return;
  }
  active.value = true;
}

watch(compitableShow, (show) => syncActive(show), { immediate: true });

onBeforeUnmount(() => {
  if (delayTimer) clearTimeout(delayTimer);
});

const roseSize = computed(() => {
  if (typeof props.size === "number") return props.size;
  const map = {
    tiny: 20,
    small: 28,
    medium: 40,
    large: 56,
    huge: 72,
  };
  return map[props.size] ?? 40;
});

const loaderLabel = computed(() => props.description || "加载中");
</script>

<template>
  <div v-if="hasDefaultSlot" class="n-spin-container">
    <div
      class="n-spin-content"
      :class="[contentClass, { 'n-spin-content--spinning': active }]"
      :style="contentStyle"
    >
      <slot />
    </div>
    <Transition name="fade-in-transition">
      <div v-if="active" class="n-spin-body">
        <div v-if="slots.icon" class="platform-spin__icon">
          <slot name="icon" />
        </div>
        <RoseLoader
          v-else
          class="platform-spin__rose"
          :size="roseSize"
          :rotate="rotate"
          :label="loaderLabel"
        />
        <div v-if="description || slots.description" class="n-spin-description">
          <slot name="description">{{ description }}</slot>
        </div>
      </div>
    </Transition>
  </div>

  <div v-else-if="active" class="n-spin-body n-spin-body--inline">
    <div v-if="slots.icon" class="platform-spin__icon">
      <slot name="icon" />
    </div>
    <RoseLoader
      v-else
      class="platform-spin__rose"
      :size="roseSize"
      :rotate="rotate"
      :label="loaderLabel"
    />
    <div v-if="description || slots.description" class="n-spin-description">
      <slot name="description">{{ description }}</slot>
    </div>
  </div>
</template>

<style scoped>
.n-spin-body--inline {
  position: relative;
  top: auto;
  left: auto;
  transform: none;
  display: inline-flex;
}

.platform-spin__rose,
.platform-spin__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  line-height: 0;
}

.platform-spin__rose :deep(.rose-loader) {
  display: block;
}
</style>
