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
  useMessage,
} from "naive-ui";
import { fetchNotifications, markNotificationRead } from "../api/client";

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
      <n-button size="small" @click="load">刷新</n-button>
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
