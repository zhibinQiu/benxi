import { computed, ref } from "vue";
import { fetchVisibleMenus } from "../api/menuSettings.js";
import { registerMenuSettingsReset } from "../utils/resetClientSessionState.js";

const MENU_CACHE_KEY = "platform:visible-menus";
const MENU_CACHE_TTL = 300_000; // 5min

const visibleKeys = ref(null);
const loading = ref(false);
const loaded = ref(false);
let loadPromise = null;

/** 废弃 sessionStorage 冷启动缓存，始终从服务端拉取最新数据。
 *
 * 旧缓存可能包含过时的菜单键（如缺少新添加的 ontology/kg），
 * 导致 visibleKeys 被设为一个真值 Set，永远不会走 MENU_FALLBACK_ORDER 降级路径，
 * 路由守卫因此拦截并重定向到 ai-home。
 *
 * 初始阶段 visibleKeys=null → visibleSet 使用 MENU_FALLBACK_ORDER，
 * 该降级列表始终包含最新功能菜单键，保证新功能不会被拦截。 */
function _restoreCachedMenus() {
  try {
    sessionStorage.removeItem(MENU_CACHE_KEY);
  } catch { /* 安全忽略 */ }
  return false;
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
  "knowledge-search": "system-functions",
  ontology: "ontology",
  kg: "kg",
  documents: "documents",
  "document-detail": "documents",
  "knowledge-subscriptions": "knowledge-subscriptions",
  "subscription-item": "knowledge-subscriptions",
  "admin-monitor": "admin-monitor",
  "admin-model-settings": "admin-model-settings",
  "menu-settings": "admin-menu-settings",
  "admin-menu-settings": "admin-menu-settings",
  "issue-reports": "issue-reports",
  "agent-skills": "agent-skills",
});

/** 管理员在「菜单管理」中可配置的侧栏项（不含权限控制的子页） */
export const CONFIGURABLE_MENU_KEYS = new Set([
  "ai-home",
  "system-functions",
  "ontology",
  "kg",
  "documents",
  "knowledge-subscriptions",
  "issue-reports",
  "agent-skills",
  "admin-monitor",
  "admin-model-settings",
  "admin-menu-settings",
]);

const MENU_FALLBACK_ORDER = Object.freeze([
  "ai-home",
  "system-functions",
  "agent-skills",
  "ontology",
  "kg",
  "documents",
  "knowledge-subscriptions",
  "issue-reports",
  "admin-menu-settings",
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
