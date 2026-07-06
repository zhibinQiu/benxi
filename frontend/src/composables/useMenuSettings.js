import { computed, ref } from "vue";
import { fetchVisibleMenus } from "../api/menuSettings.js";
import { registerMenuSettingsReset } from "../utils/resetClientSessionState.js";

const MENU_CACHE_KEY = "platform:visible-menus";
const MENU_CACHE_TTL = 300_000; // 5min

const visibleKeys = ref(null);
const loading = ref(false);
const loaded = ref(false);
let loadPromise = null;

/** 从 sessionStorage 还原菜单可见性（避免页面刷新后 beforeEach 阻塞） */
function _restoreCachedMenus() {
  try {
    const raw = sessionStorage.getItem(MENU_CACHE_KEY);
    if (!raw) return false;
    const { data, savedAt } = JSON.parse(raw);
    if (Date.now() - savedAt > MENU_CACHE_TTL) {
      sessionStorage.removeItem(MENU_CACHE_KEY);
      return false;
    }
    visibleKeys.value = new Set(data || []);
    loaded.value = true;
    return true;
  } catch {
    return false;
  }
}
_restoreCachedMenus();

/** 路由 name → 侧栏菜单 key（与后端 menu_settings_service.ROUTE_MENU_KEYS 对齐） */
export const ROUTE_MENU_KEYS = Object.freeze({
  "ai-home": "ai-home",
  "chat-history": "ai-home",
  "system-functions": "system-functions",
  translate: "system-functions",
  speech: "system-functions",
  "text-to-speech": "system-functions",
  ocr: "system-functions",
  compare: "system-functions",
  "report-generation": "system-functions",
  "ai-tools": "system-functions",
  "smart-data-query": "system-functions",
  "data-analysis": "system-functions",
  "carbon-qa": "system-functions",
  "smart-forecast": "system-functions",
  "kg-palantir": "system-functions",
  "knowledge-search": "system-functions",
  documents: "documents",
  "document-detail": "documents",
  "knowledge-subscriptions": "knowledge-subscriptions",
  "subscription-item": "knowledge-subscriptions",
  "admin-monitor": "admin-monitor",
  "admin-model-settings": "admin-model-settings",
  "agent-skills": "system-functions",
  "issue-reports": "issue-reports",
});

/** 管理员在「菜单管理」中可配置的侧栏项（不含权限控制的子页） */
export const CONFIGURABLE_MENU_KEYS = new Set([
  "ai-home",
  "system-functions",
  "documents",
  "knowledge-subscriptions",
  "issue-reports",
  "admin-monitor",
  "admin-model-settings",
]);

const MENU_FALLBACK_ORDER = Object.freeze([
  "ai-home",
  "system-functions",
  "documents",
  "knowledge-subscriptions",
  "issue-reports",
  "admin-monitor",
  "admin-model-settings",
]);

export function routeMenuKey(routeName) {
  if (!routeName) return null;
  return ROUTE_MENU_KEYS[String(routeName)] || null;
}

export function isConfigurableMenuKey(key) {
  return Boolean(key && CONFIGURABLE_MENU_KEYS.has(key));
}

export function useMenuSettings() {
  const visibleSet = computed(() => visibleKeys.value || new Set(MENU_FALLBACK_ORDER));

  async function loadMenuSettings(force = false) {
    if (loaded.value && !force) return visibleSet.value;
    if (loadPromise && !force) return loadPromise;

    loading.value = true;
    loadPromise = (async () => {
      try {
        const data = await fetchVisibleMenus();
        visibleKeys.value = new Set(data?.keys || MENU_FALLBACK_ORDER);
        loaded.value = true;
        try {
          sessionStorage.setItem(MENU_CACHE_KEY, JSON.stringify({ savedAt: Date.now(), data: data?.keys || MENU_FALLBACK_ORDER }));
        } catch { /* quota exceeded */ }
        return visibleSet.value;
      } catch {
        visibleKeys.value = new Set(MENU_FALLBACK_ORDER);
        loaded.value = true;
        return visibleSet.value;
      } finally {
        loading.value = false;
        loadPromise = null;
      }
    })();
    return loadPromise;
  }

  function isMenuVisible(key) {
    if (!key) return true;
    return visibleSet.value.has(key);
  }

  function firstVisibleRouteName() {
    for (const key of MENU_FALLBACK_ORDER) {
      if (visibleSet.value.has(key)) return key;
    }
    return "ai-home";
  }

  function resetMenuSettings() {
    visibleKeys.value = null;
    loaded.value = false;
    loadPromise = null;
  }

  return {
    visibleKeys,
    loading,
    loaded,
    visibleSet,
    loadMenuSettings,
    isMenuVisible,
    firstVisibleRouteName,
    resetMenuSettings,
  };
}

registerMenuSettingsReset(() => {
  visibleKeys.value = null;
  loaded.value = false;
  loadPromise = null;
});
