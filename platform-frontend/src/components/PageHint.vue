<script setup>
import { NAlert } from "naive-ui";

defineProps({
  type: { type: String, default: "default" },
});
</script>

<template>
  <n-alert
    :type="type"
    :bordered="false"
    class="page-hint"
    :show-icon="type !== 'default'"
  >
    <slot />
  </n-alert>
</template>

<style scoped>
.page-hint {
  margin: 0 0 14px;
  border-radius: var(--platform-radius-sm);
  background: var(--platform-toolbar-bg);
  color: var(--platform-text-secondary);
  font-size: 13px;
  line-height: 1.55;
}

.page-hint :deep(.n-alert-body) {
  padding: 10px 12px;
}
</style>
