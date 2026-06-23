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
  /** 表格内嵌操作：仅悬浮时显示选中衬底，与文档列表操作列一致 */
  variant: { type: String, default: "toolbar" },
});

const tooltipText = computed(() => props.tooltip || props.label);

defineEmits(["click"]);

const isTableVariant = computed(() => props.variant === "table");

const iconSize = computed(() => (isTableVariant.value ? 16 : 18));

const actionClass = computed(() => {
  if (isTableVariant.value) {
    if (props.type === "primary") return "table-icon-action table-icon-action--accent";
    if (props.type === "error") return "table-icon-action table-icon-action--danger";
    if (props.type === "warning") return "table-icon-action table-icon-action--caution";
    return "table-icon-action";
  }
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
        :class="isTableVariant ? actionClass : ['icon-action', actionClass]"
        :aria-label="label"
        @click="$emit('click', $event)"
      >
        <n-icon :size="iconSize" :component="icon" />
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
}

.icon-action.icon-action--active {
  color: var(--platform-accent);
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
  background: color-mix(in srgb, var(--platform-danger) 14%, var(--platform-danger-soft));
}
</style>
