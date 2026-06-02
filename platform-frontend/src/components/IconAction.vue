<script setup>
import { computed } from "vue";
import { NButton, NIcon, NTooltip } from "naive-ui";

const props = defineProps({
  label: { type: String, required: true },
  /** 悬浮提示；未设置时使用 label */
  tooltip: { type: String, default: "" },
  icon: { type: [Object, Function], required: true },
  active: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  type: { type: String, default: "default" },
  size: { type: String, default: "small" },
});

const tooltipText = computed(() => props.tooltip || props.label);

defineEmits(["click"]);

const actionClass = computed(() => {
  if (props.active || props.type === "primary") return "icon-action--active";
  if (props.type === "warning") return "icon-action--caution";
  if (props.type === "error") return "icon-action--danger";
  return "";
});
</script>

<template>
  <n-tooltip placement="bottom">
    <template #trigger>
      <n-button
        quaternary
        circle
        :size="size"
        type="default"
        :disabled="disabled"
        class="icon-action"
        :class="actionClass"
        :aria-label="label"
        @click="$emit('click', $event)"
      >
        <n-icon :size="18" :component="icon" />
      </n-button>
    </template>
    {{ tooltipText }}
  </n-tooltip>
</template>

<style scoped>
.icon-action {
  width: 32px;
  height: 32px;
  color: var(--platform-text-secondary);
  transition:
    color 0.15s ease,
    background 0.15s ease;
}

.icon-action:not(:disabled):hover {
  color: var(--platform-text);
  background: var(--platform-toolbar-bg);
}

.icon-action.icon-action--active {
  color: var(--platform-accent);
  background: var(--platform-accent-soft);
}

.icon-action.icon-action--caution:not(:disabled) {
  color: var(--platform-caution);
}

.icon-action.icon-action--caution:not(:disabled):hover {
  color: var(--platform-caution);
  background: var(--platform-caution-soft);
}

.icon-action.icon-action--danger:not(:disabled) {
  color: var(--platform-danger);
}

.icon-action.icon-action--danger:not(:disabled):hover {
  color: var(--platform-danger);
  background: var(--platform-danger-soft);
}
</style>
