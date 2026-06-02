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
  useMessage,
} from "naive-ui";
import {
  clearNotifications,
  fetchNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from "../api/client";

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
const message = useMessage();
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
    if (notifyOnError) message.error(e.message);
  } finally {
    loading.value = false;
  }
}

async function markRead(id) {
  try {
    await markNotificationRead(id);
    await load({ notifyOnError: false });
  } catch (e) {
    message.error(e.message);
  }
}

async function markAllRead() {
  try {
    const { updated } = await markAllNotificationsRead();
    message.success(updated ? `已标记 ${updated} 条为已读` : "暂无未读消息");
    await load({ notifyOnError: false });
  } catch (e) {
    message.error(e.message);
  }
}

async function doClear(scope) {
  try {
    const { deleted } = await clearNotifications(scope);
    message.success(deleted ? `已删除 ${deleted} 条消息` : "没有可删除的消息");
    await load({ notifyOnError: false });
  } catch (e) {
    message.error(e.message);
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
      <n-text strong>消息</n-text>
      <n-space :size="6">
        <n-button text type="primary" size="small" @click="load">刷新</n-button>
        <n-button text type="primary" size="small" @click="markAllRead">全部已读</n-button>
        <n-button text type="primary" size="small" @click="goNotificationsPage">
          查看全部
        </n-button>
      </n-space>
    </div>

    <div v-else class="notifications-panel__toolbar">
      <n-space :size="8">
        <n-button size="small" @click="load">刷新</n-button>
        <n-button size="small" @click="markAllRead">全部已读</n-button>
        <n-popconfirm @positive-click="doClear('read')">
          <template #trigger>
            <n-button size="small">清空已读</n-button>
          </template>
          将删除所有已读消息，确定继续？
        </n-popconfirm>
        <n-popconfirm @positive-click="doClear('all')">
          <template #trigger>
            <n-button size="small" secondary>清空全部</n-button>
          </template>
          将删除全部消息记录，确定继续？
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
                    标为已读
                  </n-button>
                  <span v-else class="notif-read">已读</span>
                </n-space>
              </template>
            </n-thing>
          </n-list-item>
        </n-list>
        <n-empty v-else description="暂无消息" />
      </div>
    </n-spin>
  </div>
</template>

<style scoped>
.notifications-panel--popover {
  width: min(400px, calc(100vw - 32px));
  padding: 12px 14px;
  background: var(--n-color);
  border-radius: var(--n-border-radius);
  box-sizing: border-box;
}

.notifications-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--n-divider-color);
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
  background: var(--n-action-color);
}

.notif-unread {
  background: rgba(13, 148, 136, 0.06);
}

.notif-time {
  font-size: 12px;
  color: #888;
}

.notif-read {
  font-size: 12px;
  color: #18a058;
}
</style>
