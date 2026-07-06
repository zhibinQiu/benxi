<script setup>
import { computed } from "vue";
import { NButton, NIcon, NTooltip } from "naive-ui";
import RoseLoader from "./RoseLoader.vue";

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
  /** 进行中：图标旋转，用于刷新等异步操作 */
  loading: { type: Boolean, default: false },
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
  const classes = ["icon-action--theme"];
  if (props.active) classes.push("icon-action--active");
  return classes.join(" ");
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
        :class="[
          isTableVariant ? actionClass : ['icon-action', actionClass],
          { 'icon-action--loading': loading },
        ]"
        :aria-label="label"
        :aria-busy="loading || undefined"
        @click="$emit('click', $event)"
      >
        <RoseLoader v-if="loading" :size="iconSize" class="icon-action__rose" />
        <n-icon v-else :size="iconSize" :component="icon" />
      </n-button>
    </template>
    {{ tooltipText }}
  </n-tooltip>
</template>

<style scoped>
.icon-action {
  width: 38px;
  height: 38px;
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  backdrop-filter: none !important;
  -webkit-backdrop-filter: none !important;
  transition:
    color 0.15s ease,
    background 0.15s ease,
    box-shadow 0.15s ease;
}

.icon-action.icon-action--theme {
  color: var(--platform-accent);
}

.icon-action.icon-action--theme:not(:disabled):hover {
  color: var(--platform-accent-hover, var(--platform-accent));
  background: color-mix(in srgb, var(--platform-accent-soft) 72%, var(--platform-accent) 28%) !important;
  box-shadow: 0 2px 10px color-mix(in srgb, var(--platform-accent) 18%, transparent);
}

.icon-action.icon-action--theme.icon-action--active {
  background: var(--platform-accent-soft);
}

.icon-action.icon-action--caution:not(:disabled) {
  color: var(--platform-caution);
  background: var(--platform-caution-soft);
  border: 1px solid color-mix(in srgb, var(--platform-caution) 24%, transparent);
  box-shadow: inset 0 1px 0 color-mix(in srgb, #fff 8%, transparent);
}

.icon-action.icon-action--caution:not(:disabled):hover {
  color: var(--platform-caution);
  background: color-mix(in srgb, var(--platform-caution) 16%, var(--platform-caution-soft));
  border-color: color-mix(in srgb, var(--platform-caution) 40%, transparent);
}

.icon-action.icon-action--danger:not(:disabled) {
  color: var(--platform-danger);
  background: var(--platform-danger-soft);
  border: 1px solid color-mix(in srgb, var(--platform-danger) 24%, transparent);
  box-shadow: inset 0 1px 0 color-mix(in srgb, #fff 8%, transparent);
}

.icon-action.icon-action--danger:not(:disabled):hover {
  color: var(--platform-danger);
  background: color-mix(in srgb, var(--platform-danger) 16%, var(--platform-danger-soft));
  border-color: color-mix(in srgb, var(--platform-danger) 40%, transparent);
}

.icon-action.icon-action--danger:disabled,
.icon-action.icon-action--caution:disabled {
  opacity: 0.42;
  background: var(--platform-bg-glass-subtle);
  border-color: var(--platform-border);
  box-shadow: none;
}

.icon-action--loading {
  pointer-events: none;
}

.icon-action__rose {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  line-height: 0;
}

@media (prefers-reduced-motion: reduce) {
  .icon-action__rose :deep(.curve-animation) {
    animation: none;
  }
}
</style>
