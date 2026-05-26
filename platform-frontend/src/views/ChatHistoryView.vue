<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { NButton, NEmpty, NIcon, NSpin, NText, useMessage } from "naive-ui";
import { ArrowBackOutline, ChatbubblesOutline } from "@vicons/ionicons5";
import { fetchChatConversations } from "../api/client";
import { CHAT_SCOPES, chatScopeTitle } from "../constants/chatScopes";

const route = useRoute();
const router = useRouter();
const message = useMessage();

const scope = computed(() => String(route.params.scope || ""));
const pageTitle = computed(() => chatScopeTitle(scope.value));

const loading = ref(false);
const items = ref([]);

const backTarget = computed(() => {
  const meta = CHAT_SCOPES[scope.value];
  if (!meta) return { name: "ai-home" };
  if (meta.routeName) return { name: meta.routeName };
  return { path: route.query.from || "/" };
});

async function loadList() {
  if (!CHAT_SCOPES[scope.value]) {
    message.error("不支持的对话类型");
    router.replace({ name: "ai-home" });
    return;
  }
  loading.value = true;
  try {
    items.value = (await fetchChatConversations(scope.value)) || [];
  } catch (e) {
    message.error(e.message || "加载历史对话失败");
    items.value = [];
  } finally {
    loading.value = false;
  }
}

function openConversation(item) {
  const meta = CHAT_SCOPES[scope.value];
  if (!meta) return;

  if (scope.value === "assistant") {
    router.push({
      path: typeof route.query.from === "string" ? route.query.from : "/",
      query: { assistantConversation: item.id },
    });
    return;
  }

  if (meta.routeName) {
    router.push({
      name: meta.routeName,
      query: { conversationId: item.id },
    });
  }
}

function formatTime(value) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  const now = new Date();
  const sameDay =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate();
  if (sameDay) {
    return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
  }
  return d.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

onMounted(loadList);
watch(scope, loadList);
</script>

<template>
  <div class="chat-history-page">
    <header class="chat-history-header">
      <n-button quaternary circle size="small" aria-label="返回" @click="router.push(backTarget)">
        <template #icon>
          <n-icon :component="ArrowBackOutline" />
        </template>
      </n-button>
      <div class="chat-history-header-text">
        <h1 class="chat-history-title">历史对话</h1>
        <n-text depth="3">{{ pageTitle }}</n-text>
      </div>
    </header>

    <n-spin :show="loading">
      <div v-if="!loading && !items.length" class="chat-history-empty">
        <n-empty description="暂无历史对话" />
      </div>
      <ul v-else class="chat-history-list">
        <li v-for="item in items" :key="item.id">
          <button type="button" class="chat-history-item" @click="openConversation(item)">
            <span class="chat-history-item-icon" aria-hidden="true">
              <n-icon :size="18" :component="ChatbubblesOutline" />
            </span>
            <span class="chat-history-item-body">
              <span class="chat-history-item-title">{{ item.title || "未命名对话" }}</span>
              <span class="chat-history-item-time">{{ formatTime(item.updated_at) }}</span>
            </span>
          </button>
        </li>
      </ul>
    </n-spin>
  </div>
</template>

<style scoped>
.chat-history-page {
  max-width: 720px;
  margin: 0 auto;
  padding: 16px 20px 32px;
}

.chat-history-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 20px;
}

.chat-history-header-text {
  min-width: 0;
}

.chat-history-title {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
  color: #0f172a;
  line-height: 1.3;
}

.chat-history-empty {
  padding: 48px 0;
}

.chat-history-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.chat-history-item {
  width: 100%;
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 16px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 12px;
  background: #fff;
  cursor: pointer;
  text-align: left;
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease;
}

.chat-history-item:hover {
  border-color: rgba(13, 148, 136, 0.35);
  box-shadow: 0 4px 16px rgba(13, 148, 136, 0.08);
}

.chat-history-item-icon {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  color: #0d9488;
  background: rgba(13, 148, 136, 0.1);
}

.chat-history-item-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.chat-history-item-title {
  font-size: 14px;
  font-weight: 500;
  color: #0f172a;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-history-item-time {
  font-size: 12px;
  color: #94a3b8;
}
</style>
