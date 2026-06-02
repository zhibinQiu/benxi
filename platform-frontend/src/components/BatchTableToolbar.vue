<script setup>
import { NButton, NSpace } from "naive-ui";

defineProps({
  count: { type: Number, default: 0 },
  disabled: { type: Boolean, default: true },
  label: { type: String, default: "删除" },
});

defineEmits(["action"]);
</script>

<template>
  <div class="batch-table-toolbar">
    <n-space align="center" :size="8">
      <n-button type="error" secondary :disabled="disabled" @click="$emit('action')">
        {{ label }}
      </n-button>
      <span v-if="count > 0" class="batch-table-toolbar__hint">已选 {{ count }} 项</span>
    </n-space>
  </div>
</template>
