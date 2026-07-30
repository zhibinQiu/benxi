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
import { RefreshOutline, CheckmarkDoneOutline, TrashOutline } from "@vicons/ionicons5";
import {
  fetchNotifications,
  markAllNotificationsRead,
  markNotificationRead } from "../api/client";
import { clearAllNotifications } from "../api/notifications";
import { LIST_PAGE_SIZE } from "../constants/listPage.js";
import { useI18n } from "../composables/useI18n";
import { usePlatformUi } from "../composables/usePlatformUi";
import { renderMarkdown } from "../utils/markdown.js";

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
      <strong class="notifications-panel__title">
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
              <n-icon :size="15" :component="RefreshOutline" />
            </button>
          </template>
          {{ t("common.refresh") }}
        </n-tooltip>
        <n-tooltip placement="bottom">
          <template #trigger>
            <button
              type="button"
              class="panel-header-btn"
              :aria-label="t('notifications.markAllRead')"
              :disabled="loading || clearing"
              @click="markAllRead"
            >
              <n-icon :size="15" :component="CheckmarkDoneOutline" />
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
              <n-icon :size="15" :component="TrashOutline" />
            </button>
          </template>
          {{ t("notifications.actions.delete") }}
        </n-tooltip>
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
            <n-thing :title="n.title">
              <template v-if="n.body" #description>
                <div class="notif-body" v-html="renderMarkdown(n.body)" />
              </template>
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
  padding: 10px 14px 8px;
  border-bottom: 1px solid var(--platform-border);
  background: transparent;
}

.notifications-panel__title {
  font-size: 13px;
  font-weight: 600;
  color: var(--platform-text);
  letter-spacing: var(--platform-tracking-tight);
}

.notifications-panel__actions {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 2px;
}

.notifications-panel__body {
  max-height: 432px;
  overflow-y: auto;
  padding: 8px 14px 14px;
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
  padding: 6px 4px;
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
  font-size: var(--platform-font-size-sm);
  line-height: 1.35;
}

.notifications-panel :deep(.n-thing .n-thing-main__description) {
  font-size: 11px;
  line-height: 1.4;
  margin-top: 2px;
}

.notif-body {
  word-break: break-word;
}

.notif-body :deep(p) {
  margin: 0 0 0.35em;
}

.notif-body :deep(p:last-child) {
  margin-bottom: 0;
}

.notif-body :deep(ul),
.notif-body :deep(ol) {
  margin: 0.2em 0;
  padding-left: 1.25em;
}

.notif-body :deep(a) {
  color: var(--platform-accent);
}

.notif-body :deep(code) {
  font-size: 0.95em;
  padding: 0.05em 0.3em;
  border-radius: 3px;
  background: var(--platform-toolbar-bg);
}

.notif-body :deep(pre) {
  margin: 0.35em 0;
  padding: 6px 8px;
  overflow-x: auto;
  border-radius: var(--platform-radius-sm, 6px);
  background: var(--platform-toolbar-bg);
  font-size: 11px;
}

.notifications-panel :deep(.n-thing .n-thing-main__footer) {
  margin-top: 4px;
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
  top: 8px;
  bottom: 8px;
  width: 3px;
  border-radius: 2px;
  background: var(--platform-accent);
}

.notif-time {
  font-size: 11px;
  color: var(--platform-text-tertiary);
}

.notif-mark-read {
  border: none;
  padding: 0 2px;
  background: transparent;
  font: inherit;
  font-size: 11px;
  font-weight: 500;
  color: var(--platform-accent);
  cursor: pointer;
}

.notif-mark-read:hover {
  color: var(--platform-accent-hover, var(--platform-accent));
  text-decoration: underline;
}

.notif-read {
  font-size: 11px;
  color: var(--platform-text-tertiary);
}

.notifications-panel__header .panel-header-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  min-width: 24px;
  padding: 0;
  border: none;
  border-radius: var(--platform-radius-sm, 6px);
  background: transparent;
  color: var(--platform-text-secondary);
  cursor: pointer;
  transition:
    background-color 0.15s ease,
    color 0.15s ease;
}

.notifications-panel__header .panel-header-btn:not(:disabled):hover {
  background: var(--platform-accent-soft);
  color: var(--platform-accent);
  transform: none;
  box-shadow: none;
}

.notifications-panel__header .panel-header-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.notifications-panel__header .panel-header-btn--danger:not(:disabled):hover {
  background: color-mix(in srgb, var(--platform-error, #d03050) 12%, transparent);
  color: var(--platform-error, #d03050);
}
</style>
