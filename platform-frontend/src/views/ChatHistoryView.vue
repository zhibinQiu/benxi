<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  NButton,
  NEmpty,
  NIcon,
  NPopconfirm,
  NSpin,
  NText,
  useDialog,
  useMessage,
} from "naive-ui";
import { ArrowBackOutline, ChatbubblesOutline, TrashOutline } from "@vicons/ionicons5";
import {
  clearChatConversations,
  deleteChatConversation,
  fetchChatConversations,
} from "../api/client";
import { CHAT_SCOPES, chatScopeTitle } from "../constants/chatScopes";
import { resolveReturnTarget } from "../utils/navigationReturn";

const route = useRoute();
const router = useRouter();
const message = useMessage();
const dialog = useDialog();

const scope = computed(() => String(route.params.scope || ""));
const pageTitle = computed(() => chatScopeTitle(scope.value));

const loading = ref(false);
const clearing = ref(false);
const deletingId = ref("");
const items = ref([]);

const backTarget = computed(() => {
  const fromReturn = resolveReturnTarget(route);
  if (fromReturn) return fromReturn;
  const meta = CHAT_SCOPES[scope.value];
  if (!meta) return { name: "ai-home" };
  if (meta.routeName) return { name: meta.routeName };
  return { path: route.query.from || "/" };
});

const canClear = computed(() => !loading.value && items.value.length > 0);

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

async function onDeleteItem(item) {
  deletingId.value = item.id;
  try {
    await deleteChatConversation(scope.value, item.id);
    items.value = items.value.filter((row) => row.id !== item.id);
    message.success("已永久删除该对话");
  } catch (e) {
    message.error(e.message || "删除失败");
  } finally {
    deletingId.value = "";
  }
}

function onClearAll() {
  dialog.warning({
    title: "清空全部历史对话",
    content: "将永久删除当前场景下的全部历史对话，且无法恢复。确定继续？",
    positiveText: "永久删除",
    negativeText: "取消",
    onPositiveClick: async () => {
      clearing.value = true;
      try {
        const res = await clearChatConversations(scope.value);
        items.value = [];
        const n = res?.deleted ?? 0;
        message.success(n > 0 ? `已永久删除 ${n} 条对话` : "已清空");
      } catch (e) {
        message.error(e.message || "清空失败");
        return false;
      } finally {
        clearing.value = false;
      }
      return true;
    },
  });
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
      <n-button
        v-if="canClear"
        size="small"
        type="error"
        tertiary
        :loading="clearing"
        class="chat-history-clear-all"
        @click="onClearAll"
      >
        清空全部
      </n-button>
    </header>

    <n-spin :show="loading">
      <div v-if="!loading && !items.length" class="chat-history-empty">
        <n-empty description="暂无历史对话" />
      </div>
      <ul v-else class="chat-history-list">
        <li v-for="item in items" :key="item.id" class="chat-history-row">
          <button type="button" class="chat-history-item" @click="openConversation(item)">
            <span class="chat-history-item-icon" aria-hidden="true">
              <n-icon :size="18" :component="ChatbubblesOutline" />
            </span>
            <span class="chat-history-item-body">
              <span class="chat-history-item-title">{{ item.title || "未命名对话" }}</span>
              <span class="chat-history-item-time">{{ formatTime(item.updated_at) }}</span>
            </span>
          </button>
          <n-popconfirm
            positive-text="永久删除"
            negative-text="取消"
            @positive-click="onDeleteItem(item)"
          >
            <template #trigger>
              <n-button
                quaternary
                circle
                size="small"
                class="chat-history-delete"
                aria-label="删除对话"
                :loading="deletingId === item.id"
                @click.stop
              >
                <template #icon>
                  <n-icon :component="TrashOutline" />
                </template>
              </n-button>
            </template>
            永久删除该对话？删除后无法恢复。
          </n-popconfirm>
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
  flex: 1;
  min-width: 0;
}

.chat-history-clear-all {
  flex-shrink: 0;
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

.chat-history-row {
  display: flex;
  align-items: center;
  gap: 4px;
}

.chat-history-item {
  flex: 1;
  min-width: 0;
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

.chat-history-delete {
  flex-shrink: 0;
  color: #94a3b8;
}

.chat-history-delete:hover {
  color: #dc2626;
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
