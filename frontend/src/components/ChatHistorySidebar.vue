<script setup>
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";
import {
  NEmpty,
  NIcon,
  NInput,
  NSpin,
} from "naive-ui";
import { ChatbubblesOutline, SearchOutline } from "@vicons/ionicons5";
import {
  fetchChatConversations,
} from "../api/client";
import { CHAT_SCOPES } from "../constants/chatScopes";
import { useChatTabs } from "../composables/useChatTabs.js";
import { useI18n } from "../composables/useI18n.js";
import { usePlatformUi } from "../composables/usePlatformUi";
import { loadChatSession } from "../utils/chatSessionPersist.js";

const props = defineProps({
  show: { type: Boolean, default: false },
  scope: { type: String, default: "ai-home" },
});

const emit = defineEmits(["update:show", "navigate"]);

const router = useRouter();
const ui = usePlatformUi();
const { t, locale } = useI18n();
const { tabs, tabHasContent, switchTab } = useChatTabs();

const loading = ref(false);
const items = ref([]);
const searchQuery = ref("");

const dateLocale = computed(() => (locale.value === "zh" ? "zh-CN" : "en-US"));

const filteredItems = computed(() => {
  const q = searchQuery.value.trim().toLowerCase();
  if (!q) return items.value;
  return items.value.filter((item) => (item.title || "").toLowerCase().includes(q));
});

function titleFromSession(session, fallback = "") {
  const fromTab = String(fallback || "").trim();
  if (fromTab) return fromTab;
  const rows = Array.isArray(session?.messages) ? session.messages : [];
  const userMsg = rows.find((m) => m.role === "user" && String(m.content || "").trim());
  const text = String(userMsg?.content || "")
    .trim()
    .replace(/\s+/g, " ");
  if (!text) return "";
  return text.length <= 48 ? text : `${text.slice(0, 47)}…`;
}

/** 当前标签页中的对话（含尚未同步到服务端的） */
function collectOpenTabItems() {
  if (props.scope !== "ai-home") return [];
  const result = [];
  for (const tab of tabs.value) {
    const session = loadChatSession(tab.sessionKey);
    const hasMessages = Array.isArray(session?.messages) && session.messages.length > 0;
    const hasContent = Boolean(tabHasContent[tab.id] || hasMessages || session?.conversationId || tab.title);
    if (!hasContent) continue;
    const conversationId = session?.conversationId || null;
    const title =
      titleFromSession(session, tab.title) || t("chatHistory.unnamedConversation");
    result.push({
      id: conversationId || `tab:${tab.id}`,
      tabId: tab.id,
      title,
      updated_at: session?.savedAt
        ? new Date(session.savedAt).toISOString()
        : null,
      isOpenTab: true,
    });
  }
  return result;
}

function mergeHistoryItems(serverItems, openItems) {
  const byKey = new Map();
  const tabByConv = new Map();

  for (const open of openItems) {
    if (open.id && !String(open.id).startsWith("tab:")) {
      tabByConv.set(open.id, open);
    }
    byKey.set(open.id, open);
  }

  for (const server of serverItems || []) {
    const open = tabByConv.get(server.id);
    if (open) {
      byKey.set(server.id, {
        ...server,
        title: open.title || server.title,
        tabId: open.tabId,
        isOpenTab: true,
      });
      continue;
    }
    if (!byKey.has(server.id)) {
      byKey.set(server.id, server);
    }
  }

  return Array.from(byKey.values()).sort((a, b) => {
    const ta = a.updated_at ? Date.parse(a.updated_at) : 0;
    const tb = b.updated_at ? Date.parse(b.updated_at) : 0;
    return tb - ta;
  });
}

async function loadList() {
  if (!CHAT_SCOPES[props.scope]) {
    ui.error(t("chatHistory.unsupportedScope"));
    return;
  }
  loading.value = true;
  try {
    const serverItems = (await fetchChatConversations(props.scope)) || [];
    items.value = mergeHistoryItems(serverItems, collectOpenTabItems());
  } catch (e) {
    ui.error(e.message || t("chatHistory.loadFailed"));
    items.value = mergeHistoryItems([], collectOpenTabItems());
  } finally {
    loading.value = false;
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
    return d.toLocaleTimeString(dateLocale.value, { hour: "2-digit", minute: "2-digit" });
  }
  return d.toLocaleString(dateLocale.value, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function openConversation(item) {
  const meta = CHAT_SCOPES[props.scope];
  if (!meta?.routeName || !item?.id) return;
  emit("update:show", false);
  emit("navigate");

  // 已打开的标签页直接切换，避免再开一份
  if (item.tabId) {
    switchTab(item.tabId);
    return;
  }

  router.push({
    name: meta.routeName,
    query: { conversationId: item.id },
  });
}

// 父级用 v-if 挂载本组件时 show 已是 true，须 immediate，否则 loadList 永不执行
watch(
  () => props.show,
  (open) => {
    if (open) loadList();
  },
  { immediate: true }
);
</script>

<template>
  <div class="chat-history-sidebar">
    <header class="chat-history-sidebar__header">
      <strong class="chat-history-sidebar__title">{{ t("chatHistory.title") }}</strong>
    </header>

    <div class="chat-history-sidebar__search">
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

    <n-spin :show="loading" class="chat-history-sidebar__body">
      <div v-if="!loading && !filteredItems.length" class="chat-history-sidebar__empty">
        <n-empty
          :description="searchQuery.trim() ? t('chatHistory.noSearchResults') : t('chatHistory.empty')"
        />
      </div>
      <ul v-else class="chat-history-sidebar__list">
        <li v-for="item in filteredItems" :key="item.id">
          <button type="button" class="chat-history-sidebar__item" @click="openConversation(item)">
            <span class="chat-history-sidebar__item-icon" aria-hidden="true">
              <n-icon :size="18" :component="ChatbubblesOutline" />
            </span>
            <span class="chat-history-sidebar__item-body">
              <span class="chat-history-sidebar__item-title">
                {{ item.title || t("chatHistory.unnamedConversation") }}
              </span>
              <span class="chat-history-sidebar__item-time">{{ formatTime(item.updated_at) }}</span>
            </span>
          </button>
        </li>
      </ul>
    </n-spin>
  </div>
</template>

<style scoped>
.chat-history-sidebar {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--platform-card-bg, #fff);
}

.chat-history-sidebar__header {
  flex-shrink: 0;
  padding: 16px 16px 10px;
}

.chat-history-sidebar__title {
  font-size: 15px;
  font-weight: 600;
  color: var(--platform-text);
}

.chat-history-sidebar__search {
  flex-shrink: 0;
  padding: 0 16px 12px;
}

.chat-history-sidebar__body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.chat-history-sidebar__body :deep(.n-spin-container),
.chat-history-sidebar__body :deep(.n-spin-content) {
  height: 100%;
}

.chat-history-sidebar__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 24px;
}

.chat-history-sidebar__list {
  list-style: none;
  margin: 0;
  padding: 0 8px 16px;
  height: 100%;
  overflow-y: auto;
}

.chat-history-sidebar__item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  width: 100%;
  padding: 10px 8px;
  border: none;
  border-radius: 0;
  background: transparent;
  text-align: left;
  cursor: pointer;
  border-bottom: 1px solid var(--platform-border-light, #E8E8E8);
}

.chat-history-sidebar__item:hover {
  background: color-mix(in srgb, var(--platform-accent) 6%, transparent);
}

.chat-history-sidebar__item-icon {
  flex-shrink: 0;
  margin-top: 2px;
  color: var(--platform-accent, #005A9E);
}

.chat-history-sidebar__item-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.chat-history-sidebar__item-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--platform-text);
  line-height: 1.35;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
}

.chat-history-sidebar__item-time {
  font-size: 11px;
  color: var(--platform-text-tertiary);
}
</style>
