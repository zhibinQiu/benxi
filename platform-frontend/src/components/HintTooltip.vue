<script setup>
import { NIcon, NTooltip } from "naive-ui";
import { InformationCircleOutline } from "@vicons/ionicons5";

defineProps({
  text: { type: String, required: true },
  placement: { type: String, default: "bottom" },
});
</script>

<template>
  <n-tooltip :placement="placement">
    <template #trigger>
      <span class="hint-tooltip" role="img" tabindex="0" :aria-label="text">
        <n-icon :size="16" :component="InformationCircleOutline" />
      </span>
    </template>
    {{ text }}
  </n-tooltip>
</template>

<style scoped>
.hint-tooltip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  color: var(--platform-text-tertiary);
  cursor: help;
  transition: color 0.15s ease, background 0.15s ease;
}

.hint-tooltip:hover,
.hint-tooltip:focus-visible {
  color: var(--platform-text-secondary);
  background: var(--platform-toolbar-bg);
  outline: none;
}
</style>
