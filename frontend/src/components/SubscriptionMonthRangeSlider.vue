<script setup>
import { computed, ref, watch } from "vue";
import { NButton, NSlider } from "naive-ui";
import {
  buildSubscriptionMonthSpan,
  formatMonthLabel,
  monthIndexFromTs,
  tsRangeFromMonthIndices,
} from "../utils/monthRange.js";

const props = defineProps({
  modelValue: { type: Array, default: null },
  locale: { type: String, default: "zh-CN" },
  label: { type: String, default: "" },
  clearLabel: { type: String, default: "" },
});

const emit = defineEmits(["update:modelValue"]);

const span = buildSubscriptionMonthSpan();

const sliderValue = ref([0, span.maxIndex]);

const isFullRange = computed(
  () => sliderValue.value[0] === 0 && sliderValue.value[1] === span.maxIndex
);

const rangeLabel = computed(() => {
  const [fromIdx, toIdx] = sliderValue.value;
  const [fromTs, toTs] = tsRangeFromMonthIndices(span.baseYear, span.baseMonth, fromIdx, toIdx);
  return `${formatMonthLabel(fromTs, props.locale)} — ${formatMonthLabel(toTs, props.locale)}`;
});

function syncSliderFromModel(value) {
  if (!value || !Array.isArray(value) || value.length !== 2) {
    sliderValue.value = [0, span.maxIndex];
    return;
  }
  const fromIdx = Math.max(0, Math.min(span.maxIndex, monthIndexFromTs(span.baseYear, span.baseMonth, value[0])));
  const toIdx = Math.max(fromIdx, Math.min(span.maxIndex, monthIndexFromTs(span.baseYear, span.baseMonth, value[1])));
  sliderValue.value = [fromIdx, toIdx];
}

function emitFromSlider([fromIdx, toIdx]) {
  if (fromIdx === 0 && toIdx === span.maxIndex) {
    emit("update:modelValue", null);
    return;
  }
  emit("update:modelValue", tsRangeFromMonthIndices(span.baseYear, span.baseMonth, fromIdx, toIdx));
}

watch(
  () => props.modelValue,
  (value) => syncSliderFromModel(value),
  { immediate: true, deep: true }
);

function onSliderUpdate(next) {
  const fromIdx = Math.min(next[0], next[1]);
  const toIdx = Math.max(next[0], next[1]);
  sliderValue.value = [fromIdx, toIdx];
  emitFromSlider(sliderValue.value);
}

function clearRange() {
  sliderValue.value = [0, span.maxIndex];
  emit("update:modelValue", null);
}
</script>

<template>
  <div
    class="subscription-month-range"
    :class="{ 'subscription-month-range--filtered': !isFullRange }"
  >
    <span v-if="label" class="subscription-month-range__label">{{ label }}</span>
    <NSlider
      :value="sliderValue"
      range
      :min="0"
      :max="span.maxIndex"
      :step="1"
      :tooltip="false"
      class="subscription-month-range__slider"
      @update:value="onSliderUpdate"
    />
    <span class="subscription-month-range__value">{{ rangeLabel }}</span>
    <NButton
      v-if="!isFullRange"
      size="tiny"
      quaternary
      class="subscription-month-range__clear"
      @click="clearRange"
    >
      {{ clearLabel }}
    </NButton>
  </div>
</template>

<style scoped>
.subscription-month-range {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 5px;
  opacity: 0.5;
  transition: opacity 0.22s ease;
  min-width: 0;
}

.subscription-month-range--filtered {
  opacity: 0.65;
}

.subscription-month-range:hover,
.subscription-month-range:focus-within {
  opacity: 1;
}

.subscription-month-range__label {
  font-size: 14px;
  color: var(--platform-text-secondary);
  flex-shrink: 0;
  white-space: nowrap;
}

.subscription-month-range__slider {
  flex: 1;
  min-width: 80px;
  max-width: 240px;
  padding: 0;
}

.subscription-month-range__slider :deep(.n-slider-rail) {
  height: 5px;
  border-radius: 1199px;
}

.subscription-month-range__slider :deep(.n-slider-rail__fill) {
  border-radius: 1199px;
}

.subscription-month-range__slider :deep(.n-slider-handle) {
  width: 15px;
  height: 15px;
}

.subscription-month-range__value {
  font-size: 13px;
  color: var(--platform-text);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  flex-shrink: 0;
}

.subscription-month-range__clear {
  flex-shrink: 0;
}
</style>
