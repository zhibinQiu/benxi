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
  NSpace,
  NText,
  NIcon,
  NDrawer,
  NDrawerContent,
  NLayoutFooter } from "naive-ui";
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
  NewspaperOutline,
  BugOutline,
  ListOutline,
  MenuOutline } from "@vicons/ionicons5";
import { useAuth } from "../composables/useAuth";
import { useI18n } from "../composables/useI18n";
import { useSystemFeatures } from "../composables/useSystemFeatures";
import { useMenuSettings } from "../composables/useMenuSettings";
import { getPageHeaderOverride } from "../composables/usePageHeader";
import { resolveFeatureIcon } from "../constants/featureIcons";
import { useAppDisplayName } from "../composables/usePlatformBranding";
import { useFeatureFavorites } from "../composables/useFeatureFavorites";
import HeaderToolbar from "../components/layout/HeaderToolbar.vue";
import PlatformBrandTitle from "../components/PlatformBrandTitle.vue";
import PlatformBrandIcon from "../components/PlatformBrandIcon.vue";
import PlatformCopyright from "../components/PlatformCopyright.vue";
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
import { prefetchKgPalantir } from "../composables/useKgPalantirPrefetch.js";
import { prefetchKnowledgeScopeTree } from "../composables/useKnowledgeScopeTree.js";
import { getToken } from "../api/client.js";
import { openExternal } from "../utils/openExternal.js";
import ChatTabBar from "../components/ChatTabBar.vue";
import { useChatTabs } from "../composables/useChatTabs.js";

/** 对话 / 知识检索 / 报告生成 / 我的文件 / 多智能体保留实例；其余功能离开路由后销毁以释放内存 */
const KEEP_ALIVE_VIEWS = ["AiHomeView", "KnowledgeFeatureLayout", "DocumentsView", "AgentSkillsView"];

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
const { t, routeTitle, featureLabel } = useI18n();
const { loadMenuSettings, isMenuVisible } = useMenuSettings();
const pageHeaderOverride = getPageHeaderOverride();
const headerToolbarRef = ref(null);
const releaseHighlightsOpen = ref(false);
const releaseHighlights = ref(null);

const SETTINGS_KEY = "system-settings";
const expandedKeys = ref([]);
const siderMenuWrapRef = ref(null);

const siderCollapsed = ref(false);
const mobileDrawerOpen = ref(false);
const isMobile = ref(window.innerWidth < 768);

function checkMobile() {
  isMobile.value = window.innerWidth < 768;
  if (!isMobile.value) mobileDrawerOpen.value = false;
}
let resizeTimer = null;
function onResize() {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(checkMobile, 100);
}

function toggleSider() {
  siderCollapsed.value = !siderCollapsed.value;
}

function openMobileDrawer() {
  mobileDrawerOpen.value = true;
}

function closeMobileDrawer() {
  mobileDrawerOpen.value = false;
}
const { features: systemFeatures, loadSystemFeatures } = useSystemFeatures();
const { favoriteIds } = useFeatureFavorites();

function favoriteMenuKey(feature) {
  if (feature.external_url) return `feature-ext:${feature.id}`;
  return `feature-fav:${feature.id}`;
}

const favoriteMenuFeatures = computed(() => {
  const byId = Object.fromEntries(systemFeatures.value.map((f) => [f.id, f]));
  return favoriteIds.value
    .map((id) => byId[id])
    .filter((f) => f && f.enabled && f.accessible);
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

const KNOWLEDGE_ROUTES = new Set(["knowledge-search", "report-generation"]);
const KG_ROUTES = new Set(["kg-palantir"]);

function prefetchFeatureCaches() {
  if (!getToken()) return;
  prefetchKnowledgeScopeTree();
  prefetchKgPalantir();
}

onMounted(() => {
  startNotificationAlerts();
  prefetchFeatureCaches();
  checkMobile();
  window.addEventListener("resize", onResize);
  Promise.allSettled([loadUser(), loadSystemFeatures(), loadMenuSettings()]).then(() => {
    prefetchFeatureCaches();
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
    if (KNOWLEDGE_ROUTES.has(routeName)) prefetchKnowledgeScopeTree();
    if (KG_ROUTES.has(routeName)) prefetchKgPalantir();
  },
  { immediate: true }
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

  if (isMenuVisible("documents")) {
    items.push({
      label: t("menu.documents"),
      key: "documents",
      icon: () => h(NIcon, null, { default: () => h(DocumentTextOutline) })});
  }
  if (isMenuVisible("knowledge-subscriptions")) {
    items.push({
      label: t("menu.knowledgeSubscriptions"),
      key: "knowledge-subscriptions",
      icon: () => h(NIcon, null, { default: () => h(NewspaperOutline) })});
  }
  if (isMenuVisible("issue-reports")) {
    items.push({
      label: t("menu.issueReports"),
      key: "issue-reports",
      icon: () => h(NIcon, null, { default: () => h(BugOutline) })});
  }

  for (const feature of favoriteMenuFeatures.value) {
    const Icon = resolveFeatureIcon(feature.icon) || GridOutline;
    items.push({
      label: featureLabel(feature.id, "title", feature.title),
      key: favoriteMenuKey(feature),
      icon: () => h(NIcon, null, { default: () => h(Icon) })});
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
    route.name === "knowledge-subscriptions" ||
    route.name === "subscription-item"
  ) {
    return "knowledge-subscriptions";
  }
  if (
    route.name === "translate" ||
    route.name === "speech" ||
    route.name === "text-to-speech" ||
    route.name === "ocr" ||
    route.name === "compare" ||
    route.name === "agent-skills" ||
    route.name === "knowledge-search" ||
    route.name === "report-generation" ||
    route.name === "ai-tools" ||
    route.name === "smart-data-query" ||
    route.name === "data-analysis" ||
    route.name === "carbon-qa" ||
    route.name === "smart-forecast"
  ) {
    return "system-functions";
  }
  if (
    route.name === "admin-users" ||
    route.name === "admin-departments" ||
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
  if (
    route.name === "documents" ||
    route.name === "knowledge-subscriptions" ||
    route.name === "subscription-item" ||
    route.name === "translate"
  ) {
    return true;
  }
  return flushFeatureNav.value;
});

const headerTitle = computed(() => {
  if (pageHeaderOverride.value) return pageHeaderOverride.value;
  return routeTitle(String(route.name || ""), String(route.meta?.title || "").trim());
});

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

const showSubsystemNav = computed(
  () => isSubsystemPage.value && Boolean(headerTitle.value)
);

const showSubsystemBack = computed(() => showSubsystemNav.value);

const showStandardFeatureTitle = computed(
  () => Boolean(headerTitle.value) && !isSubsystemPage.value
);

const showAppTitle = computed(
  () => !showSubsystemNav.value && !showStandardFeatureTitle.value
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
  switchTab: switchChatTab,
  syncActiveTabFromRoute,
  updateTabTitle,
} = useChatTabs();

/** 仅在 ai-home 相关路由显示标签栏 */
const showAiHomeTabBar = computed(() =>
  route.name === "ai-home" || route.name === "ai-home-tab"
);

function goSubsystemBack() {
  goBackToEntry(router, route);
}

function goToChatHistory() {
  router.push({ name: "chat-history", params: { scope: "ai-home" } });
}

const contentStyle = computed(() => {
  if (route.meta?.fullEmbed) {
    return "padding: 0; height: 100vh; overflow: hidden";
  }
  if (fullHeightPage.value) {
    return "flex: 1; min-height: 0; overflow: hidden; box-sizing: border-box";
  }
  if (route.name === "system-functions") {
    return "padding: 0";
  }
  if (flushFeatureNav.value) {
    return "padding: 0 24px 14px";
  }
  return "padding: 14px 24px";
});

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
      :collapsed-width="77"
      :width="264"
    >
      <div class="sider-inner">
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
                <PlatformBrandTitle :title="sidebarBrandTitle" />
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
            :node-props="siderMenuNodeProps"
            @update:expanded-keys="onExpandedKeysUpdate"
          />
        </div>
        <PlatformCopyright v-if="!siderCollapsed" class="sider-copyright" />
      </div>
    </n-layout-sider>
    <!-- 移动端抽屉 -->
    <n-drawer
      v-else
      :show="mobileDrawerOpen"
      :width="264"
      placement="left"
      class="mob-sider-drawer"
      @update:show="closeMobileDrawer"
    >
      <n-drawer-content :native-scrollbar="false" :body-content-style="{ padding: 0 }">
        <div class="sider-inner sider-inner--mob">
          <div class="brand">
            <PlatformBrandIcon class="brand-logo" />
            <div class="brand-head">
              <span class="brand-name">
                <PlatformBrandTitle :title="sidebarBrandTitle" />
              </span>
            </div>
          </div>
          <div ref="siderMenuWrapRef" class="sider-menu-wrap" @click="onSiderMenuWrapClick">
            <n-menu
              class="sider-menu"
              :value="resolvedActiveKey"
              :options="menuOptions"
              :expanded-keys="expandedKeys"
              :node-props="siderMenuNodeProps"
              @update:expanded-keys="onExpandedKeysUpdate"
              @update:value="closeMobileDrawer"
            />
          </div>
          <PlatformCopyright class="sider-copyright" />
        </div>
      </n-drawer-content>
    </n-drawer>
    <n-layout class="app-main">
      <n-layout-header :bordered="!showAiHomeTabBar" :class="['header', { 'header--tab-mode': showAiHomeTabBar }, { 'header--mob': isMobile }]">
        <div class="header-stack">
          <div class="header-primary">
            <n-space align="center" justify="space-between" style="width: 100%">
              <n-space align="center" :size="isMobile ? 6 : 10" class="header-leading">
                <!-- 移动端汉堡菜单 -->
                <n-button
                  v-if="isMobile"
                  quaternary
                  circle
                  size="tiny"
                  class="mob-hamburger"
                  aria-label="Open menu"
                  @click="openMobileDrawer"
                >
                  <n-icon :size="22" :component="MenuOutline" />
                </n-button>
                <n-space
                v-if="showSubsystemNav"
                align="center"
                :size="10"
                class="header-title-wrap header-subsystem-nav"
              >
                <n-button
                  v-if="showSubsystemBack"
                  quaternary
                  circle
                  size="tiny"
                  class="header-back"
                  :aria-label="t('header.back')"
                  @click="goSubsystemBack"
                >
                  <n-icon :size="19" :component="ArrowBackOutline" />
                </n-button>
                <n-text strong class="header-title">{{ headerTitle }}</n-text>
              </n-space>
              <n-space
                v-else-if="showStandardFeatureTitle || showAppTitle"
                align="center"
                :size="12"
                class="header-title-wrap"
              >
                <n-text v-if="showStandardFeatureTitle" strong class="header-title">
                  {{ headerTitle }}
                </n-text>
                <PlatformBrandTitle
                  v-else-if="showAppTitle && !siderCollapsed"
                  tag="div"
                  class="header-app-title"
                  :title="appDisplayName"
                />
              </n-space>
              </n-space>
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
                :intro-text="t('aiHome.chatHeaderSub')"
                @switch="switchChatTab"
                @close="closeChatTab"
                @create="createChatTab"
                @history="goToChatHistory"
              />
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
            <KeepAlive :max="12" :include="KEEP_ALIVE_VIEWS">
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

/* 系统壳层：与智能体页相同的渐变底（底色见 feature-local-nav.css 壳层规则） */
.main-layout :deep(.app-sider.n-layout-sider) {
  backdrop-filter: none !important;
  -webkit-backdrop-filter: none !important;
  box-shadow: none !important;
  border-right: 1px solid var(--platform-border) !important;
}

.main-layout :deep(.app-sider.n-layout-sider::before) {
  display: none;
}

.main-layout .header {
  backdrop-filter: none !important;
  -webkit-backdrop-filter: none !important;
  box-shadow: none !important;
  border-bottom: 1px solid var(--platform-border) !important;
}

/* ai-home 标签页模式：移除 header 底部边框，交由标签栏的标签下边框控制 */
.main-layout .header.header--tab-mode {
  border-bottom: none !important;
}

.main-layout:has(.app-content .feature-local-nav) .header,
.main-layout:has(.app-content .feature-top-strip) .header {
  border-bottom: none !important;
}

.app-sider {
  height: 100vh;
}
.app-sider :deep(.n-layout-sider-scroll-container) {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.sider-inner {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: 6px 0 0;
  box-sizing: border-box;
  background: var(--platform-sider-bg);
}
.sider-toggle {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  color: var(--platform-text-secondary);
  border-radius: var(--platform-radius-sm);
  transition:
    color 0.2s ease,
    background 0.2s ease;
}
.sider-toggle:hover {
  color: var(--platform-text);
  background: var(--platform-bg-tertiary) !important;
}
.sider-toggle-icon {
  width: 20px;
  height: 20px;
  display: block;
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 14px 12px 17px;
  margin: 0 8px 4px;
  border-bottom: 1px solid var(--platform-divider);
  flex-shrink: 0;
  overflow: hidden;
  font-size: 0.9375rem;
  border-radius: 0;
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
  font-family: var(--platform-font-display);
  font-size: inherit;
  font-weight: 700;
  line-height: 1.3;
  letter-spacing: -0.02em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  background: var(--platform-accent-gradient);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.brand-logo {
  flex-shrink: 0;
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

.sider-menu-indicator {
  position: absolute;
  left: 10px;
  right: 10px;
  top: 0;
  z-index: 0;
  border-radius: var(--platform-radius-sm);
  pointer-events: none;
  background: var(--sider-menu-glass-fill-active, var(--platform-glass-fill-active));
  box-shadow: var(--menu-glass-rim-edge-active);
  will-change: transform, height;
  transition:
    transform 0.3s cubic-bezier(0.22, 0.85, 0.32, 1),
    height 0.25s cubic-bezier(0.22, 0.85, 0.32, 1),
    opacity 0.15s ease;
}

.sider-menu {
  position: relative;
  z-index: 1;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 4px 12px 12px 17px;
}
.sider-copyright {
  flex-shrink: 0;
  margin-top: auto;
  padding-bottom: 2px;
}

.sider-copyright :deep(.platform-copyright) {
  padding: 2px 14px 5px;
}

.sider-copyright :deep(.platform-copyright p) {
  font-size: 11px;
  line-height: 1.35;
}

.sider-copyright :deep(.platform-copyright .coffee-invite) {
  font-size: 11px;
  line-height: 1.35;
  margin-bottom: 2px;
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

.header-stack {
  display: flex;
  flex-direction: column;
  width: 100%;
  min-width: 0;
}

.header-primary {
  height: 64px;
  padding: 0 24px;
  display: flex;
  align-items: center;
  flex-shrink: 0;
  box-sizing: border-box;
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
.header-leading {
  flex: 1;
  min-width: 0;
}

.header-title-wrap {
  min-width: 0;
}

.header-subsystem-nav {
  flex: 1;
  min-width: 0;
}

.header-back {
  flex-shrink: 0;
  width: 31px;
  height: 31px;
  color: var(--platform-accent);
}

.header-back:hover {
  color: var(--platform-accent-hover);
}

.header-title {
  font-size: 18px;
  font-weight: 600;
  letter-spacing: var(--platform-tracking-tight);
  color: var(--platform-text);
}

.header-app-title {
  font-size: 18px;
  font-weight: 600;
  letter-spacing: var(--platform-tracking-tight);
}

.header-app-title :deep(.platform-brand-title) {
  font-size: inherit;
  font-weight: inherit;
  letter-spacing: inherit;
}
.app-content--full {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-sizing: border-box;
  padding: 0 var(--feature-content-inset-x, 24px) 14px;
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

/* ai-home 多标签栏容器 */
.ai-home-tab-bar-wrap {
  width: 100%;
  display: flex;
  align-items: stretch;
  padding: 0 24px;
  box-sizing: border-box;
  background: var(--platform-bg-secondary);
}

/* === 移动端适配 === */
.mob-hamburger {
  flex-shrink: 0;
  color: var(--platform-text-secondary);
}

.mob-sider-drawer :deep(.n-drawer-body) {
  padding: 0;
}

.mob-sider-drawer :deep(.n-drawer-body-content-wrapper) {
  display: flex;
  flex-direction: column;
}

.sider-inner--mob {
  height: 100%;
}

.header--mob {
  min-height: 48px;
}

.header--mob .header-primary {
  height: 48px;
  padding: 0 12px;
}

.header--mob .header-title {
  font-size: 15px;
}

@media (max-width: 768px) {
  .header-primary {
    padding: 0 12px;
  }
  .main-layout :deep(.app-content) {
    padding: 0 !important;
  }
  .main-layout .app-content--full {
    padding: 0 12px 14px !important;
  }
  .header-extension--reserved {
    min-height: 40px;
  }
  .ai-home-tab-bar-wrap {
    padding: 0 12px;
  }
}
</style>
