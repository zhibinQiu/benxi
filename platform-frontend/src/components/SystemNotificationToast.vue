<script setup>
import { useRouter } from "vue-router";
import { NotificationsOutline, CloseOutline } from "@vicons/ionicons5";
import { NIcon } from "naive-ui";
import { useI18n } from "../composables/useI18n";
import { acknowledgeToast, dismissToast, useNotificationAlerts } from "../composables/useNotificationAlerts";
import { PLATFORM_Z } from "../constants/zIndex.js";

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
          class="system-notif-card__close"
          :aria-label="t('common.close')"
          @click.stop="dismissToast(toast.key)"
        >
          <n-icon :size="16" :component="CloseOutline" />
        </button>
        <button
          type="button"
          class="system-notif-card__body"
          @click="onOpen(toast)"
        >
          <span class="system-notif-card__icon" aria-hidden="true">
            <n-icon :size="20" :component="NotificationsOutline" />
          </span>
          <span class="system-notif-card__text">
            <strong class="system-notif-card__title">{{ toast.notification.title }}</strong>
            <span v-if="toast.notification.body" class="system-notif-card__desc">
              {{ toast.notification.body }}
            </span>
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
  top: calc(var(--platform-header-height, 56px) + 12px);
  right: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: min(360px, calc(100vw - 32px));
  pointer-events: none;
}

.system-notif-card {
  position: relative;
  pointer-events: auto;
  border-radius: var(--platform-radius-md, 12px);
  border: 1px solid color-mix(in srgb, var(--platform-accent) 35%, var(--platform-border));
  background: var(--platform-surface, #fff);
  box-shadow:
    0 12px 32px color-mix(in srgb, var(--platform-accent) 18%, transparent),
    0 2px 8px rgba(15, 23, 42, 0.08);
  overflow: hidden;
}

.system-notif-card--shake {
  animation: system-notif-shake 0.62s cubic-bezier(0.36, 0.07, 0.19, 0.97);
}

.system-notif-card__close {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--platform-text-tertiary);
  cursor: pointer;
}

.system-notif-card__close:hover {
  background: var(--platform-accent-soft);
  color: var(--platform-accent);
}

.system-notif-card__body {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  width: 100%;
  padding: 14px 40px 14px 14px;
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
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: var(--platform-accent-gradient-soft, rgba(24, 160, 88, 0.12));
  color: var(--platform-accent);
}

.system-notif-card__text {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.system-notif-card__title {
  font-size: 14px;
  font-weight: 600;
  line-height: 1.35;
  color: var(--platform-text);
}

.system-notif-card__desc {
  font-size: 13px;
  line-height: 1.45;
  color: var(--platform-text-secondary);
  word-break: break-word;
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
    transform: translateX(-5px);
  }
  24%,
  48%,
  72% {
    transform: translateX(5px);
  }
}
</style>
