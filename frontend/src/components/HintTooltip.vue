<script setup>
import { NIcon, NTooltip } from "naive-ui";
import { InformationCircleOutline } from "@vicons/ionicons5";

defineProps({
  text: { type: String, required: true },
  placement: { type: String, default: "bottom" },
  /** inline：表单项标签旁的小图标；default：独立圆形触发区 */
  variant: { type: String, default: "default" },
});
</script>

<template>
  <n-tooltip :placement="placement">
    <template #trigger>
      <span
        class="hint-tooltip"
        :class="{ 'hint-tooltip--inline': variant === 'inline' }"
        role="img"
        tabindex="0"
        :aria-label="text"
      >
        <n-icon :size="variant === 'inline' ? 14 : 16" :component="InformationCircleOutline" />
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
  width: 34px;
  height: 34px;
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

.hint-tooltip--inline {
  width: 26px;
  height: 26px;
  vertical-align: middle;
}

.hint-tooltip--inline:hover,
.hint-tooltip--inline:focus-visible {
  background: var(--platform-accent-muted);
  color: var(--platform-accent);
}
</style>
