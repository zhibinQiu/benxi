<script setup>
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import {
  NCard,
  NList,
  NListItem,
  NThing,
  NButton,
  NSpace,
  NEmpty,
  NPopconfirm,
  useMessage,
} from "naive-ui";
import {
  clearNotifications,
  fetchNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from "../api/client";

const router = useRouter();
const message = useMessage();
const items = ref([]);
const loading = ref(false);

async function load() {
  loading.value = true;
  try {
    const data = await fetchNotifications({ page: 1 });
    items.value = data.items;
  } catch (e) {
    message.error(e.message);
  } finally {
    loading.value = false;
  }
}

async function markRead(id) {
  try {
    await markNotificationRead(id);
    await load();
  } catch (e) {
    message.error(e.message);
  }
}

async function markAllRead() {
  try {
    const { updated } = await markAllNotificationsRead();
    message.success(updated ? `已标记 ${updated} 条为已读` : "暂无未读消息");
    await load();
  } catch (e) {
    message.error(e.message);
  }
}

async function doClear(scope) {
  try {
    const { deleted } = await clearNotifications(scope);
    message.success(deleted ? `已删除 ${deleted} 条消息` : "没有可删除的消息");
    await load();
  } catch (e) {
    message.error(e.message);
  }
}

async function openNotification(n) {
  if (!n.read_at) {
    try {
      await markNotificationRead(n.id);
      n.read_at = new Date().toISOString();
    } catch {
      /* ignore */
    }
  }
  if (n.link) {
    router.push(n.link);
  }
}

onMounted(load);
</script>

<template>
  <n-card title="消息中心">
    <template #header-extra>
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
    </template>
    <n-list v-if="items.length" bordered>
      <n-list-item
        v-for="n in items"
        :key="n.id"
        :class="{ 'notif-clickable': !!n.link }"
        @click="n.link && openNotification(n)"
      >
        <n-thing :title="n.title" :description="n.body">
          <template #footer>
            <n-space>
              <span style="font-size: 12px; color: #888">
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
              <span v-else style="font-size: 12px; color: #18a058">已读</span>
            </n-space>
          </template>
        </n-thing>
      </n-list-item>
    </n-list>
    <n-empty v-else description="暂无消息" />
  </n-card>
</template>

<style scoped>
.notif-clickable {
  cursor: pointer;
}
.notif-clickable:hover {
  background: var(--n-action-color);
}
</style>
