<script setup>
import { computed, h, onMounted, ref, watch } from "vue";
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
  NewspaperOutline,
  ChatbubbleEllipsesOutline,
  BookOutline,
} from "@vicons/ionicons5";
import { useAuth } from "../composables/useAuth";
import { useI18n } from "../composables/useI18n";
import { getPageHeaderOverride } from "../composables/usePageHeader";
import { resolveFeatureIcon } from "../constants/featureIcons";
import { PLATFORM_APP_NAME } from "../constants/platform";
import { usePlatformBranding } from "../composables/usePlatformBranding";
import { fetchSystemFeatures } from "../api/client";
import { prefetchKnowflowSession } from "../api/rag.js";
import { useFeatureFavorites } from "../composables/useFeatureFavorites";
import HeaderToolbar from "../components/layout/HeaderToolbar.vue";
import PlatformBrandTitle from "../components/PlatformBrandTitle.vue";
import PlatformCopyright from "../components/PlatformCopyright.vue";
import { useMainLayoutRouteMotion } from "../composables/useMainLayoutRouteMotion";
import { SUBSYSTEM_PAGE_ROUTES } from "../utils/routeTransition";
import { useSiderMenuIndicator } from "../composables/useSiderMenuIndicator";
import { publicAsset } from "../utils/appBase";
import { goBackToEntry } from "../utils/navigationReturn";

const route = useRoute();
const router = useRouter();
const { loadUser, hasPerm } = useAuth();
const { t, routeTitle } = useI18n();
const pageHeaderOverride = getPageHeaderOverride();
const { innerRouteTransition } = useMainLayoutRouteMotion();
const headerToolbarRef = ref(null);

const SETTINGS_KEY = "system-settings";
const expandedKeys = ref([]);
const siderMenuWrapRef = ref(null);

const siderCollapsed = ref(false);
const systemFeatures = ref([]);
const { favoriteIds } = useFeatureFavorites();

function favoriteMenuKey(feature) {
  if (feature.external_url) return `feature-ext:${feature.id}`;
  return `feature-fav:${feature.id}`;
}

const favoriteMenuFeatures = computed(() => {
  const byId = Object.fromEntries(systemFeatures.value.map((f) => [f.id, f]));
  return favoriteIds.value.map((id) => byId[id]).filter((f) => f && f.enabled);
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

async function loadSystemFeatures() {
  try {
    systemFeatures.value = (await fetchSystemFeatures()) || [];
  } catch {
    systemFeatures.value = [];
  }
}

onMounted(async () => {
  await loadUser();
  prefetchKnowflowSession();
  loadSystemFeatures();
});

const showUserAdmin = computed(() => hasPerm("admin.user"));
const showDeptAdmin = computed(() => hasPerm("admin.dept"));
const showMonitor = computed(() => hasPerm("admin.audit"));
const showModelSettings = computed(() => hasPerm("admin.settings"));
const showRagEncoding = computed(() => hasPerm("feature.rag_qa"));

const showSystemSettings = computed(
  () =>
    showUserAdmin.value ||
    showDeptAdmin.value ||
    showMonitor.value ||
    showModelSettings.value ||
    showRagEncoding.value
);

const settingsChildren = computed(() => {
  const children = [];
  if (showUserAdmin.value) {
    children.push({
      label: t("menu.users"),
      key: "admin-users",
      icon: () => h(NIcon, null, { default: () => h(PeopleOutline) }),
    });
  }
  if (showDeptAdmin.value) {
    children.push({
      label: t("menu.departments"),
      key: "admin-departments",
      icon: () => h(NIcon, null, { default: () => h(BusinessOutline) }),
    });
  }
  if (showMonitor.value) {
    children.push({
      label: t("menu.monitor"),
      key: "admin-monitor",
      icon: () => h(NIcon, null, { default: () => h(PulseOutline) }),
    });
  }
  if (showModelSettings.value) {
    children.push({
      label: t("menu.modelSettings"),
      key: "admin-model-settings",
      icon: () => h(NIcon, null, { default: () => h(HardwareChipOutline) }),
    });
  }
  if (showRagEncoding.value) {
    children.push({
      label: t("menu.encodingManagement"),
      key: "rag",
      icon: () => h(NIcon, null, { default: () => h(ChatbubbleEllipsesOutline) }),
    });
  }
  if (showSystemSettings.value) {
    children.push({
      label: t("menu.systemDocs"),
      key: "admin-docs",
      icon: () => h(NIcon, null, { default: () => h(BookOutline) }),
    });
  }
  return children;
});

const menuOptions = computed(() => {
  const items = [
    {
      label: t("menu.aiHome"),
      key: "ai-home",
      icon: () => h(NIcon, null, { default: () => h(SparklesOutline) }),
    },
    {
      label: t("menu.systemFunctions"),
      key: "system-functions",
      icon: () => h(NIcon, null, { default: () => h(GridOutline) }),
    },
  ];

  for (const feature of favoriteMenuFeatures.value) {
    const Icon = resolveFeatureIcon(feature.icon) || GridOutline;
    items.push({
      label: feature.title,
      key: favoriteMenuKey(feature),
      icon: () => h(NIcon, null, { default: () => h(Icon) }),
    });
  }

  items.push(
    {
      label: t("menu.documents"),
      key: "documents",
      icon: () => h(NIcon, null, { default: () => h(DocumentTextOutline) }),
    },
    {
      label: t("menu.knowledgeSubscriptions"),
      key: "knowledge-subscriptions",
      icon: () => h(NIcon, null, { default: () => h(NewspaperOutline) }),
    }
  );

  if (showSystemSettings.value && settingsChildren.value.length) {
    items.push({
      label: t("menu.systemSettings"),
      key: SETTINGS_KEY,
      icon: () => h(NIcon, null, { default: () => h(SettingsOutline) }),
      children: settingsChildren.value,
    });
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
  if (route.name === "knowledge-qa") {
    return "system-functions";
  }
  if (
    route.name === "knowledge-subscriptions" ||
    route.name === "subscription-item" ||
    route.name === "wechat-mp" ||
    route.name === "wechat-mp-article" ||
    route.name === "feed-subscriptions" ||
    route.name === "feed-entry"
  ) {
    return "knowledge-subscriptions";
  }
  if (
    route.name === "translate" ||
    route.name === "speech" ||
    route.name === "ocr" ||
    route.name === "compare" ||
    route.name === "assist-writing" ||
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
    route.name === "admin-docs" ||
    route.name === "rag"
  ) {
    return String(route.name);
  }
  return String(route.name || "ai-home");
});

const fullHeightPage = computed(() => Boolean(route.meta?.fullHeight));

const flushFeatureNav = computed(
  () => fullHeightPage.value || Boolean(route.meta?.featureLocalNav)
);

const headerTitle = computed(() => {
  if (pageHeaderOverride.value) return pageHeaderOverride.value;
  return routeTitle(String(route.name || ""), String(route.meta?.title || "").trim());
});

const { platformAppTitle } = usePlatformBranding();

const appDisplayName = computed(
  () => platformAppTitle.value || t("app.name") || PLATFORM_APP_NAME
);

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

const { indicatorStyle: menuIndicatorStyle } = useSiderMenuIndicator(siderMenuWrapRef, {
  activeKey: resolvedActiveKey,
  collapsed: siderCollapsed,
  expandedKeys,
});

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

function goSubsystemBack() {
  goBackToEntry(router, route);
}

const contentStyle = computed(() => {
  if (route.meta?.fullEmbed) {
    return "padding: 0; height: 100vh; overflow: hidden";
  }
  if (fullHeightPage.value) {
    return "padding: 0; height: calc(100vh - 56px); overflow: hidden; box-sizing: border-box";
  }
  if (route.name === "system-functions") {
    return "padding: 0";
  }
  if (flushFeatureNav.value) {
    return "padding: 0 20px 12px";
  }
  return "padding: 12px 20px";
});

function ensureMenuExpanded() {
  const keys = [...expandedKeys.value];
  if (
    route.name === "admin-users" ||
    route.name === "admin-departments" ||
    route.name === "admin-monitor" ||
    route.name === "admin-model-settings" ||
    route.name === "admin-docs" ||
    route.name === "rag"
  ) {
    if (!keys.includes(SETTINGS_KEY)) keys.push(SETTINGS_KEY);
  }
  expandedKeys.value = keys;
}

watch(() => route.name, ensureMenuExpanded, { immediate: true });

watch(
  () => route.name,
  (name) => {
    headerToolbarRef.value?.closeAllFlyouts?.();
    if (name && name !== "login") {
      headerToolbarRef.value?.refreshHeaderBadges?.();
    }
  },
);

function onExpandedKeysUpdate(keys) {
  expandedKeys.value = keys;
}

function onMenuSelect(key) {
  if (key === SETTINGS_KEY) return;
  headerToolbarRef.value?.closeAllFlyouts?.();

  if (key.startsWith("feature-ext:")) {
    const featureId = key.slice("feature-ext:".length);
    const feature = systemFeatures.value.find((f) => f.id === featureId);
    if (feature?.external_url) {
      window.open(feature.external_url, "_blank", "noopener,noreferrer");
    }
    return;
  }

  if (key.startsWith("feature-fav:")) {
    const featureId = key.slice("feature-fav:".length);
    const feature = systemFeatures.value.find((f) => f.id === featureId);
    if (feature?.route) {
      router.push({ path: feature.route });
    }
    return;
  }

  router.push({ name: key });
}
</script>

<template>
  <n-layout class="main-layout" has-sider>
    <n-layout-sider
      v-model:collapsed="siderCollapsed"
      class="app-sider"
      bordered
      collapse-mode="width"
      :collapsed-width="64"
      :width="220"
      show-trigger
    >
      <div class="sider-inner">
        <div class="brand" :class="{ 'brand--collapsed': siderCollapsed }">
          <img :src="publicAsset('logo.svg')" alt="" class="brand-logo" />
          <span v-if="!siderCollapsed" class="brand-name">
            <PlatformBrandTitle :title="appDisplayName" />
          </span>
        </div>
        <div ref="siderMenuWrapRef" class="sider-menu-wrap">
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
            @update:expanded-keys="onExpandedKeysUpdate"
            @update:value="onMenuSelect"
          />
        </div>
        <PlatformCopyright v-if="!siderCollapsed" class="sider-copyright" />
      </div>
    </n-layout-sider>
    <n-layout class="app-main">
      <n-layout-header bordered class="header">
        <div class="header-stack">
          <div class="header-primary">
            <n-space align="center" justify="space-between" style="width: 100%">
              <n-space
                v-if="showSubsystemNav"
                align="center"
                :size="8"
                class="header-title-wrap header-subsystem-nav"
              >
                <n-button
                  v-if="showSubsystemBack"
                  quaternary
                  circle
                  size="small"
                  class="header-back"
                  :aria-label="t('header.back')"
                  @click="goSubsystemBack"
                >
                  <n-icon :size="20" :component="ArrowBackOutline" />
                </n-button>
                <n-text strong class="header-title">{{ headerTitle }}</n-text>
              </n-space>
              <n-space
                v-else-if="showStandardFeatureTitle || showAppTitle"
                align="center"
                :size="10"
                class="header-title-wrap"
              >
                <n-text v-if="showStandardFeatureTitle" strong class="header-title">
                  {{ headerTitle }}
                </n-text>
                <PlatformBrandTitle
                  v-else-if="showAppTitle"
                  tag="div"
                  class="header-app-title"
                  :title="appDisplayName"
                />
              </n-space>
              <HeaderToolbar ref="headerToolbarRef" />
            </n-space>
          </div>
          <div id="page-header-extension" class="header-extension" />
        </div>
      </n-layout-header>
      <n-layout-content
        :class="['app-content', { 'app-content--full': fullHeightPage }]"
        :content-style="contentStyle"
      >
        <div
          :class="[
            'app-view-host',
            { 'app-view-host--full': fullHeightPage },
          ]"
        >
          <router-view v-slot="{ Component, route: viewRoute }">
            <Transition
              v-if="innerRouteTransition !== 'route-instant'"
              :name="innerRouteTransition"
            >
              <div
                :key="viewRoute.path"
                :class="[
                  'app-route-page',
                  { 'app-route-page--full': fullHeightPage },
                ]"
              >
                <component :is="Component" />
              </div>
            </Transition>
            <div
              v-else
              :key="viewRoute.path"
              :class="[
                'app-route-page',
                { 'app-route-page--full': fullHeightPage },
              ]"
            >
              <component :is="Component" />
            </div>
          </router-view>
        </div>
      </n-layout-content>
    </n-layout>
  </n-layout>
</template>

<style scoped>
.main-layout :deep(.n-layout-header) {
  overflow: visible !important;
}

.main-layout {
  height: 100vh;
  min-height: 100vh;
  overflow: hidden;
}

/* 系统壳层：与智能体页相同的渐变底 */
.main-layout :deep(.app-sider.n-layout-sider) {
  background: var(--platform-chat-gradient) !important;
  backdrop-filter: none !important;
  -webkit-backdrop-filter: none !important;
  box-shadow: none !important;
  border-right: 1px solid var(--platform-border) !important;
}

.main-layout :deep(.app-sider.n-layout-sider::before) {
  display: none;
}

.main-layout .header {
  background: var(--platform-chat-gradient) !important;
  backdrop-filter: none !important;
  -webkit-backdrop-filter: none !important;
  box-shadow: none !important;
  border-bottom: 1px solid var(--platform-border) !important;
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
  padding: 8px 0;
  box-sizing: border-box;
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 14px 10px;
  flex-shrink: 0;
  overflow: hidden;
}
.brand--collapsed {
  justify-content: center;
  gap: 0;
  padding-left: 0;
  padding-right: 0;
}
.brand-name {
  font-family: var(--platform-font-display);
  font-size: 1.2rem;
  font-weight: 700;
  line-height: 1.25;
  letter-spacing: 0.04em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}
.brand-logo {
  width: 30px;
  height: 30px;
  flex-shrink: 0;
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
  left: 14px;
  right: 10px;
  top: 0;
  z-index: 0;
  border-radius: var(--platform-radius-sm);
  pointer-events: none;
  background: linear-gradient(
    180deg,
    var(--menu-glass-bg-active) 0%,
    var(--menu-glass-bg-active-bottom) 100%
  );
  box-shadow: inset 0 1px 0 var(--liquid-edge-highlight);
  transition:
    transform 0.45s var(--platform-ease-spring-soft),
    height 0.4s var(--platform-ease-spring-soft),
    opacity 0.3s var(--platform-ease-smooth),
    box-shadow 0.3s var(--platform-ease-smooth);
}

.sider-menu {
  position: relative;
  z-index: 1;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 4px 10px 10px 14px;
}
.sider-copyright {
  flex-shrink: 0;
  border-top: 1px solid var(--platform-divider);
}
.app-main {
  height: 100vh;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--platform-chat-gradient);
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
  min-height: 56px;
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
  height: 56px;
  padding: 0 20px;
  display: flex;
  align-items: center;
  flex-shrink: 0;
  box-sizing: border-box;
}

.header-extension:empty {
  display: none;
}

.header-extension:not(:empty) {
  flex-shrink: 0;
  box-sizing: border-box;
  background: transparent;
  border-top: none;
  border-bottom: none;
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
  color: var(--platform-accent);
}

.header-back:hover {
  color: var(--platform-accent-hover);
}

.header-title {
  font-size: 17px;
  font-weight: 600;
  letter-spacing: var(--platform-tracking-tight);
  color: var(--platform-text);
}

.header-app-title {
  font-size: 17px;
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
}
.app-view-host {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  background: transparent;
  transform: translateZ(0);
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
  display: flex;
  flex-direction: column;
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
</style>
