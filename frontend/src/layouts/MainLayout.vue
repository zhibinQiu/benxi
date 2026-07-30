<script setup>
import { computed, h, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  NLayout,
  NLayoutHeader,
  NLayoutSider,
  NLayoutContent,
  NMenu,
  NButton,
  NIcon,
  NSpace,
} from "naive-ui";
import {
  DocumentTextOutline,
  PeopleOutline,
  BusinessOutline,
  GridOutline,
  SettingsOutline,
  PulseOutline,
  HardwareChipOutline,
  SparklesOutline,
  ArrowBackOutline,
  BugOutline,
  ListOutline,
  GitNetworkOutline,
  ExtensionPuzzleOutline,
  TimerOutline,
} from "@vicons/ionicons5";
import { useAuth } from "../composables/useAuth";
import { useI18n } from "../composables/useI18n";
import { useSystemFeatures } from "../composables/useSystemFeatures";
import { useMenuSettings } from "../composables/useMenuSettings";
import { getPageHeaderOverride } from "../composables/usePageHeader";
import { resolveFeatureIcon } from "../constants/featureIcons";
import { useAppDisplayName } from "../composables/usePlatformBranding";
import {
  SIDEBAR_DEDICATED_FEATURE_IDS,
  useFeatureFavorites,
} from "../composables/useFeatureFavorites";
import HeaderToolbar from "../components/layout/HeaderToolbar.vue";
import PlatformBrandTitle from "../components/PlatformBrandTitle.vue";
import PlatformBrandIcon from "../components/PlatformBrandIcon.vue";
import SystemNotificationToast from "../components/SystemNotificationToast.vue";
import { startNotificationAlerts, stopNotificationAlerts } from "../composables/useNotificationAlerts.js";
import { SUBSYSTEM_PAGE_ROUTES } from "../utils/routeTransition";
import { useSiderMenuIndicator } from "../composables/useSiderMenuIndicator";
import { goBackToEntry } from "../utils/navigationReturn";
import { isBenignNavigationError } from "../api/requestScope.js";
import { sessionEpoch } from "../utils/sessionEpoch.js";
import ReleaseHighlightsModal from "../components/ReleaseHighlightsModal.vue";
import { fetchReleaseHighlights } from "../api/system.js";
import {
  acknowledgeReleaseVersion,
  shouldShowReleaseHighlights,
} from "../utils/releaseNotesAck.js";
import { useBlockingUiCleanup } from "../composables/useBlockingUiCleanup.js";
import { prefetchKnowledgeScopeTree } from "../composables/useKnowledgeScopeTree.js";
import { getToken } from "../api/client.js";
import { openExternal } from "../utils/openExternal.js";
import { publicAsset } from "../utils/appBase.js";
import ChatTabBar from "../components/ChatTabBar.vue";
import ChatHistorySidebar from "../components/ChatHistorySidebar.vue";
import { useChatTabs } from "../composables/useChatTabs.js";

/** 侧栏底部装饰：海颐 logo；双碳线条图标为内联 SVG 背景 */
const haiyiLogoSrc = publicAsset("images/haiyi-logo.png");

/** 对话 / 知识检索 / 报告生成 / 文档管理 / 多智能体保留实例；其余功能离开路由后销毁以释放内存 */
const KEEP_ALIVE_VIEWS = [
  "AiHomeView",
  "KnowledgeFeatureLayout",
  "DocumentsView",
  "AgentSkillsView",
  "OntologyView",
  "AutomationView",
];

function routeViewKey(viewRoute) {
  const name = String(viewRoute.name || "");
  if (name === "knowledge-search" || name === "report-generation") {
    return `${sessionEpoch.value}:knowledge-feature`;
  }
  // ai-home 多标签页：每个标签页独立 KeepAlive 实例
  if (name === "ai-home" || name === "ai-home-tab") {
    const tabId = viewRoute.params?.tabId || "";
    return `${sessionEpoch.value}:ai-home${tabId ? `:${tabId}` : ""}`;
  }
  const base = viewRoute.meta?.keepAlive
    ? name || viewRoute.path
    : viewRoute.path;
  return `${sessionEpoch.value}:${base}`;
}

const route = useRoute();
const router = useRouter();
useBlockingUiCleanup();
const { loadUser, hasPerm } = useAuth();
const { t, routeTitle, featureLabel, featureDescription } = useI18n();
const { loadMenuSettings, isMenuVisible } = useMenuSettings();
const pageHeaderOverride = getPageHeaderOverride();
const headerToolbarRef = ref(null);
const releaseHighlightsOpen = ref(false);
const releaseHighlights = ref(null);
const chatHistoryDrawerOpen = ref(false);

const SETTINGS_KEY = "system-settings";
const expandedKeys = ref([]);
const siderMenuWrapRef = ref(null);

const siderCollapsed = ref(false);
const isMobile = ref(window.innerWidth < 768);

function toggleChatHistoryDrawer() {
  headerToolbarRef.value?.closeAllFlyouts?.();
  chatHistoryDrawerOpen.value = !chatHistoryDrawerOpen.value;
}

function checkMobile() {
  isMobile.value = window.innerWidth < 768;
}
let resizeTimer = null;
function onResize() {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(checkMobile, 100);
}

function toggleSider() {
  siderCollapsed.value = !siderCollapsed.value;
}


const { features: systemFeatures, loadSystemFeatures } = useSystemFeatures();
const { favoriteIds } = useFeatureFavorites();

function favoriteMenuKey(feature) {
  if (feature.external_url) return `feature-ext:${feature.id}`;
  return `feature-fav:${feature.id}`;
}

const favoriteMenuFeatures = computed(() => {
  const byId = Object.fromEntries(systemFeatures.value.map((f) => [f.id, f]));
  const dedicated = new Set(SIDEBAR_DEDICATED_FEATURE_IDS);
  return favoriteIds.value
    .map((id) => byId[id])
    .filter((f) => f && f.enabled && f.accessible && !dedicated.has(f.id));
});

const favoriteActiveKey = computed(() => {
  const path = route.path;
  for (const id of favoriteIds.value) {
    const feature = systemFeatures.value.find((f) => f.id === id);
    if (!feature?.route) continue;
    if (path === feature.route || path.startsWith(`${feature.route}/`)) {
      return favoriteMenuKey(feature);
    }
  }
  return null;
});

const KNOWLEDGE_ROUTES = new Set([]);

/** 标题在顶栏 primary 区域的路由（知识检索/报告生成已改为内容区标题，不在此列） */
const showTitleInPrimary = computed(() => KNOWLEDGE_ROUTES.has(String(route.name || "")));

/** 隐藏顶栏 header-primary 行（仅本析智能用标签栏替代顶栏） */
const HEADERLESS_PRIMARY_ROUTES = new Set(["ai-home", "ai-home-tab"]);
const showHeaderPrimary = computed(() => !HEADERLESS_PRIMARY_ROUTES.has(String(route.name || "")));

const EXCLUDED_BACK_ROUTES = new Set(["knowledge-search", "report-generation", "agent-skills", "knowledge-subscriptions"]);

let knowledgeScopePrefetchScheduled = false;

function scheduleKnowledgeScopePrefetch() {
  if (!getToken() || knowledgeScopePrefetchScheduled) return;
  knowledgeScopePrefetchScheduled = true;
  const run = () => {
    knowledgeScopePrefetchScheduled = false;
    if (getToken()) prefetchKnowledgeScopeTree();
  };
  if (typeof window.requestIdleCallback === "function") {
    requestIdleCallback(run, { timeout: 2500 });
  } else {
    setTimeout(run, 400);
  }
}

onMounted(() => {
  startNotificationAlerts();
  scheduleKnowledgeScopePrefetch();
  checkMobile();
  window.addEventListener("resize", onResize);
  Promise.allSettled([loadUser(), loadSystemFeatures(), loadMenuSettings()]).then(() => {
    scheduleKnowledgeScopePrefetch();
    nextTick(() => {
      const wrap = siderMenuWrapRef.value;
      const selected = wrap?.querySelector(".n-menu-item-content.n-menu-item-content--selected");
      if (selected) moveIndicatorToContent(selected);
    });
    void tryShowReleaseHighlights();
  });
});

onUnmounted(() => {
  stopNotificationAlerts();
  window.removeEventListener("resize", onResize);
});

watch(
  () => route.name,
  (name) => {
    if (!getToken()) return;
    const routeName = String(name || "");
    if (routeName === "knowledge-search" || routeName === "report-generation") {
      scheduleKnowledgeScopePrefetch();
    }
  }
);

async function tryShowReleaseHighlights() {
  try {
    const data = await fetchReleaseHighlights();
    if (!data?.version) return;
    const hasItems = (data.features?.length || 0) + (data.fixes?.length || 0) > 0;
    if (!hasItems || !shouldShowReleaseHighlights(data.version)) return;
    releaseHighlights.value = data;
    releaseHighlightsOpen.value = true;
  } catch {
    /* 非关键路径：忽略网络或权限错误 */
  }
}

function onReleaseHighlightsAcknowledge() {
  const version = releaseHighlights.value?.version;
  if (version) acknowledgeReleaseVersion(version);
  releaseHighlightsOpen.value = false;
}

const showUserAdmin = computed(() => hasPerm("admin.user"));
const showDeptAdmin = computed(() => hasPerm("admin.dept"));

const settingsChildren = computed(() => {
  const children = [];
  if (showUserAdmin.value) {
    children.push(
      {
        label: t("menu.users"),
        key: "admin-users",
        icon: () => h(NIcon, null, { default: () => h(PeopleOutline) })},
      {
        label: t("menu.menuSettings"),
        key: "admin-menu-settings",
        icon: () => h(NIcon, null, { default: () => h(ListOutline) })}
    );
    if (isMenuVisible("admin-model-settings")) {
      children.push({
        label: t("menu.modelSettings"),
        key: "admin-model-settings",
        icon: () => h(NIcon, null, { default: () => h(HardwareChipOutline) })});
    }
  }
  if (showDeptAdmin.value) {
    children.push({
      label: t("menu.departments"),
      key: "admin-departments",
      icon: () => h(NIcon, null, { default: () => h(BusinessOutline) })});
  }
  const memberSettingsMenus = [
    {
      label: t("menu.issueReports"),
      key: "issue-reports",
      icon: () => h(NIcon, null, { default: () => h(BugOutline) })},
    {
      label: t("menu.monitor"),
      key: "admin-monitor",
      icon: () => h(NIcon, null, { default: () => h(PulseOutline) })},
  ];
  for (const item of memberSettingsMenus) {
    if (isMenuVisible(item.key)) {
      children.push(item);
    }
  }
  return children;
});

const menuOptions = computed(() => {
  const items = [];

  if (isMenuVisible("ai-home")) {
    items.push({
      label: t("menu.aiHome"),
      key: "ai-home",
      icon: () => h(NIcon, null, { default: () => h(SparklesOutline) })});
  }
  if (isMenuVisible("system-functions")) {
    items.push({
      label: t("menu.systemFunctions"),
      key: "system-functions",
      icon: () => h(NIcon, null, { default: () => h(GridOutline) })});
  }

  if (isMenuVisible("agent-skills")) {
    items.push({
      label: t("menu.agentSkills"),
      key: "agent-skills",
      icon: () => h(NIcon, null, { default: () => h(ExtensionPuzzleOutline) })});
  }

  if (isMenuVisible("automation")) {
    items.push({
      label: t("menu.automation"),
      key: "automation",
      icon: () => h(NIcon, null, { default: () => h(TimerOutline) })});
  }

  if (isMenuVisible("documents")) {
    items.push({
      label: t("menu.documents"),
      key: "documents",
      icon: () => h(NIcon, null, { default: () => h(DocumentTextOutline) })});
  }

  for (const feature of favoriteMenuFeatures.value) {
    const Icon = resolveFeatureIcon(feature.icon) || GridOutline;
    items.push({
      label: featureLabel(feature.id, "title", feature.title),
      key: favoriteMenuKey(feature),
      icon: () => h(NIcon, null, { default: () => h(Icon) })});
  }

  // 本体定义（含模式层 + 实例图谱）
  if (hasPerm("feature.ontology") && isMenuVisible("ontology")) {
    items.push({
      label: t("menu.ontology"),
      key: "ontology",
      icon: () => h(NIcon, null, { default: () => h(GitNetworkOutline) })});
  }

  if (settingsChildren.value.length) {
    items.push({
      label: t("menu.systemSettings"),
      key: SETTINGS_KEY,
      icon: () => h(NIcon, null, { default: () => h(SettingsOutline) }),
      children: settingsChildren.value});
  }
  return items;
});

/** 从系统功能进入的子功能页（翻译、问数、问答等） */
const SUBSYSTEM_HEADER_ROUTES = SUBSYSTEM_PAGE_ROUTES;

const isSubsystemPage = computed(() =>
  SUBSYSTEM_HEADER_ROUTES.has(String(route.name || ""))
);

const activeKey = computed(() => {
  if (route.name === "document-detail") return "documents";
  if (favoriteActiveKey.value) return favoriteActiveKey.value;
  if (
    route.name === "ai-home" ||
    route.name === "ai-home-tab"
  ) {
    return "ai-home";
  }
  if (
    route.name === "translate" ||
    route.name === "speech" ||
    route.name === "text-to-speech" ||
    route.name === "ocr" ||
    route.name === "compare" ||
    route.name === "knowledge-search" ||
    route.name === "report-generation" ||
    route.name === "knowledge-subscriptions" ||
    route.name === "subscription-item" ||
    route.name === "ai-tools" ||
    route.name === "smart-data-query" ||
    route.name === "data-analysis" ||
    route.name === "carbon-qa" ||
    route.name === "carbon-news" ||
    route.name === "carbon-assistant" ||
    route.name === "finance-assistant" ||
    route.name === "notes" ||
    route.name === "smart-forecast"
  ) {
    return "system-functions";
  }
  if (
    route.name === "admin-users" ||
    route.name === "admin-departments" ||
    route.name === "agent-skills" ||
    route.name === "automation" ||
    route.name === "admin-monitor" ||
    route.name === "admin-model-settings" ||
    route.name === "admin-menu-settings" ||
    route.name === "issue-reports"
  ) {
    return String(route.name);
  }
  return String(route.name || "ai-home");
});

const fullHeightPage = computed(() => Boolean(route.meta?.fullHeight));

const flushFeatureNav = computed(
  () => fullHeightPage.value || Boolean(route.meta?.featureLocalNav)
);

/** 子功能页 Teleport 操作条：预留顶栏高度，避免注入后挤压正文 */
const reservesHeaderExtension = computed(() => {
  const name = String(route.name || "");
  // ai-home 用标签栏替代顶栏
  if (name === "ai-home" || name === "ai-home-tab") return flushFeatureNav.value;
  // 其余页面有标题行 + 操作栏，始终预留空间
  return true;
});

const headerTitle = computed(() => {
  if (pageHeaderOverride.value) return pageHeaderOverride.value;
  return routeTitle(String(route.name || ""), String(route.meta?.title || "").trim());
});

const headerDescription = computed(() => featureDescription(String(route.name || "")));

const appDisplayName = useAppDisplayName();
const sidebarBrandTitle = useAppDisplayName();

const menuOptionKeys = computed(() => {
  const keys = new Set();
  function walk(items) {
    for (const item of items || []) {
      if (item?.key) keys.add(String(item.key));
      if (item?.children?.length) walk(item.children);
    }
  }
  walk(menuOptions.value);
  return keys;
});

const resolvedActiveKey = computed(() => {
  const key = String(activeKey.value || "");
  if (menuOptionKeys.value.has(key)) return key;
  if (key.startsWith("feature-fav:") || key.startsWith("feature-ext:")) {
    return "system-functions";
  }
  return key || "ai-home";
});

const { indicatorStyle: menuIndicatorStyle, moveIndicatorToContent } = useSiderMenuIndicator(siderMenuWrapRef, {
  activeKey: resolvedActiveKey,
  collapsed: siderCollapsed,
  expandedKeys});

const showSubsystemBack = computed(
  () => isSubsystemPage.value && Boolean(headerTitle.value) && !EXCLUDED_BACK_ROUTES.has(String(route.name || ""))
);

/** ai-home 多标签页管理器 */
const {
  tabs: chatTabs,
  activeTabId: chatActiveTabId,
  canCreateTab: chatCanCreateTab,
  tabCount: chatTabCount,
  tabStreaming,
  tabHasContent,
  createTab: createChatTab,
  closeTab: closeChatTab,
  closeAllTabs,
  switchTab: switchChatTab,
  syncActiveTabFromRoute,
  updateTabTitle,
} = useChatTabs();

/** 仅在 ai-home 相关路由显示标签栏 */
const showAiHomeTabBar = computed(() =>
  route.name === "ai-home" || route.name === "ai-home-tab"
);

watch(showAiHomeTabBar, (show) => {
  if (!show) chatHistoryDrawerOpen.value = false;
});

function goSubsystemBack() {
  goBackToEntry(router, route);
}

const contentStyle = computed(() => {
  if (route.meta?.fullEmbed) {
    return "padding: 0; height: 100vh; overflow: hidden";
  }
  if (fullHeightPage.value) {
    return "flex: 1; min-height: 0; overflow: hidden; box-sizing: border-box";
  }
  if (route.name === "system-functions") {
    return "padding: 14px 24px";
  }
  if (flushFeatureNav.value) {
    return "padding: 0 24px 14px";
  }
  return "padding: 14px 24px";
});

/** 移动端底部导航栏：核心入口（资讯等子功能经功能列表收藏后出现在侧栏） */
const mobileBottomTabs = computed(() => [
  {
    key: "ai-home",
    label: t("menu.aiHome"),
    icon: SparklesOutline,
    routeName: "ai-home",
  },
  {
    key: "documents",
    label: t("menu.documents"),
    icon: DocumentTextOutline,
    routeName: "documents",
  },
  {
    key: "system-functions",
    label: t("menu.systemFunctions"),
    icon: GridOutline,
    routeName: "system-functions",
  },
]);

const mobileTabActiveKey = computed(() => {
  const name = String(route.name || "");
  if (name === "ai-home" || name === "ai-home-tab") return "ai-home";
  if (name === "documents" || name === "document-detail") return "documents";
  if (
    name === "system-functions" ||
    name === "knowledge-subscriptions" ||
    name === "subscription-item"
  ) {
    return "system-functions";
  }
  return "ai-home";
});

function onMobileTabSelect(key) {
  const tab = mobileBottomTabs.value.find((t) => t.key === key);
  if (!tab) return;
  if (key === String(route.name || "")) return;
  pushRoute(tab.routeName);
}

function onExpandedKeysUpdate(keys) {
  expandedKeys.value = keys;
}

watch(
  () => route.name,
  (name) => {
    headerToolbarRef.value?.closeAllFlyouts?.({ releasePanels: true });
    if (name && name !== "login") {
      headerToolbarRef.value?.refreshHeaderBadges?.();
    }
  },
);

/* ai-home 多标签页：路由变化时同步活跃标签状态 */
watch(
  () => [route.name, route.params?.tabId],
  ([name, tabId]) => {
    if (name === "ai-home" || name === "ai-home-tab") {
      syncActiveTabFromRoute(String(tabId || "tab-0"));
    }
  },
  { immediate: true },
);

function siderMenuNodeProps(node) {
  const key = node?.key;
  if (key == null || key === "") return {};
  return { "data-menu-key": String(key) };
}

function pushRoute(target) {
  const p = typeof target === "string" ? router.push({ name: target }) : router.push(target);
  if (p && typeof p.catch === "function") {
    p.catch((err) => {
      if (!isBenignNavigationError(err)) {
        console.warn("[router]", err);
      }
    });
  }
}

function resolveMenuKeyFromEvent(e) {
  const item = e.target?.closest?.("[data-menu-key]");
  const key = item?.getAttribute("data-menu-key");
  return key || null;
}

function onSiderMenuWrapClick(e) {
  const content = e.target?.closest?.(".n-menu-item-content");
  if (!content || content.classList.contains("n-menu-item-content--disabled")) return;
  moveIndicatorToContent(content);

  const key = resolveMenuKeyFromEvent(e);
  if (!key || key === SETTINGS_KEY) return;

  if (key === resolvedActiveKey.value) {
    if (isSubsystemPage.value && key === "system-functions") {
      pushRoute("system-functions");
    } else if (route.name === "document-detail" && key === "documents") {
      pushRoute("documents");
    }
    return;
  }

  onMenuSelect(key);
}

function onMenuSelect(key) {
  if (key === SETTINGS_KEY) return;
  headerToolbarRef.value?.closeAllFlyouts?.();

  if (key.startsWith("feature-ext:")) {
    const featureId = key.slice("feature-ext:".length);
    const feature = systemFeatures.value.find((f) => f.id === featureId);
    if (feature?.external_url) {
      openExternal(feature.external_url);
    }
    return;
  }

  if (key.startsWith("feature-fav:")) {
    const featureId = key.slice("feature-fav:".length);
    const feature = systemFeatures.value.find((f) => f.id === featureId);
    if (feature?.route) {
      pushRoute({ path: feature.route });
    }
    return;
  }

  pushRoute(key);
}
</script>

<template>
  <n-layout class="main-layout" has-sider>
    <!-- 桌面端侧栏 -->
    <n-layout-sider
      v-if="!isMobile"
      v-model:collapsed="siderCollapsed"
      class="app-sider"
      bordered
      collapse-mode="width"
      :collapsed-width="56"
      :width="220"
    >
      <div class="sider-inner">
        <div class="sider-carbon-bg" aria-hidden="true">
          <svg
            class="sider-carbon-bg__svg"
            viewBox="0 0 220 210"
            fill="none"
            preserveAspectRatio="xMidYMax meet"
          >
            <defs>
              <g
                id="sider-leaf"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <path
                  fill="currentColor"
                  fill-opacity="0.1"
                  stroke="currentColor"
                  stroke-width="1.05"
                  d="M50 8C70 20 84 48 88 86C92 124 78 152 54 168C52 170 51 170 50 170C49 170 48 170 46 168C22 152 8 124 12 86C16 48 30 20 50 8Z"
                />
                <path
                  fill="none"
                  stroke="currentColor"
                  stroke-width="0.68"
                  d="M50 164C51 128 52 78 50 22"
                />
                <g
                  fill="none"
                  stroke="currentColor"
                  stroke-width="0.4"
                  opacity="0.8"
                >
                  <path d="M50 52C40 57 31 65 26 74" />
                  <path d="M50 52C60 57 69 65 74 74" />
                  <path d="M50 88C38 95 28 105 22 116" />
                  <path d="M50 88C62 95 72 105 78 116" />
                  <path d="M50 124C40 131 31 140 26 150" />
                  <path d="M50 124C60 131 69 140 74 150" />
                </g>
              </g>
            </defs>
            <g>
              <!-- 双叶同向：尖端朝右上，整体偏下 -->
              <use
                href="#sider-leaf"
                transform="translate(62 198) rotate(36) translate(-50 -170)"
              />
              <path
                fill="#0D2A47"
                d="M50 8C70 20 84 48 88 86C92 124 78 152 54 168C52 170 51 170 50 170C49 170 48 170 46 168C22 152 8 124 12 86C16 48 30 20 50 8Z"
                transform="translate(98 188) rotate(42) translate(-50 -170)"
              />
              <use
                href="#sider-leaf"
                transform="translate(98 188) rotate(42) translate(-50 -170)"
              />
            </g>
          </svg>
        </div>
        <div class="brand" :class="{ 'brand--collapsed': siderCollapsed }">
          <template v-if="siderCollapsed">
            <n-button
              quaternary
              circle
              size="small"
              class="sider-toggle"
              :aria-label="t('header.toggleSidebar')"
              @click="toggleSider"
            >
              <svg
                class="sider-toggle-icon"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.75"
                stroke-linecap="round"
                stroke-linejoin="round"
                aria-hidden="true"
              >
                <rect x="3.5" y="3.5" width="17" height="17" rx="2.5" />
                <line x1="9.5" y1="3.5" x2="9.5" y2="20.5" />
              </svg>
            </n-button>
          </template>
          <template v-else>
            <PlatformBrandIcon class="brand-logo" />
            <div class="brand-head">
              <span class="brand-name">
                <PlatformBrandTitle :title="sidebarBrandTitle" strong />
              </span>
              <n-button
                quaternary
                circle
                size="small"
                class="sider-toggle"
                :aria-label="t('header.toggleSidebar')"
                @click="toggleSider"
              >
                <svg
                  class="sider-toggle-icon"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.75"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  aria-hidden="true"
                >
                  <rect x="3.5" y="3.5" width="17" height="17" rx="2.5" />
                  <line x1="9.5" y1="3.5" x2="9.5" y2="20.5" />
                </svg>
              </n-button>
            </div>
          </template>
        </div>
        <div ref="siderMenuWrapRef" class="sider-menu-wrap" @click="onSiderMenuWrapClick">
          <div
            class="sider-menu-indicator"
            aria-hidden="true"
            :style="menuIndicatorStyle"
          />
          <n-menu
            class="sider-menu"
            :value="resolvedActiveKey"
            :options="menuOptions"
            :expanded-keys="expandedKeys"
            :collapsed-width="56"
            :icon-size="18"
            :collapsed-icon-size="18"
            :node-props="siderMenuNodeProps"
            @update:expanded-keys="onExpandedKeysUpdate"
          />
        </div>
        <div v-if="!siderCollapsed" class="sider-decor" aria-hidden="true">
          <img class="sider-decor__logo" :src="haiyiLogoSrc" alt="" />
        </div>
      </div>
    </n-layout-sider>
    <!-- 移动端无需抽屉，改用底部导航栏 -->
    <n-layout class="app-main">
      <n-layout-header :bordered="false" :class="['header', { 'header--tab-mode': showAiHomeTabBar }, { 'header--mob': isMobile }]">
        <div class="header-stack">
          <div
            class="header-primary"
            :class="{ 'header-primary--toolbar-only': !showHeaderPrimary }"
          >
            <n-space align="center" justify="space-between" style="width: 100%">
              <n-space v-if="showHeaderPrimary" align="center" :size="isMobile ? 6 : 10" class="header-leading">
                <template v-if="showTitleInPrimary">
                  <div class="header-title-inline">
                    <span class="header-title">{{ headerTitle }}</span>
                    <span v-if="headerDescription" class="header-title-desc">{{ headerDescription }}</span>
                  </div>
                </template>
              </n-space>
              <span v-else aria-hidden="true" />
              <HeaderToolbar ref="headerToolbarRef" />
            </n-space>
          </div>
          <div
            id="page-header-extension"
            class="header-extension"
            :class="{ 'header-extension--reserved': reservesHeaderExtension }"
          >
            <div v-if="showAiHomeTabBar" class="ai-home-tab-bar-wrap">
              <ChatTabBar
                :tabs="chatTabs"
                :active-tab-id="chatActiveTabId"
                :can-create-tab="chatCanCreateTab"
                :tab-count="chatTabCount"
                :tab-streaming="tabStreaming"
                :tab-has-content="tabHasContent"
                :history-active="chatHistoryDrawerOpen"
                @switch="switchChatTab"
                @close="closeChatTab"
                @create="createChatTab"
                @close-all="closeAllTabs"
                @history="toggleChatHistoryDrawer"
              />
            </div>
            <div v-else-if="!showTitleInPrimary" class="bare-feature-title-row">
              <div class="bare-feature-title-left">
                <n-button
                  v-if="showSubsystemBack"
                  quaternary
                  circle
                  size="tiny"
                  class="header-back"
                  :aria-label="t('header.back')"
                  @click="goSubsystemBack"
                >
                  <n-icon :size="14" :component="ArrowBackOutline" />
                </n-button>
                <div class="bare-feature-title-block">
                  <div class="bare-feature-title-line">
                    <span class="bare-feature-title">{{ headerTitle }}</span>
                    <div id="header-title-adjacent" class="header-title-adjacent"></div>
                  </div>
                  <div class="bare-feature-description-row">
                    <span v-if="headerDescription" class="bare-feature-description">{{ headerDescription }}</span>
                  </div>
                  <div class="bare-feature-tools-row">
                    <div id="header-page-tools" class="header-page-tools"></div>
                    <div id="header-actions-row" class="bare-feature-actions-row"></div>
                  </div>
                </div>
              </div>
              <div id="header-actions" class="header-actions"></div>
            </div>
          </div>
        </div>
      </n-layout-header>
      <n-layout-content
        :class="[
          'app-content',
          {
            'app-content--full': fullHeightPage,
            'app-content--flush-start': fullHeightPage && route.meta?.flushStart,
            'app-content--flush-end': fullHeightPage && route.meta?.flushEnd,
          },
        ]"
        :content-style="contentStyle"
      >
        <div
          :class="[
            'app-view-host',
            { 'app-view-host--full': fullHeightPage },
          ]"
        >
          <router-view v-slot="{ Component, route: viewRoute }">
            <KeepAlive :max="8" :include="KEEP_ALIVE_VIEWS">
              <component
                :is="Component"
                :key="routeViewKey(viewRoute)"
                :class="[
                  'app-route-page',
                  { 'app-route-page--full': viewRoute.meta?.fullHeight },
                ]"
              />
            </KeepAlive>
          </router-view>
        </div>
      </n-layout-content>
    </n-layout>
  </n-layout>
  <ReleaseHighlightsModal
    v-model:show="releaseHighlightsOpen"
    :highlights="releaseHighlights"
    @acknowledge="onReleaseHighlightsAcknowledge"
  />
  <SystemNotificationToast />
  <!-- 本析智能：历史对话左侧抽屉 -->
  <Teleport to="body">
    <Transition name="chat-history-backdrop">
      <div
        v-if="chatHistoryDrawerOpen"
        class="chat-history-drawer-backdrop"
        @click="chatHistoryDrawerOpen = false"
      />
    </Transition>
    <Transition name="chat-history-slide">
      <div
        v-if="chatHistoryDrawerOpen"
        class="chat-history-drawer"
        role="dialog"
        :aria-label="t('chatHistory.title')"
        @click.stop
      >
        <ChatHistorySidebar
          :show="chatHistoryDrawerOpen"
          scope="ai-home"
          @update:show="chatHistoryDrawerOpen = $event"
          @navigate="chatHistoryDrawerOpen = false"
        />
      </div>
    </Transition>
  </Teleport>
  <!-- 移动端底部导航栏 -->
  <div v-if="isMobile" class="mobile-bottom-tabs">
    <button
      v-for="tab in mobileBottomTabs"
      :key="tab.key"
      class="mobile-tab-item"
      :class="{ 'mobile-tab-item--active': mobileTabActiveKey === tab.key }"
      @click="onMobileTabSelect(tab.key)"
    >
      <n-icon :size="22" :component="tab.icon" />
      <span class="mobile-tab-label">{{ tab.label }}</span>
    </button>
  </div>
</template>

<style scoped>
.main-layout :deep(.n-layout-header) {
  overflow: visible !important;
}

.main-layout {
  --feature-content-inset-x: 24px;
  height: 100vh;
  min-height: 100vh;
  overflow: hidden;
}

/* 系统壳层：侧栏 / 顶栏毛玻璃由 platform-ui-glass.css 统一控制 */
.main-layout :deep(.app-sider.n-layout-sider) {
  border-right: 1px solid var(--platform-glass-border-soft, var(--platform-border));
}

.main-layout .header {
  border-bottom: none;
}

/* Header 微妙的玻璃质感 — 仅在非 tab 模式 / 无 feature-local-nav 时生效 */
.main-layout .header::after {
  display: none;
}

/* ai-home 标签页模式：移除 header 底部边框，交由标签栏的标签下边框控制 */
.main-layout .header.header--tab-mode {
  border-bottom: none;
}


.app-sider {
  height: 100vh;
}

/* 侧栏最底部：海颐 logo */
.sider-decor {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  padding: 12px 0 16px;
  box-sizing: border-box;
}

.sider-decor__logo {
  width: 36%;
  max-width: 78px;
  height: auto;
  display: block;
  object-fit: contain;
}

.app-sider :deep(.n-layout-sider-scroll-container) {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.sider-inner {
  position: relative;
  display: flex;
  flex-direction: column;
  flex: 1;
  height: 100%;
  min-height: 0;
  padding: 6px 0 0;
  box-sizing: border-box;
  background: transparent;
  overflow: hidden;
}

/* 双碳线条图标：贴在 haiyi logo 正上方 */
.sider-carbon-bg {
  position: absolute;
  left: -4%;
  right: -4%;
  bottom: 52px;
  height: 38%;
  max-height: 280px;
  z-index: 0;
  pointer-events: none;
  overflow: visible;
  color: #8EC4E8;
  opacity: 0.42;
}

.sider-carbon-bg__svg {
  display: block;
  width: 100%;
  height: 100%;
  overflow: visible;
}

.app-sider.n-layout-sider--collapsed .sider-carbon-bg {
  left: -10%;
  right: -10%;
  bottom: 16px;
  height: 36%;
  opacity: 0.24;
}

.app-sider:not(.n-layout-sider--collapsed) .sider-carbon-bg {
  bottom: 52px;
}

.brand,
.sider-menu-wrap,
.sider-decor {
  position: relative;
  z-index: 1;
}
.sider-toggle {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  color: #ACD2EB;
  border: none !important;
  outline: none !important;
  border-radius: var(--platform-radius-sm);
}
.sider-toggle:hover {
  color: #FFFFFF;
  background: rgba(255, 255, 255, 0.08) !important;
}
.sider-toggle-icon {
  width: 20px;
  height: 20px;
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px 12px 12px;
  margin: 0 8px 4px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  flex-shrink: 0;
  overflow: hidden;
  font-size: 0.9375rem;
  border-radius: 0;
  transition: padding 0.25s var(--platform-ease-smooth);
}
.brand--collapsed {
  justify-content: center;
  gap: 0;
  padding: 10px 0 14px;
  margin: 0 4px 4px;
}
.brand-head {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 4px;
}
.brand-name {
  flex: 1;
  min-width: 0;
  font-family: var(--platform-font);
  font-size: inherit;
  font-weight: 700;
  line-height: 1.3;
  letter-spacing: -0.02em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #FFFFFF;
}
.brand-name :deep(.platform-brand-title),
.brand-name :deep(.platform-brand-title--strong),
.brand-name :deep(.platform-brand-title__plain),
.brand-name :deep(.platform-text-gradient) {
  color: #FFFFFF !important;
  font-weight: 700;
  background: none !important;
  -webkit-background-clip: unset !important;
  background-clip: unset !important;
  -webkit-text-fill-color: #FFFFFF !important;
}
.brand-logo {
  flex-shrink: 0;
  filter: none;
}
.brand-logo :deep(.platform-brand-icon) {
  width: 1em;
  height: 1em;
}
.sider-menu-wrap {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

/* 选中态流动玻璃指示条样式见 sider-menu.css */

.sider-menu {
  position: relative;
  z-index: 1;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 4px 0 12px;
}

/* 收缩后：图标水平居中，与上方展开按钮对齐 */
.app-sider.n-layout-sider--collapsed .sider-menu .n-menu-item-content {
  padding-right: 0 !important;
  justify-content: center;
}
.app-sider.n-layout-sider--collapsed .sider-menu .n-menu-item-content__icon {
  margin-right: 0 !important;
}
.app-main {
  height: 100vh;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.app-main :deep(.n-layout-scroll-container) {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
}

.app-content:not(.app-content--full) :deep(.n-layout-scroll-container) {
  overflow-y: auto !important;
  overflow-x: hidden;
  -webkit-overflow-scrolling: touch;
  scrollbar-gutter: stable;
}

.app-content {
  flex: 1;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  scrollbar-gutter: stable;
}
.header {
  position: relative;
  z-index: 100;
  overflow: visible;
  padding: 0;
  height: auto;
  min-height: 64px;
  display: flex;
  align-items: stretch;
  flex-shrink: 0;
}

/* 隐藏顶栏标题行高度由内容撑开（本析智能标签栏模式仍保留工具条） */
.header--bare {
  min-height: 0;
}

.header-stack {
  display: flex;
  flex-direction: column;
  width: 100%;
  min-width: 0;
}
/* 在顶栏 primary 区域显示的标题行（知识检索/报告生成） */
.header-title-inline {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
  min-width: 0;
}
.header-title-inline .header-title {
  font-size: 18px;
  font-weight: var(--platform-font-weight-strong);
  color: var(--platform-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.header-title-inline .header-title-desc {
  font-size: var(--platform-font-size-sm);
  color: var(--platform-text-tertiary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header-primary {
  height: 64px;
  padding: 0 24px;
  display: flex;
  align-items: center;
  flex-shrink: 0;
  box-sizing: border-box;
}

.header-primary--toolbar-only {
  height: 48px;
  min-height: 48px;
}
.bare-feature-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 24px;
  min-height: 52px;
  min-width: 0;
}
.bare-feature-title-block {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 1px;
  min-width: 0;
  flex: 1;
}
.bare-feature-description-row {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.bare-feature-actions-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex-wrap: wrap;
  margin-top: 12px;
}

.header-extension:empty:not(.header-extension--reserved) {
  display: none;
}
.header-extension--reserved {
  min-height: 52px;
  flex-shrink: 0;
  box-sizing: border-box;
}
.header-extension:not(:empty) {
  flex-shrink: 0;
  box-sizing: border-box;
  background: transparent;
  border-top: none;
  border-bottom: none;
}
.bare-feature-title {
  font-size: 24px;
  font-weight: var(--platform-font-weight-strong);
  color: var(--platform-text);
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bare-feature-title-line {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.header-title-adjacent {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  min-width: 0;
  /* 避免 :empty 在 Teleport 注入瞬间把容器隐藏导致定位失败 */
  min-height: 1px;
}
.header-title-adjacent:empty {
  display: flex;
  width: 0;
  overflow: hidden;
  pointer-events: none;
}
.bare-feature-description {
  font-size: var(--platform-font-size-sm);
  font-weight: 400;
  color: var(--platform-text-tertiary);
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 480px;
}

.header-leading {
  flex: 1;
  min-width: 0;
}

.header-back {
  flex-shrink: 0;
  width: 26px !important;
  height: 26px !important;
  min-width: 26px !important;
  min-height: 26px !important;
  color: var(--platform-accent);
  --n-height: 26px !important;
  --n-icon-size: 16px !important;
}
.header-back :deep(.n-icon) {
  font-size: 16px !important;
  width: 16px !important;
  height: 16px !important;
}

.header-back:hover {
  color: var(--platform-accent-hover);
}

.app-content--full {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-sizing: border-box;
  padding: 17px var(--feature-content-inset-x, 24px) 17px;
}

.app-content--full.app-content--flush-start {
  padding-left: 0;
}

.app-content--full.app-content--flush-end {
  padding-right: 0;
}

.app-content--full.app-content--flush-start.app-content--flush-end {
  padding-bottom: 0;
}
.app-view-host {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  background: transparent;
  transform: translateZ(0);
  isolation: isolate;
}

.app-content:not(.app-content--full) .app-view-host {
  flex: none;
  min-height: auto;
  overflow: visible;
}

.app-route-page {
  min-height: 100%;
  width: 100%;
  box-sizing: border-box;
  background: transparent;
  backface-visibility: hidden;
  -webkit-backface-visibility: hidden;
}

.app-content:not(.app-content--full) .app-route-page:not(.app-route-page--full) {
  min-height: auto;
}

.app-route-page--full {
  min-height: 100%;
  height: 100%;
  min-width: 0;
  max-width: 100%;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
}

.app-route-page--full > :deep(*) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  width: 100%;
}

.app-view-host--full {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  width: 100%;
}

/* ai-home 多标签栏容器：与内容区同色，无分割线 */
.ai-home-tab-bar-wrap {
  width: 100%;
  display: flex;
  align-items: stretch;
  padding: 0 24px 0 4px;
  box-sizing: border-box;
  background: transparent;
}

/* === 移动端适配 === */

.header--mob {
  min-height: 48px;
}

.header--mob .header-primary {
  height: 48px;
  padding: 0 12px;
}

/* =============================================
 * 移动端适配（< 768px）：缩小布局尺寸、
 * 防溢出、隐藏次要元素
 * ============================================= */
@media (max-width: 768px) {
  .header-primary {
    padding: 0 10px;
  }
  .main-layout {
    max-width: 100vw;
    overflow-x: hidden;
  }
  .app-main {
    max-width: 100vw;
    overflow-x: hidden;
  }
  .main-layout :deep(.app-content) {
    padding: 0 !important;
    font-size: 14px;
    max-width: 100% !important;
    overflow-x: hidden !important;
    box-sizing: border-box !important;
  }
  .main-layout .app-content--full {
    padding: 0 10px 10px !important;
  }
  .app-content :deep(.n-layout-scroll-container) {
    max-width: 100% !important;
    overflow-x: hidden !important;
    box-sizing: border-box !important;
  }
  .header-extension--reserved {
    min-height: 36px;
  }
  .ai-home-tab-bar-wrap {
    padding: 0 10px 0 2px;
  }
  /* 移动端底部导航栏：预留空间 */
  .main-layout .app-content {
    padding-bottom: 60px !important;
  }
  .main-layout .app-content--full {
    padding-bottom: calc(10px + 60px) !important;
  }
  /* 全局内容紧凑：缩小行距与标题字号 */
  .main-layout .app-content {
    --platform-mobile-content: 1;
  }

  /* === 防溢出 — 文本换行与媒体缩放 === */
  .app-view-host,
  .app-route-page,
  .app-route-page--full {
    max-width: 100%;
    overflow-x: hidden;
    box-sizing: border-box;
    word-wrap: break-word;
    overflow-wrap: break-word;
  }

  .main-layout .app-content :deep(img),
  .main-layout .app-content :deep(video),
  .main-layout .app-content :deep(iframe),
  .main-layout .app-content :deep(pre),
  .main-layout .app-content :deep(table),
  .main-layout .app-content :deep(svg) {
    max-width: 100% !important;
    height: auto;
  }

  .main-layout .app-content :deep(.n-scrollbar),
  .main-layout .app-content :deep(.n-scrollbar-content) {
    max-width: 100%;
    overflow-x: hidden;
  }

  .main-layout .app-content :deep(.n-space) {
    flex-wrap: wrap;
    min-width: 0;
  }

  .main-layout .app-content :deep(h1) {
    font-size: 18px;
  }
  .main-layout .app-content :deep(h2) {
    font-size: 16px;
  }
  .main-layout .app-content :deep(h3) {
    font-size: 14px;
  }
  .main-layout .app-content :deep(p) {
    line-height: 1.5;
    margin-bottom: 8px;
  }
  .main-layout .app-content :deep(.n-card) {
    font-size: 13px;
  }
  .main-layout .app-content :deep(.n-card__content) {
    padding: 10px 12px;
  }
  .main-layout .app-content :deep(.n-card__header) {
    padding: 10px 12px 0;
  }

  /* ── Header 移动端优化 ── */
  .header--mob .header-primary {
    height: 44px;
    padding: 0 10px;
  }
  .header--mob .header-primary :deep(.n-space) {
    gap: 4px !important;
  }
  .header--tab-mode.header--mob {
    min-height: 0;
  }

  /* 标题栏优化 - 减小标题字号 */
  .bare-feature-title {
    font-size: 18px !important;
  }
  .bare-feature-description {
    font-size: 11px !important;
    max-width: 200px;
  }
  .bare-feature-title-row {
    min-height: 40px;
    padding: 0 10px;
  }
  .header-title-inline .header-title {
    font-size: 15px;
  }
  .header-title-inline .header-title-desc {
    font-size: 11px;
  }

  /* ── 隐藏操作栏中的描述文字 ── */
  .bare-feature-description-row {
    display: none;
  }

  /* ── content 内边距减小 ── */
  .main-layout .app-content {
    --feature-content-inset-x: 10px;
  }
  .main-layout .app-content--full {
    padding: 0 10px 14px !important;
  }

  /* ── 底部导航栏安全区优化 ── */
  .mobile-bottom-tabs {
    height: 50px;
    padding-bottom: 0;
  }
  .mobile-tab-item {
    gap: 1px;
    padding: 2px 0;
  }
  .mobile-tab-item :deep(.n-icon) {
    font-size: 20px !important;
  }
  .mobile-tab-label {
    font-size: 9px;
  }

  /* ── 隐藏侧栏相关的不必要元素 ── */
  .header-back {
    width: 26px !important;
    height: 26px !important;
  }
  .header-back :deep(.n-icon) {
    font-size: 16px !important;
    width: 16px !important;
    height: 16px !important;
  }
}

/* === 本析智能：历史对话左侧抽屉 === */
.chat-history-drawer-backdrop {
  position: fixed;
  inset: 0;
  z-index: 10590;
  background: rgba(0, 0, 0, 0.25);
}

.chat-history-drawer {
  position: fixed;
  left: 0;
  top: 0;
  bottom: 0;
  width: min(360px, calc(100vw - 48px));
  z-index: 10600;
  display: flex;
  flex-direction: column;
  background: var(--platform-bg-elevated-solid, #fff);
  border-right: 1px solid var(--platform-border);
  box-shadow: var(--platform-shadow-lg);
  overflow: hidden;
}

.chat-history-slide-enter-active {
  transition: transform 0.28s cubic-bezier(0.22, 0.85, 0.32, 1);
}

.chat-history-slide-leave-active {
  transition: transform 0.22s cubic-bezier(0.22, 0.85, 0.32, 1);
}

.chat-history-slide-enter-from,
.chat-history-slide-leave-to {
  transform: translateX(-100%);
}

.chat-history-backdrop-enter-active {
  transition: opacity 0.28s ease;
}

.chat-history-backdrop-leave-active {
  transition: opacity 0.22s ease;
}

.chat-history-backdrop-enter-from,
.chat-history-backdrop-leave-to {
  opacity: 0;
}

/* === 移动端底部导航栏 === */
.mobile-bottom-tabs {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 1000;
  display: flex;
  align-items: stretch;
  height: 56px;
  background: var(--platform-sider-bg, #fff);
  border-top: 1px solid var(--platform-border, #e5e5e5);
  padding-bottom: env(safe-area-inset-bottom, 0);
  box-sizing: content-box;
}

.mobile-tab-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  border: none;
  background: transparent;
  color: var(--platform-text-secondary, #999);
  cursor: pointer;
  padding: 4px 0;
  min-width: 0;
  transition: color 0.2s ease;
  -webkit-tap-highlight-color: transparent;
}

.mobile-tab-item--active {
  color: var(--platform-accent, #005A9E);
}

.mobile-tab-label {
  font-size: 10px;
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}
</style>


<!-- 非 scoped：Teleport 到 #header-page-tools / #header-actions / #header-actions-row 的按钮样式 -->
<style>
/* 标题左侧容器：后退按钮 + 标题块 */
.bare-feature-title-left {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  min-width: 0;
  flex: 1;
}

/* 工具栏容器：所有按钮区在同一行 */
.bare-feature-tools-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
}
#header-page-tools {
  display: flex;
  align-items: center;
  gap: 6px;
}
/* 与标题同行的右侧按钮区 */
#header-actions {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
  padding-top: 2px;
}
#header-actions-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  min-width: 0;
  flex: 1;
  margin-top: 0;
}
#header-actions-row .documents-actions-bar {
  padding: 0;
}
#header-actions-row .documents-actions-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

/* —— 统一工具栏按钮：约头像尺寸再略小（26px），图标 16px —— */
.header .header-toolbar .header-icon-btn,
#header-page-tools .header-icon-btn,
#header-actions .header-icon-btn,
#header-actions .icon-action,
#header-actions-row .icon-action,
#header-actions-row .n-button.n-button--quaternary:not(.agent-skills-action-btn),
#header-page-tools .n-button.n-button--quaternary {
  flex-shrink: 0 !important;
  width: 26px !important;
  height: 26px !important;
  min-width: 0 !important;
  min-height: 0 !important;
  padding: 0 !important;
  border: none !important;
  box-shadow: none !important;
  outline: none !important;
  border-radius: 50% !important;
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  line-height: 0 !important;
  --n-height: 26px !important;
  --n-icon-size: 16px !important;
  background: color-mix(in srgb, var(--platform-bg-tertiary) 52%, transparent) !important;
  color: var(--platform-text-tertiary) !important;
  font-size: var(--platform-font-size-sm) !important;
  transition:
    color 0.2s ease,
    background 0.2s ease !important;
}

/* 工具栏按钮中的图标: 统一 16px */
.header .header-toolbar .header-icon-btn .n-icon,
#header-page-tools .header-icon-btn .n-icon,
#header-actions .header-icon-btn .n-icon,
#header-actions-row .icon-action .n-icon,
#header-actions-row .n-button .n-icon,
#header-page-tools .n-button .n-icon {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  font-size: 16px !important;
  width: 16px !important;
  height: 16px !important;
}

/* 刷新按钮：加载时图标旋转动画（替代 Naive UI 内置 loading spinner） */
#header-page-tools .header-icon-btn--spinning .n-icon,
#header-actions .header-icon-btn--spinning .n-icon {
  animation: agent-header-spin 0.6s linear infinite;
}
#header-page-tools .header-icon-btn--spinning .n-icon svg,
#header-actions .header-icon-btn--spinning .n-icon svg {
  transform-origin: center center;
}
@keyframes agent-header-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 悬浮：更深玻璃背景 */
#header-page-tools .header-icon-btn:not(:disabled):hover,
#header-actions .header-icon-btn:not(:disabled):hover,
#header-actions-row .icon-action:not(:disabled):hover,
#header-actions-row .n-button.n-button--quaternary:not(.agent-skills-action-btn):not(:disabled):hover,
#header-page-tools .n-button.n-button--quaternary:not(:disabled):hover {
  color: var(--platform-text) !important;
  background: color-mix(in srgb, var(--platform-bg-tertiary) 80%, transparent) !important;
}

/* 选中/激活态 */
#header-page-tools .header-icon-btn--active,
#header-actions .header-icon-btn--active,
#header-actions .icon-action.icon-action--active {
  color: var(--platform-accent) !important;
  background: color-mix(in srgb, var(--platform-accent-soft) 72%, var(--platform-accent) 28%) !important;
}
#header-actions-row .icon-action.icon-action--active {
  color: var(--platform-accent) !important;
  background: color-mix(in srgb, var(--platform-accent-soft) 72%, var(--platform-accent) 28%) !important;
}

/* 核心操作组 */
#header-actions-row .documents-actions-core {
  display: flex;
  align-items: center;
  gap: 6px;
}

/* caution/danger 在操作栏中保持透明玻璃背景 */
#header-actions-row .icon-action.icon-action--caution:not(:disabled),
#header-actions-row .icon-action.icon-action--danger:not(:disabled) {
  background: color-mix(in srgb, var(--platform-bg-tertiary) 52%, transparent) !important;
  border: none !important;
  box-shadow: none !important;
}
#header-actions-row .icon-action.icon-action--caution:not(:disabled):hover {
  color: var(--platform-caution) !important;
  background: color-mix(in srgb, var(--platform-bg-tertiary) 80%, transparent) !important;
}
#header-actions-row .icon-action.icon-action--danger:not(:disabled):hover {
  color: var(--platform-danger) !important;
  background: color-mix(in srgb, var(--platform-bg-tertiary) 80%, transparent) !important;
}
#header-actions-row .icon-action.icon-action--caution:disabled,
#header-actions-row .icon-action.icon-action--danger:disabled {
  opacity: 0.42;
}

/* 清除 Naive UI 内部干扰元素 */
#header-actions-row .n-button.n-button--quaternary::after,
#header-page-tools .n-button.n-button--quaternary::after,
#header-actions .n-button.n-button--quaternary::after,
#header-actions-row .n-button.n-button--quaternary .n-button__border,
#header-page-tools .n-button.n-button--quaternary .n-button__border,
#header-actions .n-button.n-button--quaternary .n-button__border,
#header-actions-row .n-button.n-button--quaternary .n-button__state-border,
#header-page-tools .n-button.n-button--quaternary .n-button__state-border,
#header-actions .n-button.n-button--quaternary .n-button__state-border {
  display: none !important;
}
#header-actions-row .n-button,
#header-page-tools .n-button,
#header-actions .n-button {
  --n-ripple-duration: 0s !important;
  --n-ripple-color: transparent !important;
}
#header-page-tools .n-button,
#header-actions .n-button {
  --n-text-color: var(--platform-text-tertiary) !important;
}
#header-page-tools .n-button.n-button--quaternary,
#header-actions .n-button.n-button--quaternary {
  background: color-mix(in srgb, var(--platform-bg-tertiary) 52%, transparent) !important;
}
#header-page-tools .n-button .n-button__content,
#header-actions .n-button .n-button__content {
  font-size: inherit !important;
  line-height: 0 !important;
}

/* 操作栏搜索输入框 */
#header-actions-row .n-input {
  width: 180px !important;
  flex-shrink: 0;
}

/* 侧栏按钮去掉边框，颜色与菜单图标一致 */
.app-sider .sider-toggle,
.app-sider .sider-toggle.n-button {
  border: none !important;
  outline: none !important;
  box-shadow: none !important;
  --n-text-color: #ACD2EB !important;
  --n-text-color-hover: #FFFFFF !important;
  --n-text-color-pressed: #FFFFFF !important;
  --n-text-color-focus: #FFFFFF !important;
  color: #ACD2EB !important;
}
.app-sider .sider-toggle .n-button__border,
.app-sider .sider-toggle .n-button__state-border {
  display: none !important;
}

/* ── 侧栏菜单图标 / 文字：未选中 #ACD2EB，选中白色 ── */
.app-sider .sider-menu .n-menu-item-content {
  transition: none !important;
  color: #ACD2EB !important;
}
.app-sider .sider-menu .n-menu-item-content__icon {
  transition: none !important;
  color: #ACD2EB !important;
  font-size: 18px !important;
  width: 18px !important;
  height: 18px !important;
}
.app-sider .sider-menu .n-menu-item-content__icon .n-icon {
  transition: none !important;
  color: #ACD2EB !important;
  font-size: 18px !important;
  width: 18px !important;
  height: 18px !important;
}
.app-sider .sider-menu .n-menu-item-content--selected,
.app-sider .sider-menu .n-menu-item-content--child-active,
.app-sider .sider-menu .n-menu-item-content--hovered {
  color: #FFFFFF !important;
}
.app-sider .sider-menu .n-menu-item-content--selected .n-menu-item-content__icon,
.app-sider .sider-menu .n-menu-item-content--selected .n-menu-item-content__icon .n-icon,
.app-sider .sider-menu .n-menu-item-content--hovered .n-menu-item-content__icon,
.app-sider .sider-menu .n-menu-item-content--hovered .n-menu-item-content__icon .n-icon,
.app-sider .sider-menu .n-menu-item-content--child-active .n-menu-item-content__icon,
.app-sider .sider-menu .n-menu-item-content--child-active .n-menu-item-content__icon .n-icon {
  transition: none !important;
  color: #FFFFFF !important;
}
</style>
