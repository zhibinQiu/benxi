<script setup>
import { NIcon } from "naive-ui";
import { RefreshOutline } from "@vicons/ionicons5";
import { useI18n } from "../composables/useI18n.js";

defineProps({
  align: {
    type: String,
    default: "start",
    validator: (v) => v === "start" || v === "end",
  },
  disabled: { type: Boolean, default: false },
});

const emit = defineEmits(["retry"]);

const { t } = useI18n();
</script>

<template>
  <button
    type="button"
    class="chat-bubble-retry"
    :class="`chat-bubble-retry--${align}`"
    :disabled="disabled"
    :aria-label="t('chat.retry')"
    :title="t('chat.retry')"
    @click="emit('retry')"
  >
    <n-icon :size="13" :component="RefreshOutline" />
  </button>
</template>

<style scoped>
.chat-bubble-retry {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-top: 4px;
  padding: 2px 4px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--platform-text-secondary);
  opacity: 0.38;
  cursor: pointer;
  transition:
    opacity 0.15s ease,
    color 0.15s ease,
    background 0.15s ease;
}

.chat-bubble-retry--start {
  align-self: flex-start;
}

.chat-bubble-retry--end {
  align-self: flex-end;
}

.chat-bubble-retry:hover:not(:disabled) {
  opacity: 0.78;
  color: var(--platform-accent-pressed);
  background: color-mix(in srgb, var(--platform-accent-muted) 55%, transparent);
}

.chat-bubble-retry:disabled {
  opacity: 0.22;
  cursor: not-allowed;
}
</style>
