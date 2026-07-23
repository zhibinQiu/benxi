<script setup>
import { HelpCircleOutline } from "@vicons/ionicons5";

defineProps({
  tip: { type: String, required: true },
});
</script>

<template>
  <n-tooltip trigger="hover" placement="top" :style="{ maxWidth: '280px' }">
    <template #trigger>
      <n-button
        quaternary
        circle
        size="tiny"
        class="field-help-btn"
        tabindex="-1"
        @click.prevent.stop
      >
        <template #icon>
          <n-icon :component="HelpCircleOutline" :size="12" />
        </template>
      </n-button>
    </template>
    <span class="field-help-tip">{{ tip }}</span>
  </n-tooltip>
</template>

<style scoped>
.field-help-btn {
  width: 16px;
  height: 16px;
  margin-left: 2px;
  vertical-align: -2px;
  color: var(--platform-text-tertiary);
}
.field-help-tip {
  font-size: 11px;
  line-height: 1.45;
}
</style>
