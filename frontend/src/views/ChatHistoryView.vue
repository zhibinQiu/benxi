<script setup>
import { usePlatformUi } from "../composables/usePlatformUi";
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  NButton,
  NCheckbox,
  NEmpty,
  NIcon,
  NInput,
  NSpin } from "naive-ui";
import { ChatbubblesOutline, SearchOutline, TrashOutline } from "@vicons/ionicons5";
import IconAction from "../components/IconAction.vue";
import {
  deleteChatConversation,
  fetchChatConversations } from "../api/client";
import { CHAT_SCOPES } from "../constants/chatScopes";
import { useI18n } from "../composables/useI18n.js";
import { resolveReturnTarget } from "../utils/navigationReturn";
import { deleteSequentially } from "../utils/batchActions";
import ListTableFooter from "../components/ListTableFooter.vue";
import { LIST_PAGE_SIZE } from "../constants/listPage.js";

const route = useRoute();
const router = useRouter();
const ui = usePlatformUi();
const { t, locale } = useI18n();

const dateLocale = computed(() => (locale.value === "zh" ? "zh-CN" : "en-US"));

const scope = computed(() => String(route.params.scope || ""));

const loading = ref(false);
const batchDeleting = ref(false);
const items = ref([]);
const selectedIds = ref([]);
const page = ref(1);
const searchQuery = ref("");

const filteredItems = computed(() => {
  const q = searchQuery.value.trim().toLowerCase();
  if (!q) return items.value;
  return items.value.filter((item) => {
    const title = (item.title || "").toLowerCase();
    return title.includes(q);
  });
});

const pagedItems = computed(() => {
  const start = (page.value - 1) * LIST_PAGE_SIZE;
  return filteredItems.value.slice(start, start + LIST_PAGE_SIZE);
});

const filteredCount = computed(() => filteredItems.value.length);

function onPageChange(next) {
  page.value = next;
}

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
    ui.error(t("chatHistory.unsupportedScope"));
    router.replace({ name: "ai-home" });
    return;
  }
  loading.value = true;
  try {
    items.value = (await fetchChatConversations(scope.value)) || [];
    selectedIds.value = [];
    page.value = 1;
  } catch (e) {
    ui.error(e.message || t("chatHistory.loadFailed"));
    items.value = [];
    selectedIds.value = [];
  } finally {
    loading.value = false;
  }
}

function openConversation(item) {
  const meta = CHAT_SCOPES[scope.value];
  if (!meta || !item?.id) return;

  if (scope.value === "assistant") {
    const target = resolveReturnTarget(route) || { name: "ai-home", query: {}, params: {} };
    router.push({
      name: target.name,
      params: target.params || {},
      query: { ...(target.query || {}), assistantConversation: item.id },
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
  const content =
    rows.length === 1
      ? t("chatHistory.batchDeleteContentSingle")
      : t("chatHistory.batchDeleteContentMulti", { count: rows.length });
  ui.confirmDelete({
    title: t("chatHistory.batchDeleteTitle"),
    content,
    positiveText: t("chatHistory.permanentlyDelete"),
    onPositive: async () => {
      batchDeleting.value = true;
      try {
        const { deleted, failed } = await deleteSequentially(rows, (row) =>
          deleteChatConversation(scope.value, row.id)
        );
        items.value = items.value.filter((row) => !selectedIds.value.includes(row.id));
        selectedIds.value = [];
        if (failed.length) {
          ui.warning(
            t("chatHistory.batchDeletePartial", {
              deleted,
              failed: failed.length,
              error: failed[0].message || t("chatHistory.unknownError"),
            })
          );
        } else {
          ui.success(
            deleted > 1
              ? t("chatHistory.batchDeleteSuccessMulti", { count: deleted })
              : t("chatHistory.batchDeleteSuccessSingle")
          );
        }
      } finally {
        batchDeleting.value = false;
      }
    }});
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
    return d.toLocaleTimeString(dateLocale.value, { hour: "2-digit", minute: "2-digit" });
  }
  return d.toLocaleString(dateLocale.value, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"});
}

onMounted(loadList);
watch(scope, loadList);
watch(searchQuery, () => {
  page.value = 1;
});
</script>

<template>
  <div class="chat-history-page">
    <header class="chat-history-header">
      <n-space align="center" :size="5" class="chat-history-actions">
        <IconAction
          :label="t('chatHistory.delete')"
          :icon="TrashOutline"
          type="error"
          :disabled="!canBatchDelete"
          @click="handleBatchDelete"
        />
      </n-space>
    </header>

    <div v-if="selectedCount > 0" class="chat-history-selection-hint">
      {{ t("common.selectedCount", { count: selectedCount }) }}
    </div>

    <div class="chat-history-search">
      <n-input
        v-model:value="searchQuery"
        :placeholder="t('chatHistory.searchPlaceholder')"
        clearable
        size="small"
      >
        <template #prefix>
          <n-icon :component="SearchOutline" />
        </template>
      </n-input>
    </div>

    <n-spin :show="loading" local>
      <div v-if="!loading && !filteredCount" class="chat-history-empty">
        <n-empty :description="searchQuery.trim() ? t('chatHistory.noSearchResults') : t('chatHistory.empty')" />
      </div>
      <div v-else class="admin-list-table">
        <ul class="chat-history-list">
          <li v-for="item in pagedItems" :key="item.id" class="chat-history-row">
            <n-checkbox
              :checked="isSelected(item.id)"
              class="chat-history-select"
              @update:checked="(v) => toggleSelected(item.id, v)"
              @click.stop
            />
            <button type="button" class="chat-history-item" @click="openConversation(item)">
              <span class="chat-history-item-icon" aria-hidden="true">
                <n-icon :size="22" :component="ChatbubblesOutline" />
              </span>
              <span class="chat-history-item-body">
                <span class="chat-history-item-title">{{ item.title || t("chatHistory.unnamedConversation") }}</span>
                <span class="chat-history-item-time">{{ formatTime(item.updated_at) }}</span>
              </span>
            </button>
          </li>
        </ul>
        <ListTableFooter
          :page="page"
          :page-size="LIST_PAGE_SIZE"
          :item-count="filteredCount"
          @update:page="onPageChange"
        />
      </div>
    </n-spin>
  </div>
</template>

<style scoped>
.chat-history-page {
  max-width: 864px;
  margin: 0 auto;
  padding: 16px 24px 38px;
}

.chat-history-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 12px;
}

.chat-history-actions {
  flex-shrink: 0;
  margin-left: auto;
}

.chat-history-selection-hint {
  margin: -6px 0 10px;
  font-size: 13px;
  color: #666;
}

.chat-history-search {
  margin-bottom: 12px;
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
  gap: 5px;
  border-radius: var(--platform-card-radius);
  background: var(--platform-card-bg);
  border: 1px solid var(--platform-card-border-color);
  box-shadow: none;
  overflow: hidden;
}

.chat-history-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 8px;
}

.chat-history-row:not(:last-child) .chat-history-item {
  border-bottom: 1px solid color-mix(in srgb, var(--platform-divider) 72%, transparent);
}

.chat-history-select {
  flex-shrink: 0;
}

.chat-history-item {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border: none;
  border-radius: 0;
  background: transparent;
  cursor: pointer;
  text-align: left;
  transition: background-color 0.15s ease;
}

.chat-history-item:hover {
  background: var(--platform-toolbar-bg);
}

.chat-history-item-icon {
  flex-shrink: 0;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  color: var(--platform-accent);
  background: var(--platform-accent-soft);
}

.chat-history-item-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.chat-history-item-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--platform-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-history-item-time {
  font-size: 12px;
  color: var(--platform-text-tertiary);
}
</style>
