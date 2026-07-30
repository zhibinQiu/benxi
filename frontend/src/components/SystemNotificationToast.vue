<script setup>
import { useRouter } from "vue-router";
import { NotificationsOutline } from "@vicons/ionicons5";
import { NIcon } from "naive-ui";
import { useI18n } from "../composables/useI18n";
import { acknowledgeToast, useNotificationAlerts } from "../composables/useNotificationAlerts";
import { PLATFORM_Z } from "../constants/zIndex.js";
import { renderMarkdown } from "../utils/markdown.js";

const router = useRouter();
const { t } = useI18n();
const { activeToasts } = useNotificationAlerts();

function onOpen(toast) {
  acknowledgeToast(toast, {
    navigate: (link) => router.push(link),
  });
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="activeToasts.length"
      class="system-notif-stack"
      :style="{ zIndex: PLATFORM_Z.notificationAlert }"
      aria-live="assertive"
      aria-relevant="additions"
    >
      <article
        v-for="toast in activeToasts"
        :key="toast.key"
        class="system-notif-card system-notif-card--shake"
        role="alert"
      >
        <button
          type="button"
          class="system-notif-card__body"
          @click="onOpen(toast)"
        >
          <span class="system-notif-card__icon" aria-hidden="true">
            <n-icon :size="16" :component="NotificationsOutline" />
          </span>
          <span class="system-notif-card__text">
            <div
              v-if="toast.notification.body"
              class="system-notif-card__desc"
              v-html="renderMarkdown(toast.notification.body)"
            />
            <span class="system-notif-card__hint">{{ t("notifications.alertHint") }}</span>
          </span>
        </button>
      </article>
    </div>
  </Teleport>
</template>

<style scoped>
.system-notif-stack {
  position: fixed;
  /* 避开顶栏/标签栏，整体下移，避免贴顶遮挡 */
  top: 72px;
  right: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: min(280px, calc(100vw - 32px));
  pointer-events: none;
}

.system-notif-card {
  position: relative;
  pointer-events: auto;
  border-radius: var(--platform-radius-md, 10px);
  border: 1px solid color-mix(in srgb, var(--platform-accent) 28%, var(--platform-border));
  background: var(--platform-card-bg);
  box-shadow:
    0 8px 22px color-mix(in srgb, var(--platform-accent) 12%, transparent),
    0 1px 6px rgba(15, 23, 42, 0.06);
  overflow: hidden;
}

.system-notif-card--shake {
  animation: system-notif-shake 0.62s cubic-bezier(0.36, 0.07, 0.19, 0.97);
}

.system-notif-card__body {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  width: 100%;
  padding: 10px 12px;
  border: none;
  background: transparent;
  text-align: left;
  cursor: pointer;
  font: inherit;
  color: inherit;
}

.system-notif-card__body:hover {
  background: var(--platform-accent-soft);
}

.system-notif-card__icon {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 8px;
  background: var(--platform-accent-gradient-soft, rgba(24, 160, 88, 0.12));
  color: var(--platform-accent);
}

.system-notif-card__text {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.system-notif-card__desc {
  font-size: 13px;
  line-height: 1.4;
  color: var(--platform-text-secondary);
  word-break: break-word;
}

.system-notif-card__desc :deep(p) {
  margin: 0 0 0.25em;
}

.system-notif-card__desc :deep(p:last-child) {
  margin-bottom: 0;
}

.system-notif-card__desc :deep(ul),
.system-notif-card__desc :deep(ol) {
  margin: 0.15em 0;
  padding-left: 1.2em;
}

.system-notif-card__desc :deep(a) {
  color: var(--platform-accent);
}

.system-notif-card__hint {
  font-size: 11px;
  color: var(--platform-text-tertiary);
}

@keyframes system-notif-shake {
  0%,
  100% {
    transform: translateX(0);
  }
  12%,
  36%,
  60%,
  84% {
    transform: translateX(-6px);
  }
  24%,
  48%,
  72% {
    transform: translateX(6px);
  }
}
</style>
