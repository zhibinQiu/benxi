import { computed, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";

const TABS_STORAGE_KEY = "platform:chat-tabs:ai-home";
const MAX_TABS = 7;
const MAX_TITLE_LEN = 15;
let tabCounter = 0;

function generateTabId() {
  tabCounter += 1;
  return `tab-${Date.now()}-${tabCounter}`;
}

function generateSessionKey(tabId) {
  if (tabId === "tab-0") return "ai-home";
  return `ai-home:tab:${tabId}`;
}

function loadPersistedTabs() {
  try {
    const raw = sessionStorage.getItem(TABS_STORAGE_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    if (!Array.isArray(data)) return null;
    return data.map((t, i) => ({
      id: t.id || `tab-${i}`,
      title: typeof t.title === "string" ? t.title : "",
      sessionKey: t.sessionKey || generateSessionKey(t.id || `tab-${i}`),
    }));
  } catch {
    return null;
  }
}

function saveTabsToStorage(tabs) {
  try {
    sessionStorage.setItem(
      TABS_STORAGE_KEY,
      JSON.stringify(
        tabs.map((t) => ({
          id: t.id,
          title: t.title,
          sessionKey: t.sessionKey,
        }))
      )
    );
  } catch {
    /* quota exceeded */
  }
}

/**
 * 管理「本析智能」最多 7 个并发对话标签页。
 *
 * 每个标签页对应独立路由：
 * - tab-0  → /ai-home
 * - 其他   → /ai-home/tab/:tabId
 *
 * 切换/创建/关闭标签均通过 router.push 导航，MainLayout 的 KeepAlive
 * 以不同 key 保留后台标签页实例。
 *
 * tabStreaming / tabHasContent 由 AiHomeView 在 onChatStateChange 回调中驱动。
 *
 * ⚠️ 使用模块级单例状态，确保 MainLayout 与 AiHomeView 共享同一份 state。
 */

/* --- 模块级单例状态 --- */
const persisted = loadPersistedTabs();

const tabs = ref(
  persisted && persisted.length > 0
    ? persisted
    : [
        {
          id: "tab-0",
          title: "",
          sessionKey: "ai-home",
        },
      ]
);

const activeTabId = ref(tabs.value[0]?.id || "tab-0");

/** 各标签是否正在流式响应 */
const tabStreaming = reactive({});
/** 各标签是否已有对话内容 */
const tabHasContent = reactive({});

watch(
  tabs,
  (list) => {
    saveTabsToStorage(list);
  },
  { deep: true }
);

export function resetChatTabs() {
  /* 登录/退出时重置为单个新对话标签 */
  tabs.value = [
    {
      id: "tab-0",
      title: "",
      sessionKey: "ai-home",
    },
  ];
  activeTabId.value = "tab-0";
  Object.keys(tabStreaming).forEach((k) => delete tabStreaming[k]);
  Object.keys(tabHasContent).forEach((k) => delete tabHasContent[k]);
  saveTabsToStorage(tabs.value);
}

export function useChatTabs() {
  const router = useRouter();

  const activeTab = computed(() =>
    tabs.value.find((t) => t.id === activeTabId.value)
  );

  const tabCount = computed(() => tabs.value.length);

  const canCreateTab = computed(() => tabs.value.length < MAX_TABS);

  function navigateToTab(id) {
    if (id === "tab-0") {
      router.push({ name: "ai-home" });
    } else {
      router.push({ name: "ai-home-tab", params: { tabId: id } });
    }
  }

  function createTab() {
    if (!canCreateTab.value) return null;
    const id = generateTabId();
    const tab = {
      id,
      title: "",
      sessionKey: generateSessionKey(id),
    };
    tabs.value = [...tabs.value, tab];
    activeTabId.value = id;
    navigateToTab(id);
    return tab;
  }

  function closeTab(id) {
    if (tabs.value.length <= 1) return null;
    const idx = tabs.value.findIndex((t) => t.id === id);
    if (idx < 0) return null;
    clearTabSession(id);
    delete tabStreaming[id];
    delete tabHasContent[id];
    const newList = tabs.value.filter((t) => t.id !== id);
    tabs.value = newList;
    const newIdx = Math.min(idx, newList.length - 1);
    const nextId = newList[newIdx]?.id || newList[0]?.id || "";
    activeTabId.value = nextId;
    navigateToTab(nextId);
    return nextId;
  }

  function switchTab(id) {
    const exists = tabs.value.some((t) => t.id === id);
    if (exists) {
      activeTabId.value = id;
      navigateToTab(id);
    }
  }

  function updateTabTitle(id, title) {
    tabs.value = tabs.value.map((t) =>
      t.id === id
        ? { ...t, title: String(title || "").slice(0, MAX_TITLE_LEN) }
        : t
    );
  }

  function syncActiveTabFromRoute(tabId) {
    if (tabId && tabs.value.some((t) => t.id === tabId)) {
      activeTabId.value = tabId;
    } else if (tabId) {
      tabs.value = [
        ...tabs.value,
        {
          id: tabId,
          title: "",
          sessionKey: generateSessionKey(tabId),
        },
      ];
      activeTabId.value = tabId;
    } else {
      activeTabId.value = "tab-0";
    }
  }

  function getSessionKey(id) {
    const tab = tabs.value.find((t) => t.id === id);
    return tab?.sessionKey || "ai-home";
  }

  function clearTabSession(id) {
    const tab = tabs.value.find((t) => t.id === id);
    if (tab) {
      try {
        sessionStorage.removeItem(`platform:chat-session:${tab.sessionKey}`);
      } catch {
        /* ignore */
      }
    }
  }

  function setTabStreaming(id, val) {
    tabStreaming[id] = val;
  }

  function setTabHasContent(id, val) {
    tabHasContent[id] = val;
  }

  /** 一键关闭所有标签，重置为单个新对话 */
  function closeAllTabs() {
    resetChatTabs();
  }

  return {
    tabs,
    activeTabId,
    activeTab,
    tabCount,
    canCreateTab,
    tabStreaming,
    tabHasContent,
    createTab,
    closeTab,
    closeAllTabs,
    switchTab,
    updateTabTitle,
    syncActiveTabFromRoute,
    getSessionKey,
    setTabStreaming,
    setTabHasContent,
  };
}
