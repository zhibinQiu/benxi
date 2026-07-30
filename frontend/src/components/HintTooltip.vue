<script setup>
import { computed } from "vue";
import { NButton, NIcon, NTooltip } from "naive-ui";
import { HelpCircleOutline, InformationCircleOutline } from "@vicons/ionicons5";

const props = defineProps({
  /** 提示文案（主属性） */
  text: { type: String, default: "" },
  /** 兼容 FieldHelp 的 tip 别名 */
  tip: { type: String, default: "" },
  placement: { type: String, default: "bottom" },
  /**
   * default：独立圆形触发区
   * inline：表单项标签旁小图标
   * field：表单标签内极小帮助按钮（原 FieldHelp）
   */
  variant: { type: String, default: "default" },
});

const content = computed(() => props.text || props.tip || "");
const isField = computed(() => props.variant === "field");
const resolvedPlacement = computed(() =>
  isField.value && props.placement === "bottom" ? "top" : props.placement
);
</script>

<template>
  <n-tooltip
    :placement="resolvedPlacement"
    :trigger="isField ? 'hover' : undefined"
    :style="isField ? { maxWidth: '280px' } : undefined"
  >
    <template #trigger>
      <n-button
        v-if="isField"
        quaternary
        circle
        size="tiny"
        class="hint-tooltip hint-tooltip--field"
        tabindex="-1"
        @click.prevent.stop
      >
        <template #icon>
          <n-icon :component="HelpCircleOutline" :size="12" />
        </template>
      </n-button>
      <span
        v-else
        class="hint-tooltip"
        :class="{ 'hint-tooltip--inline': variant === 'inline' }"
        role="img"
        tabindex="0"
        :aria-label="content"
      >
        <n-icon :size="variant === 'inline' ? 14 : 16" :component="InformationCircleOutline" />
      </span>
    </template>
    <span :class="{ 'hint-tooltip__tip': isField }">{{ content }}</span>
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

.hint-tooltip--field {
  width: 16px;
  height: 16px;
  margin-left: 2px;
  vertical-align: -2px;
  color: var(--platform-text-tertiary);
}

.hint-tooltip__tip {
  font-size: 11px;
  line-height: 1.45;
}
</style>
