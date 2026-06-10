<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  NButton,
  NCheckbox,
  NEmpty,
  NIcon,
  NSpin,
  NText,
  useDialog,
  useMessage,
} from "naive-ui";
import { ArrowBackOutline, ChatbubblesOutline, TrashOutline } from "@vicons/ionicons5";
import IconAction from "../components/IconAction.vue";
import {
  clearChatConversations,
  deleteChatConversation,
  fetchChatConversations,
} from "../api/client";
import { CHAT_SCOPES, chatScopeTitle } from "../constants/chatScopes";
import { resolveReturnTarget } from "../utils/navigationReturn";
import { deleteSequentially } from "../utils/batchActions";

const route = useRoute();
const router = useRouter();
const message = useMessage();
const dialog = useDialog();

const scope = computed(() => String(route.params.scope || ""));
const pageTitle = computed(() => chatScopeTitle(scope.value));

const loading = ref(false);
const clearing = ref(false);
const batchDeleting = ref(false);
const items = ref([]);
const selectedIds = ref([]);

const backTarget = computed(() => {
  const fromReturn = resolveReturnTarget(route);
  if (fromReturn) return fromReturn;
  const meta = CHAT_SCOPES[scope.value];
  if (!meta) return { name: "ai-home" };
  if (meta.routeName) return { name: meta.routeName };
  return { path: route.query.from || "/" };
});

const canClear = computed(() => !loading.value && items.value.length > 0);
const selectedCount = computed(() => selectedIds.value.length);
const canBatchDelete = computed(() => selectedCount.value > 0 && !batchDeleting.value);

function isSelected(id) {
  return selectedIds.value.includes(id);
}

function toggleSelected(id, checked) {
  if (checked) {
    if (!selectedIds.value.includes(id)) selectedIds.value = [...selectedIds.value, id];
  } else {
    selectedIds.value = selectedIds.value.filter((x) => x !== id);
  }
}

async function loadList() {
  if (!CHAT_SCOPES[scope.value]) {
    message.error("不支持的对话类型");
    router.replace({ name: "ai-home" });
    return;
  }
  loading.value = true;
  try {
    items.value = (await fetchChatConversations(scope.value)) || [];
    selectedIds.value = [];
  } catch (e) {
    message.error(e.message || "加载历史对话失败");
    items.value = [];
    selectedIds.value = [];
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

function handleBatchDelete() {
  const rows = items.value.filter((row) => selectedIds.value.includes(row.id));
  if (!rows.length) return;
  const summary = rows.length === 1 ? "该对话" : `选中的 ${rows.length} 条对话`;
  dialog.warning({
    title: "批量删除对话",
    content: `确定永久删除${summary}？删除后无法恢复。`,
    positiveText: "永久删除",
    negativeText: "取消",
    onPositiveClick: async () => {
      batchDeleting.value = true;
      try {
        const { deleted, failed } = await deleteSequentially(rows, (row) =>
          deleteChatConversation(scope.value, row.id)
        );
        items.value = items.value.filter((row) => !selectedIds.value.includes(row.id));
        selectedIds.value = [];
        if (failed.length) {
          message.warning(
            `已删除 ${deleted} 条，${failed.length} 条失败：${failed[0].message || "未知错误"}`
          );
        } else {
          message.success(deleted > 1 ? `已永久删除 ${deleted} 条对话` : "已永久删除该对话");
        }
      } catch (e) {
        message.error(e.message || "删除失败");
        return false;
      } finally {
        batchDeleting.value = false;
      }
      return true;
    },
  });
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
        selectedIds.value = [];
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
      <n-space align="center" :size="4" class="chat-history-actions">
        <IconAction
          label="删除"
          :icon="TrashOutline"
          type="error"
          :disabled="!canBatchDelete"
          @click="handleBatchDelete"
        />
        <IconAction
          v-if="canClear"
          label="清空全部"
          :icon="TrashOutline"
          type="error"
          @click="onClearAll"
        />
      </n-space>
    </header>

    <div v-if="selectedCount > 0" class="chat-history-selection-hint">
      已选 {{ selectedCount }} 项
    </div>

    <n-spin :show="loading">
      <div v-if="!loading && !items.length" class="chat-history-empty">
        <n-empty description="暂无历史对话" />
      </div>
      <ul v-else class="chat-history-list">
        <li v-for="item in items" :key="item.id" class="chat-history-row">
          <n-checkbox
            :checked="isSelected(item.id)"
            class="chat-history-select"
            @update:checked="(v) => toggleSelected(item.id, v)"
            @click.stop
          />
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
  flex: 1;
  min-width: 0;
}

.chat-history-actions {
  flex-shrink: 0;
  margin-left: auto;
}

.chat-history-selection-hint {
  margin: -8px 0 12px;
  font-size: 13px;
  color: #666;
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
  gap: 8px;
}

.chat-history-select {
  flex-shrink: 0;
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
  border-color: var(--platform-accent-border);
  box-shadow: 0 4px 16px color-mix(in srgb, var(--platform-accent) 8%, transparent);
}

.chat-history-item-icon {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  color: var(--platform-accent);
  background: var(--platform-accent-soft);
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
