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
  NIcon } from "naive-ui";
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
  ListOutline,
  BookOutline } from "@vicons/ionicons5";
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
import PlatformCopyright from "../components/PlatformCopyright.vue";
import { SUBSYSTEM_PAGE_ROUTES } from "../utils/routeTransition";
import { useSiderMenuIndicator } from "../composables/useSiderMenuIndicator";
import { publicAsset } from "../utils/appBase";
import { goBackToEntry } from "../utils/navigationReturn";
import { sessionEpoch } from "../utils/sessionEpoch.js";

/** 保留对话类页面实例，避免切路由丢失会话与顶栏操作条状态 */
const KEEP_ALIVE_VIEWS = ["AiHomeView", "ReportGenerationView"];

function routeViewKey(viewRoute) {
  const base = viewRoute.meta?.keepAlive
    ? String(viewRoute.name || viewRoute.path)
    : viewRoute.path;
  return `${sessionEpoch.value}:${base}`;
}

const route = useRoute();
const router = useRouter();
const { loadUser, hasPerm, isSystemAdmin } = useAuth();
const { t, routeTitle, featureLabel } = useI18n();
const { loadMenuSettings, isMenuVisible } = useMenuSettings();
const pageHeaderOverride = getPageHeaderOverride();
const headerToolbarRef = ref(null);

const SETTINGS_KEY = "system-settings";
const expandedKeys = ref([]);
const siderMenuWrapRef = ref(null);

const siderCollapsed = ref(false);
const { features: systemFeatures, loadSystemFeatures } = useSystemFeatures();
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

onMounted(() => {
  Promise.allSettled([loadUser(), loadSystemFeatures(), loadMenuSettings()]);
});

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
        icon: () => h(NIcon, null, { default: () => h(ListOutline) })},
      {
        label: t("menu.modelSettings"),
        key: "admin-model-settings",
        icon: () => h(NIcon, null, { default: () => h(HardwareChipOutline) })}
    );
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
    {
      label: t("menu.systemDocs"),
      key: "admin-docs",
      icon: () => h(NIcon, null, { default: () => h(BookOutline) })},
  ];
  for (const item of memberSettingsMenus) {
    if (isSystemAdmin.value || isMenuVisible(item.key)) {
      children.push(item);
    }
  }
  return children;
});

const menuOptions = computed(() => {
  const items = [];

  if (isSystemAdmin.value || isMenuVisible("ai-home")) {
    items.push({
      label: t("menu.aiHome"),
      key: "ai-home",
      icon: () => h(NIcon, null, { default: () => h(SparklesOutline) })});
  }
  if (isSystemAdmin.value || isMenuVisible("system-functions")) {
    items.push({
      label: t("menu.systemFunctions"),
      key: "system-functions",
      icon: () => h(NIcon, null, { default: () => h(GridOutline) })});
  }

  for (const feature of favoriteMenuFeatures.value) {
    const Icon = resolveFeatureIcon(feature.icon) || GridOutline;
    items.push({
      label: featureLabel(feature.id, "title", feature.title),
      key: favoriteMenuKey(feature),
      icon: () => h(NIcon, null, { default: () => h(Icon) })});
  }

  if (isSystemAdmin.value || isMenuVisible("documents")) {
    items.push({
      label: t("menu.documents"),
      key: "documents",
      icon: () => h(NIcon, null, { default: () => h(DocumentTextOutline) })});
  }
  if (isSystemAdmin.value || isMenuVisible("knowledge-subscriptions")) {
    items.push({
      label: t("menu.knowledgeSubscriptions"),
      key: "knowledge-subscriptions",
      icon: () => h(NIcon, null, { default: () => h(NewspaperOutline) })});
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
    route.name === "admin-docs"
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

const appDisplayName = useAppDisplayName();

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
    return "padding: 0";
  }
  if (flushFeatureNav.value) {
    return "padding: 0 20px 12px";
  }
  return "padding: 12px 20px";
});

function onExpandedKeysUpdate(keys) {
  expandedKeys.value = keys;
}

watch(
  () => route.name,
  (name) => {
    headerToolbarRef.value?.closeAllFlyouts?.();
    if (name && name !== "login") {
      headerToolbarRef.value?.refreshHeaderBadges?.();
    }
  },
);

function onSiderMenuWrapClick(e) {
  const content = e.target?.closest?.(".n-menu-item-content");
  if (!content || content.classList.contains("n-menu-item-content--disabled")) return;
  moveIndicatorToContent(content);

  // 子功能页侧栏仍高亮「功能列表」，再点同一项时 Naive Menu 不会触发 update:value
  if (
    isSubsystemPage.value &&
    resolvedActiveKey.value === "system-functions" &&
    content.classList.contains("n-menu-item-content--selected")
  ) {
    router.push({ name: "system-functions" });
  }
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
            <KeepAlive :max="2" :include="KEEP_ALIVE_VIEWS">
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
</template>

<style scoped>
.main-layout :deep(.n-layout-header) {
  overflow: visible !important;
}

.main-layout {
  --feature-content-inset-x: 20px;
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
  flex: 1;
  min-width: 0;
  font-family: var(--platform-font-display);
  font-size: 0.9375rem;
  font-weight: 700;
  line-height: 1.3;
  letter-spacing: 0.01em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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
  background: var(--sider-menu-glass-fill-active, var(--platform-glass-fill-active));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.42);
  will-change: transform;
  transition:
    transform 0.24s cubic-bezier(0.22, 0.95, 0.32, 1),
    height 0.2s cubic-bezier(0.22, 0.95, 0.32, 1),
    opacity 0.12s ease;
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
  padding: 0 var(--feature-content-inset-x, 20px) 12px;
}

.app-content--full.app-content--flush-start {
  padding-left: 0;
}

.app-content--full.app-content--flush-end {
  padding-right: 0;
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
</style>
