import { computed, ref } from "vue";
import { fetchVisibleMenus } from "../api/menuSettings.js";
import { registerMenuSettingsReset } from "../utils/resetClientSessionState.js";

const visibleKeys = ref(null);
const loading = ref(false);
const loaded = ref(false);
let loadPromise = null;

/** 路由 name → 侧栏菜单 key（与后端 menu_settings_service.ROUTE_MENU_KEYS 对齐） */
export const ROUTE_MENU_KEYS = {
  "ai-home": "ai-home",
  "chat-history": "ai-home",
  "system-functions": "system-functions",
  translate: "system-functions",
  speech: "system-functions",
  ocr: "system-functions",
  compare: "system-functions",
  "assist-writing": "system-functions",
  "report-generation": "system-functions",
  "ai-tools": "system-functions",
  "smart-data-query": "system-functions",
  "data-analysis": "system-functions",
  "carbon-qa": "system-functions",
  "carbon-assets": "system-functions",
  "carbon-assets-history": "system-functions",
  "smart-forecast": "system-functions",
  "kg-palantir": "system-functions",
  "knowledge-search": "system-functions",
  documents: "documents",
  "document-detail": "documents",
  "knowledge-subscriptions": "knowledge-subscriptions",
  "subscription-item": "knowledge-subscriptions",
  "wechat-mp": "knowledge-subscriptions",
  "wechat-mp-article": "knowledge-subscriptions",
  "feed-subscriptions": "knowledge-subscriptions",
  "feed-entry": "knowledge-subscriptions",
  "admin-monitor": "admin-monitor",
  "admin-model-settings": "admin-model-settings",
  "admin-docs": "admin-docs",
};

const MENU_FALLBACK_ORDER = [
  "ai-home",
  "system-functions",
  "documents",
  "knowledge-subscriptions",
  "admin-monitor",
  "admin-model-settings",
  "admin-docs",
];

export function routeMenuKey(routeName) {
  if (!routeName) return null;
  return ROUTE_MENU_KEYS[String(routeName)] || null;
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
    if (!loaded.value || !visibleKeys.value) return true;
    return visibleKeys.value.has(key);
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
