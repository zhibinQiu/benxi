<script setup>
import { onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import {
  NEmpty,
  NIcon,
  NList,
  NListItem,
  NSpace,
  NSpin,
  NThing,
  NTooltip } from "naive-ui";
import { RefreshOutline, CheckmarkDoneOutline } from "@vicons/ionicons5";
import {
  fetchNotifications,
  markAllNotificationsRead,
  markNotificationRead } from "../api/client";
import { useI18n } from "../composables/useI18n";
import { usePlatformUi } from "../composables/usePlatformUi";

const props = defineProps({
  active: {
    type: Boolean,
    default: true}});

const emit = defineEmits(["updated", "navigate"]);

const router = useRouter();
const ui = usePlatformUi();
const { t } = useI18n();
const items = ref([]);
const loading = ref(false);

async function load({ notifyOnError = true } = {}) {
  loading.value = true;
  try {
    const data = await fetchNotifications({ page: 1, page_size: 12 });
    items.value = data.items;
    emit("updated", data);
  } catch (e) {
    if (notifyOnError) ui.error(e);
  } finally {
    loading.value = false;
  }
}

async function markRead(id) {
  try {
    await markNotificationRead(id);
    await load({ notifyOnError: false });
  } catch (e) {
    ui.error(e);
  }
}

async function markAllRead() {
  try {
    const { deleted } = await markAllNotificationsRead();
    if (deleted > 0) {
      ui.success("notifications.messages.clearedAll", { count: deleted });
    } else {
      ui.success("notifications.messages.noneUnread");
    }
    await load({ notifyOnError: false });
  } catch (e) {
    ui.error(e);
  }
}

async function openNotification(n) {
  if (!n.read_at) {
    try {
      await markNotificationRead(n.id);
      n.read_at = new Date().toISOString();
      emit("updated");
    } catch {
      /* ignore */
    }
  }
  if (n.link) {
    emit("navigate");
    router.push(n.link);
  }
}

watch(
  () => props.active,
  (visible) => {
    if (visible) load();
  }
);

onMounted(() => {
  if (props.active) load();
});

defineExpose({ load, refresh: load });
</script>

<template>
  <div class="notifications-panel">
    <header class="notifications-panel__header">
      <strong class="platform-text-gradient notifications-panel__title">
        {{ t("notifications.title") }}
      </strong>
      <div class="notifications-panel__actions">
        <n-tooltip placement="bottom">
          <template #trigger>
            <button
              type="button"
              class="notif-header-btn notif-header-btn--refresh"
              :aria-label="t('common.refresh')"
              :disabled="loading"
              @click="load"
            >
              <n-icon :size="16" :component="RefreshOutline" />
            </button>
          </template>
          {{ t("common.refresh") }}
        </n-tooltip>
        <n-tooltip placement="bottom">
          <template #trigger>
            <button
              type="button"
              class="notif-header-btn notif-header-btn--read"
              :aria-label="t('notifications.markAllRead')"
              @click="markAllRead"
            >
              <n-icon :size="16" :component="CheckmarkDoneOutline" />
            </button>
          </template>
          {{ t("notifications.markAllRead") }}
        </n-tooltip>
      </div>
    </header>

    <n-spin :show="loading">
      <div class="notifications-panel__body">
        <n-list v-if="items.length" bordered>
          <n-list-item
            v-for="n in items"
            :key="n.id"
            :class="{ 'notif-clickable': !!n.link, 'notif-unread': !n.read_at }"
            @click="n.link && openNotification(n)"
          >
            <n-thing :title="n.title" :description="n.body">
              <template #footer>
                <n-space>
                  <span class="notif-time">
                    {{ new Date(n.created_at).toLocaleString() }}
                  </span>
                  <button
                    v-if="!n.read_at"
                    type="button"
                    class="notif-mark-read"
                    @click.stop="markRead(n.id)"
                  >
                    {{ t("notifications.actions.markRead") }}
                  </button>
                  <span v-else class="notif-read">{{ t("notifications.read") }}</span>
                </n-space>
              </template>
            </n-thing>
          </n-list-item>
        </n-list>
        <n-empty v-else :description="t('notifications.empty')" />
      </div>
    </n-spin>
  </div>
</template>

<style scoped>
.notifications-panel {
  width: 100%;
  box-sizing: border-box;
}

.notifications-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 12px 14px 10px;
  border-bottom: 1px solid var(--platform-border);
  background: linear-gradient(
    180deg,
    var(--platform-toolbar-bg) 0%,
    transparent 100%
  );
}

.notifications-panel__title {
  font-size: 15px;
  font-weight: 600;
  letter-spacing: var(--platform-tracking-tight);
}

.notifications-panel__actions {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px;
  border-radius: var(--platform-radius-sm);
  background: var(--platform-bg-elevated-solid);
  border: 1px solid var(--platform-border);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

.notif-header-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  padding: 0;
  border: none;
  border-radius: calc(var(--platform-radius-sm) - 2px);
  cursor: pointer;
  transition:
    transform 0.15s var(--platform-ease-smooth),
    background-color 0.15s ease,
    color 0.15s ease,
    box-shadow 0.15s ease;
}

.notif-header-btn:not(:disabled):hover {
  transform: translateY(-1px);
}

.notif-header-btn:not(:disabled):active {
  transform: translateY(0);
}

.notif-header-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.notif-header-btn--refresh {
  color: var(--platform-accent);
  background: var(--platform-accent-soft);
}

.notif-header-btn--refresh:not(:disabled):hover {
  color: var(--platform-accent-hover, var(--platform-accent));
  background: color-mix(in srgb, var(--platform-accent-soft) 72%, var(--platform-accent) 28%);
  box-shadow: 0 2px 8px color-mix(in srgb, var(--platform-accent) 22%, transparent);
}

.notif-header-btn--read {
  color: var(--platform-accent);
  background: var(--platform-accent-soft);
}

.notif-header-btn--read:not(:disabled):hover {
  background: color-mix(in srgb, var(--platform-accent-soft) 72%, var(--platform-accent) 28%);
  box-shadow: 0 2px 8px color-mix(in srgb, var(--platform-accent) 18%, transparent);
}

.notifications-panel__body {
  max-height: 360px;
  overflow-y: auto;
  padding: 10px 14px 14px;
}

.notifications-panel :deep(.n-list) {
  border: none;
  background: transparent;
}

.notifications-panel :deep(.n-list-item) {
  padding-left: 0;
  padding-right: 0;
  border-radius: var(--platform-radius-sm);
}

.notifications-panel :deep(.n-empty) {
  padding: 16px 0 8px;
}

.notif-clickable {
  cursor: pointer;
}

.notif-clickable:hover {
  background: var(--platform-toolbar-bg);
}

.notif-unread {
  background: var(--platform-accent-soft);
}

.notif-time {
  font-size: 12px;
  color: var(--platform-text-tertiary);
}

.notif-mark-read {
  border: none;
  padding: 0 2px;
  background: transparent;
  font: inherit;
  font-size: 12px;
  font-weight: 500;
  color: var(--platform-accent);
  cursor: pointer;
}

.notif-mark-read:hover {
  color: var(--platform-accent-hover, var(--platform-accent));
  text-decoration: underline;
}

.notif-read {
  font-size: 12px;
  color: var(--platform-text-tertiary);
}
</style>
