<script setup>
import { NIcon } from "naive-ui";
import {
  CopyOutline,
  RefreshOutline,
  ShareSocialOutline,
  ThumbsDown,
  ThumbsDownOutline,
  ThumbsUp,
  ThumbsUpOutline,
} from "@vicons/ionicons5";
import { useI18n } from "../composables/useI18n.js";

defineProps({
  align: {
    type: String,
    default: "start",
    validator: (v) => v === "start" || v === "end",
  },
  disabled: { type: Boolean, default: false },
  showRetry: { type: Boolean, default: false },
  retryDisabled: { type: Boolean, default: false },
  feedback: {
    type: String,
    default: null,
    validator: (v) => v == null || v === "up" || v === "down",
  },
});

const emit = defineEmits(["copy", "share", "retry", "feedback"]);

const { t } = useI18n();
</script>

<template>
  <div
    class="chat-bubble-actions"
    :class="`chat-bubble-actions--${align}`"
    role="toolbar"
    :aria-label="t('chat.messageActions')"
  >
    <button
      type="button"
      class="chat-bubble-actions__btn"
      :disabled="disabled"
      :aria-label="t('chat.copy')"
      :title="t('chat.copy')"
      @click="emit('copy')"
    >
      <n-icon :size="13" :component="CopyOutline" />
    </button>
    <button
      type="button"
      class="chat-bubble-actions__btn"
      :disabled="disabled"
      :aria-label="t('chat.share')"
      :title="t('chat.share')"
      @click="emit('share')"
    >
      <n-icon :size="13" :component="ShareSocialOutline" />
    </button>
    <button
      v-if="showRetry"
      type="button"
      class="chat-bubble-actions__btn"
      :disabled="disabled || retryDisabled"
      :aria-label="t('chat.retry')"
      :title="t('chat.retry')"
      @click="emit('retry')"
    >
      <n-icon :size="13" :component="RefreshOutline" />
    </button>
    <button
      type="button"
      class="chat-bubble-actions__btn"
      :class="{ 'chat-bubble-actions__btn--active': feedback === 'up' }"
      :disabled="disabled"
      :aria-label="t('chat.like')"
      :title="t('chat.like')"
      :aria-pressed="feedback === 'up'"
      @click="emit('feedback', feedback === 'up' ? null : 'up')"
    >
      <n-icon :size="13" :component="feedback === 'up' ? ThumbsUp : ThumbsUpOutline" />
    </button>
    <button
      type="button"
      class="chat-bubble-actions__btn"
      :class="{ 'chat-bubble-actions__btn--active': feedback === 'down' }"
      :disabled="disabled"
      :aria-label="t('chat.dislike')"
      :title="t('chat.dislike')"
      :aria-pressed="feedback === 'down'"
      @click="emit('feedback', feedback === 'down' ? null : 'down')"
    >
      <n-icon :size="13" :component="feedback === 'down' ? ThumbsDown : ThumbsDownOutline" />
    </button>
  </div>
</template>

<style scoped>
.chat-bubble-actions {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  margin-top: 4px;
  opacity: 0.42;
  transition: opacity 0.15s ease;
}

.chat-bubble-actions--start {
  align-self: flex-start;
}

.chat-bubble-actions--end {
  align-self: flex-end;
}

.chat-bubble-actions:hover,
.ai-home-msg-stack:hover .chat-bubble-actions,
.assistant-msg-stack:hover .chat-bubble-actions,
.chat-item-stack:hover .chat-bubble-actions,
.knowledge-search-panel__answer:hover .chat-bubble-actions {
  opacity: 0.88;
}

.chat-bubble-actions__btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--platform-text-secondary);
  cursor: pointer;
  transition:
    color 0.15s ease,
    background 0.15s ease,
    opacity 0.15s ease;
}

.chat-bubble-actions__btn:hover:not(:disabled) {
  color: var(--platform-accent-pressed);
  background: color-mix(in srgb, var(--platform-accent-muted) 55%, transparent);
}

.chat-bubble-actions__btn--active {
  color: var(--platform-accent);
  opacity: 1;
}

.chat-bubble-actions__btn--active:hover:not(:disabled) {
  color: var(--platform-accent-hover);
}

.chat-bubble-actions__btn:disabled {
  opacity: 0.28;
  cursor: not-allowed;
}

.chat-bubble-actions__btn:focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px var(--platform-bg-elevated), 0 0 0 4px var(--platform-accent);
}
</style>
