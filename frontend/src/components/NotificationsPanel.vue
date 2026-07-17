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
import { RefreshOutline, CheckmarkDoneOutline, CloseOutline, TrashOutline } from "@vicons/ionicons5";
import {
  fetchNotifications,
  markAllNotificationsRead,
  markNotificationRead } from "../api/client";
import { clearAllNotifications } from "../api/notifications";
import { LIST_PAGE_SIZE } from "../constants/listPage.js";
import { useI18n } from "../composables/useI18n";
import { usePlatformUi } from "../composables/usePlatformUi";

const props = defineProps({
  active: {
    type: Boolean,
    default: true}});

const emit = defineEmits(["updated", "navigate", "close"]);

const router = useRouter();
const ui = usePlatformUi();
const { t } = useI18n();
const items = ref([]);
const loading = ref(false);
const clearing = ref(false);

async function load({ notifyOnError = true } = {}) {
  loading.value = true;
  try {
    const data = await fetchNotifications({ page: 1, page_size: LIST_PAGE_SIZE });
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
    const { updated } = await markAllNotificationsRead();
    if (updated > 0) {
      ui.success("notifications.messages.markedRead", { count: updated });
    } else {
      ui.success("notifications.messages.noneUnread");
    }
    await load({ notifyOnError: false });
  } catch (e) {
    ui.error(e);
  }
}

async function clearAll() {
  clearing.value = true;
  try {
    const { deleted } = await clearAllNotifications();
    if (deleted > 0) {
      ui.success("notifications.messages.clearedAll", { count: deleted });
    } else {
      ui.success("notifications.messages.noneUnread");
    }
    await load({ notifyOnError: false });
  } catch (e) {
    ui.error(e);
  } finally {
    clearing.value = false;
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

defineExpose({ load, refresh: load, markAllRead, clearAll });
</script>

<template>
  <div class="notifications-panel">
    <header class="notifications-panel__header">
      <strong class="platform-text-gradient notifications-panel__title">
        {{ t("notifications.title") }}
      </strong>
      <div class="notifications-panel__actions panel-header-actions">
        <n-tooltip placement="bottom">
          <template #trigger>
            <button
              type="button"
              class="panel-header-btn"
              :aria-label="t('common.refresh')"
              :disabled="loading"
              @click="load"
            >
              <n-icon :size="18" :component="RefreshOutline" />
            </button>
          </template>
          {{ t("common.refresh") }}
        </n-tooltip>
        <n-tooltip placement="bottom">
          <template #trigger>
            <button
              type="button"
              class="panel-header-btn panel-header-btn--accent"
              :aria-label="t('notifications.markAllRead')"
              :disabled="loading || clearing"
              @click="markAllRead"
            >
              <n-icon :size="18" :component="CheckmarkDoneOutline" />
            </button>
          </template>
          {{ t("notifications.markAllRead") }}
        </n-tooltip>
        <n-tooltip placement="bottom">
          <template #trigger>
            <button
              type="button"
              class="panel-header-btn panel-header-btn--danger"
              :aria-label="t('notifications.actions.delete')"
              :disabled="loading || clearing"
              @click="clearAll"
            >
              <n-icon :size="18" :component="TrashOutline" />
            </button>
          </template>
          {{ t("notifications.actions.delete") }}
        </n-tooltip>
        <div class="panel-header-sep" />
        <button
          type="button"
          class="panel-header-btn"
          aria-label="关闭"
          @click="emit('close')"
        >
          <n-icon :size="18" :component="CloseOutline" />
        </button>
      </div>
    </header>

    <n-spin :show="loading" local>
      <div class="notifications-panel__body">
        <n-list v-if="items.length" class="notif-list">
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
  gap: 12px;
  padding: 14px 17px 12px;
  border-bottom: 1px solid var(--platform-border);
  background: linear-gradient(
    180deg,
    var(--platform-toolbar-bg) 0%,
    transparent 100%
  );
}

.notifications-panel__title {
  font-size: 16px;
  font-weight: 600;
  letter-spacing: var(--platform-tracking-tight);
}

.notifications-panel__actions {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 4px;
}

.notifications-panel__body {
  max-height: 432px;
  overflow-y: auto;
  padding: 8px 16px 14px;
}

.notifications-panel :deep(.n-list) {
  border: none;
  background: transparent;
}

.notifications-panel :deep(.notif-list .n-list-item) {
  padding-left: 0;
  padding-right: 0;
  border-radius: var(--platform-radius-sm);
  margin: 0 -4px;
  padding: 10px 4px;
  border-bottom: 1px solid var(--platform-border);
  transition:
    background-color 0.2s ease,
    box-shadow 0.2s ease;
}

.notifications-panel :deep(.notif-list .n-list-item:last-child) {
  border-bottom: none;
}

.notifications-panel :deep(.n-list-item:hover) {
  background: var(--platform-toolbar-bg) !important;
}

.notifications-panel :deep(.n-thing .n-thing-header__title) {
  font-size: 13px;
}

.notifications-panel :deep(.n-thing .n-thing-main__description) {
  font-size: 12px;
}

.notifications-panel :deep(.n-empty) {
  padding: 19px 0 10px;
}

.notif-clickable {
  cursor: pointer;
}

.notif-clickable:hover {
  background: var(--platform-toolbar-bg);
}

.notif-unread {
  background: var(--platform-accent-soft);
  position: relative;
}

.notif-unread::before {
  content: "";
  position: absolute;
  left: 0;
  top: 12px;
  bottom: 12px;
  width: 3px;
  border-radius: 2px;
  background: var(--platform-accent);
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

/* panel-header-btn — 通用头部图标按钮 */
:deep(.panel-header-btn) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: var(--platform-radius-sm, 6px);
  background: transparent;
  color: var(--platform-text-secondary);
  cursor: pointer;
  transition:
    background-color 0.15s ease,
    color 0.15s ease;
}

:deep(.panel-header-btn:hover) {
  background: var(--platform-accent-soft);
  color: var(--platform-accent);
}

:deep(.panel-header-btn:disabled) {
  opacity: 0.4;
  cursor: not-allowed;
}

:deep(.panel-header-btn--accent:hover) {
  background: var(--platform-accent-soft);
  color: var(--platform-accent);
}

:deep(.panel-header-btn--danger:hover) {
  background: color-mix(in srgb, var(--platform-error, #d03050) 12%, transparent);
  color: var(--platform-error, #d03050);
}

.panel-header-sep {
  width: 1px;
  height: 18px;
  background: var(--platform-border);
  flex-shrink: 0;
  margin: 0 2px;
}
</style>
