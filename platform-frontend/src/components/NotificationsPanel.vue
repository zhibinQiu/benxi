<script setup>
import { onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import {
  NButton,
  NEmpty,
  NList,
  NListItem,
  NPopconfirm,
  NSpace,
  NSpin,
  NText,
  NThing,
} from "naive-ui";
import { RefreshOutline, TrashOutline, CheckmarkDoneOutline } from "@vicons/ionicons5";
import {
  clearNotifications,
  fetchNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from "../api/client";
import IconAction from "./IconAction.vue";
import { useI18n } from "../composables/useI18n";
import { usePlatformUi } from "../composables/usePlatformUi";

const props = defineProps({
  variant: {
    type: String,
    default: "page",
    validator: (v) => v === "page" || v === "popover",
  },
  active: {
    type: Boolean,
    default: true,
  },
});

const emit = defineEmits(["updated", "navigate"]);

const router = useRouter();
const ui = usePlatformUi();
const { t } = useI18n();
const items = ref([]);
const loading = ref(false);

async function load({ notifyOnError = true } = {}) {
  loading.value = true;
  try {
    const pageSize = props.variant === "popover" ? 12 : 20;
    const data = await fetchNotifications({ page: 1, page_size: pageSize });
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
    ui.success(updated ? "notifications.messages.markedRead" : "notifications.messages.noneUnread", {
      count: updated || 0,
    });
    await load({ notifyOnError: false });
  } catch (e) {
    ui.error(e);
  }
}

async function doClear(scope) {
  try {
    const { deleted } = await clearNotifications(scope);
    ui.success(
      deleted ? "notifications.messages.cleared" : "notifications.messages.nothingToClear",
      { count: deleted || 0 }
    );
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

function goNotificationsPage() {
  emit("navigate");
  router.push({ name: "notifications" });
}

watch(
  () => props.active,
  (visible) => {
    if (visible) load();
  }
);

onMounted(() => {
  if (props.variant === "page" || props.active) load();
});

defineExpose({ load, refresh: load });
</script>

<template>
  <div
    :class="[
      'notifications-panel',
      { 'notifications-panel--popover': variant === 'popover' },
    ]"
  >
    <div v-if="variant === 'popover'" class="notifications-panel__header">
      <n-text strong>{{ t("notifications.title") }}</n-text>
      <n-space :size="4">
        <IconAction :label="t('common.refresh')" :icon="RefreshOutline" size="tiny" @click="load" />
        <IconAction
          :label="t('notifications.markAllRead')"
          :icon="CheckmarkDoneOutline"
          size="tiny"
          @click="markAllRead"
        />
        <n-button text type="primary" size="small" @click="goNotificationsPage">
          {{ t("common.viewAll") }}
        </n-button>
      </n-space>
    </div>

    <div v-else class="notifications-panel__toolbar">
      <n-space :size="6">
        <IconAction :label="t('common.refresh')" :icon="RefreshOutline" @click="load" />
        <IconAction
          :label="t('notifications.markAllRead')"
          :icon="CheckmarkDoneOutline"
          @click="markAllRead"
        />
        <n-popconfirm @positive-click="doClear('read')">
          <template #trigger>
            <IconAction :label="t('notifications.actions.delete')" :icon="TrashOutline" />
          </template>
          {{ t("notifications.confirm.clearRead") }}
        </n-popconfirm>
        <n-popconfirm @positive-click="doClear('all')">
          <template #trigger>
            <IconAction :label="t('notifications.clearAll')" :icon="TrashOutline" type="default" />
          </template>
          {{ t("notifications.confirm.clearAll") }}
        </n-popconfirm>
      </n-space>
    </div>

    <n-spin :show="loading">
      <div
        :class="[
          'notifications-panel__body',
          { 'notifications-panel__body--popover': variant === 'popover' },
        ]"
      >
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
                  <n-button
                    v-if="!n.read_at"
                    text
                    type="primary"
                    size="small"
                    @click.stop="markRead(n.id)"
                  >
                    {{ t("notifications.actions.markRead") }}
                  </n-button>
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
.notifications-panel--popover {
  width: min(400px, calc(100vw - 32px));
  padding: 12px 14px;
  background: var(--platform-bg-elevated);
  border: 1px solid var(--platform-border);
  border-radius: var(--platform-radius);
  box-sizing: border-box;
  box-shadow: var(--platform-shadow-lg);
}

.notifications-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--platform-border);
}

.notifications-panel__toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 12px;
}

.notifications-panel__body--popover {
  max-height: 360px;
  overflow-y: auto;
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

.notif-read {
  font-size: 12px;
  color: var(--platform-accent);
}
</style>
