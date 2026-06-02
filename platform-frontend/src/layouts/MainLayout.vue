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
  NBadge,
  NSpace,
  NText,
  NAvatar,
  NPopover,
  NDropdown,
  NTooltip,
} from "naive-ui";
import {
  DocumentTextOutline,
  NotificationsOutline,
  TimeOutline,
  PeopleOutline,
  BusinessOutline,
  LogOutOutline,
  GridOutline,
  SettingsOutline,
  PulseOutline,
  HardwareChipOutline,
  ListOutline,
  SparklesOutline,
  GitNetworkOutline,
  ArrowBackOutline,
  NewspaperOutline,
  PersonOutline,
  ChevronDownOutline,
  MoonOutline,
  SunnyOutline,
  LanguageOutline,
  ChatbubbleEllipsesOutline,
} from "@vicons/ionicons5";
import { NIcon } from "naive-ui";
import { useAuth } from "../composables/useAuth";
import { useAppPreferences } from "../composables/useAppPreferences";
import { useI18n } from "../composables/useI18n";
import { getPageHeaderOverride } from "../composables/usePageHeader";
import { resolveFeatureIcon } from "../constants/featureIcons";
import { PLATFORM_APP_NAME } from "../constants/platform";
import { fetchJobs, fetchNotifications } from "../api/client";
import AssistantChatFab from "../components/AssistantChatFab.vue";
import PlatformCopyright from "../components/PlatformCopyright.vue";
import JobsPanel from "../components/JobsPanel.vue";
import NotificationsPanel from "../components/NotificationsPanel.vue";
import { consumeSkipInnerRouteMotion } from "../utils/routeTransition";
import { publicAsset } from "../utils/appBase";
import { goBackToEntry } from "../utils/navigationReturn";

const route = useRoute();
const router = useRouter();
const { user, loadUser, logout, hasPerm } = useAuth();
const { isDark, toggleTheme, toggleLocale } = useAppPreferences();
const { t, routeTitle, localeLabel } = useI18n();
const pageHeaderOverride = getPageHeaderOverride();

const innerRouteTransition = ref(
  consumeSkipInnerRouteMotion() ? "route-instant" : "route-fade",
);

const SETTINGS_KEY = "system-settings";
const expandedKeys = ref([]);

const unreadCount = ref(0);
const activeJobCount = ref(0);
const siderCollapsed = ref(false);
const jobsPopoverOpen = ref(false);
const notificationsPopoverOpen = ref(false);
const assistantOpen = ref(false);

async function refreshUnreadCount() {
  try {
    const data = await fetchNotifications({ page: 1, page_size: 1, unread_only: true });
    unreadCount.value = data.total ?? 0;
  } catch {
    unreadCount.value = 0;
  }
}

async function refreshActiveJobCount() {
  try {
    const data = await fetchJobs({ page: 1, page_size: 50 });
    activeJobCount.value = (data.items || []).filter((job) =>
      ["pending", "running"].includes(job.status)
    ).length;
  } catch {
    activeJobCount.value = 0;
  }
}

async function refreshHeaderBadges() {
  await Promise.all([refreshUnreadCount(), refreshActiveJobCount()]);
}

onMounted(async () => {
  await loadUser();
  refreshHeaderBadges();
});

const showUserAdmin = computed(() => hasPerm("admin.user"));
const showDeptAdmin = computed(() => hasPerm("admin.dept"));
const showMonitor = computed(() => hasPerm("admin.audit"));
const showModelSettings = computed(() => hasPerm("admin.settings"));
const showSystemSettings = computed(
  () =>
    showUserAdmin.value ||
    showDeptAdmin.value ||
    showMonitor.value ||
    showModelSettings.value
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
    {
      label: t("menu.documents"),
      key: "documents",
      icon: () => h(NIcon, null, { default: () => h(DocumentTextOutline) }),
    },
    {
      label: t("menu.knowledgeSubscriptions"),
      key: "knowledge-subscriptions",
      icon: () => h(NIcon, null, { default: () => h(NewspaperOutline) }),
    },
    {
      label: t("menu.knowledgeGraph"),
      key: "knowledge-graph",
      icon: () => h(NIcon, null, { default: () => h(GitNetworkOutline) }),
    },
  ];
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
const SUBSYSTEM_HEADER_ROUTES = new Set([
  "ai-tools",
  "translate",
  "rag",
  "smart-data-query",
  "carbon-qa",
  "carbon-assets",
  "smart-forecast",
  "speech",
  "ocr",
  "compare",
  "assist-writing",
  "knowledge-graph",
  "knowledge-search",
  "knowledge-subscriptions",
  "subscription-item",
  "wechat-mp",
  "wechat-mp-article",
  "feed-subscriptions",
  "feed-entry",
  "document-detail",
  "chat-history",
  "carbon-assets-history",
]);

const isSubsystemPage = computed(() =>
  SUBSYSTEM_HEADER_ROUTES.has(String(route.name || ""))
);

function toggleAssistant() {
  jobsPopoverOpen.value = false;
  notificationsPopoverOpen.value = false;
  assistantOpen.value = !assistantOpen.value;
}

const activeKey = computed(() => {
  if (route.name === "document-detail") return "documents";
  if (route.name === "knowledge-search") return "ai-home";
  if (route.name === "knowledge-graph") return "knowledge-graph";
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
    route.name === "rag" ||
    route.name === "speech" ||
    route.name === "ocr" ||
    route.name === "compare" ||
    route.name === "assist-writing" ||
    route.name === "ai-tools" ||
    route.name === "smart-data-query" ||
    route.name === "carbon-qa" ||
    route.name === "smart-forecast"
  ) {
    return "system-functions";
  }
  if (
    route.name === "admin-users" ||
    route.name === "admin-departments" ||
    route.name === "admin-monitor" ||
    route.name === "admin-model-settings"
  ) {
    return String(route.name);
  }
  return String(route.name || "ai-home");
});

const fullHeightPage = computed(() => Boolean(route.meta?.fullHeight));

const headerTitle = computed(() => {
  if (pageHeaderOverride.value) return pageHeaderOverride.value;
  return routeTitle(String(route.name || ""), String(route.meta?.title || "").trim());
});

const appDisplayName = computed(() => t("app.name") || PLATFORM_APP_NAME);

const headerIcon = computed(() => resolveFeatureIcon(route.meta?.featureIcon));

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
    return "padding: 8px 12px; height: calc(100vh - 52px); overflow: hidden; box-sizing: border-box";
  }
  return "padding: 20px 24px";
});

function ensureMenuExpanded() {
  const keys = [...expandedKeys.value];
  if (
    route.name === "admin-users" ||
    route.name === "admin-departments" ||
    route.name === "admin-monitor" ||
    route.name === "admin-model-settings"
  ) {
    if (!keys.includes(SETTINGS_KEY)) keys.push(SETTINGS_KEY);
  }
  expandedKeys.value = keys;
}

watch(() => route.name, ensureMenuExpanded, { immediate: true });

watch(
  () => route.name,
  (name) => {
    jobsPopoverOpen.value = false;
    notificationsPopoverOpen.value = false;
    if (name && name !== "login") refreshHeaderBadges();
  }
);

function onJobsUpdated() {
  refreshActiveJobCount();
}

function onNotificationsUpdated() {
  refreshUnreadCount();
}

function closeJobsPopover() {
  jobsPopoverOpen.value = false;
}

function closeNotificationsPopover() {
  notificationsPopoverOpen.value = false;
}

function goTodos() {
  jobsPopoverOpen.value = false;
  notificationsPopoverOpen.value = false;
  router.push({ name: "todos" });
}

function onExpandedKeysUpdate(keys) {
  expandedKeys.value = keys;
}

function onMenuSelect(key) {
  if (key === SETTINGS_KEY) return;
  jobsPopoverOpen.value = false;
  notificationsPopoverOpen.value = false;
  router.push({ name: key });
}

function doLogout() {
  logout();
  router.push({ name: "login" });
}

const userDisplayName = computed(
  () =>
    user.value?.display_name ||
    user.value?.username ||
    t("userMenu.defaultName")
);

const userMenuOptions = computed(() => [
  {
    label: t("userMenu.profile"),
    key: "profile",
    icon: () => h(NIcon, null, { default: () => h(PersonOutline) }),
  },
  { type: "divider", key: "divider-prefs" },
  {
    label: isDark.value ? t("userMenu.lightMode") : t("userMenu.darkMode"),
    key: "theme",
    icon: () =>
      h(NIcon, null, {
        default: () => h(isDark.value ? SunnyOutline : MoonOutline),
      }),
  },
  {
    label: localeLabel.value,
    key: "locale",
    icon: () => h(NIcon, null, { default: () => h(LanguageOutline) }),
  },
  { type: "divider", key: "divider-logout" },
  {
    label: t("userMenu.logout"),
    key: "logout",
    icon: () => h(NIcon, null, { default: () => h(LogOutOutline) }),
  },
]);

function onUserMenuSelect(key) {
  if (key === "profile") {
    router.push({ name: "profile" });
    return;
  }
  if (key === "theme") {
    toggleTheme();
    return;
  }
  if (key === "locale") {
    toggleLocale();
    return;
  }
  if (key === "logout") {
    doLogout();
  }
}

function renderUserMenuOption({ node, option }) {
  if (option.type === "divider") return node;
  if (option.key === "logout") {
    return h("div", { class: "platform-dropdown-option--danger" }, node);
  }
  return node;
}
</script>

<template>
  <n-layout class="app-shell" has-sider>
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
          <span v-if="!siderCollapsed" class="brand-name">{{ appDisplayName }}</span>
        </div>
        <n-menu
          class="sider-menu"
          :value="activeKey"
          :options="menuOptions"
          :expanded-keys="expandedKeys"
          @update:expanded-keys="onExpandedKeysUpdate"
          @update:value="onMenuSelect"
        />
        <PlatformCopyright v-if="!siderCollapsed" class="sider-copyright" />
      </div>
    </n-layout-sider>
    <n-layout class="app-main">
      <n-layout-header bordered class="header">
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
            <div v-if="headerIcon" class="header-feature-icon header-feature-icon--brand">
              <n-icon :size="20" :component="headerIcon" />
            </div>
            <n-text strong class="header-title">{{ headerTitle }}</n-text>
          </n-space>
          <n-space
            v-else-if="showStandardFeatureTitle || showAppTitle"
            align="center"
            :size="10"
            class="header-title-wrap"
          >
            <div v-if="headerIcon && showStandardFeatureTitle" class="header-feature-icon">
              <n-icon :size="22" :component="headerIcon" />
            </div>
            <n-text v-if="showStandardFeatureTitle" strong class="header-title">
              {{ headerTitle }}
            </n-text>
            <n-text v-else-if="showAppTitle" depth="2">{{ appDisplayName }}</n-text>
          </n-space>
          <div class="header-actions">
            <div class="header-toolbar">
              <n-button
                quaternary
                circle
                size="small"
                class="header-icon-btn"
                :type="route.name === 'todos' ? 'primary' : 'default'"
                :aria-label="t('header.todos')"
                @click="goTodos"
              >
                <n-icon :size="18" :component="ListOutline" />
              </n-button>
              <n-popover
                v-model:show="jobsPopoverOpen"
                trigger="click"
                placement="bottom-end"
                :show-arrow="false"
                raw
              >
                <template #trigger>
                  <n-badge :value="activeJobCount" :max="99" :show="activeJobCount > 0">
                    <n-button
                      quaternary
                      circle
                      size="small"
                      class="header-icon-btn"
                      :type="jobsPopoverOpen || route.name === 'jobs' ? 'primary' : 'default'"
                      :aria-label="t('header.jobs')"
                    >
                      <n-icon :size="18" :component="TimeOutline" />
                    </n-button>
                  </n-badge>
                </template>
                <JobsPanel
                  variant="popover"
                  :active="jobsPopoverOpen"
                  @updated="onJobsUpdated"
                  @navigate="closeJobsPopover"
                />
              </n-popover>
              <n-popover
                v-model:show="notificationsPopoverOpen"
                trigger="click"
                placement="bottom-end"
                :show-arrow="false"
                raw
              >
                <template #trigger>
                  <n-badge :value="unreadCount" :max="99" :show="unreadCount > 0">
                    <n-button
                      quaternary
                      circle
                      size="small"
                      class="header-icon-btn"
                      :type="
                        notificationsPopoverOpen || route.name === 'notifications'
                          ? 'primary'
                          : 'default'
                      "
                      :aria-label="t('header.notifications')"
                    >
                      <n-icon :size="18" :component="NotificationsOutline" />
                    </n-button>
                  </n-badge>
                </template>
                <NotificationsPanel
                  variant="popover"
                  :active="notificationsPopoverOpen"
                  @updated="onNotificationsUpdated"
                  @navigate="closeNotificationsPopover"
                />
              </n-popover>
              <n-tooltip placement="bottom">
                <template #trigger>
                  <n-button
                    quaternary
                    circle
                    size="small"
                    class="header-icon-btn"
                    :type="assistantOpen ? 'primary' : 'default'"
                    :aria-label="t('header.assistant')"
                    @click="toggleAssistant"
                  >
                    <n-icon :size="18" :component="ChatbubbleEllipsesOutline" />
                  </n-button>
                </template>
                {{ t("header.assistant") }}
              </n-tooltip>
            </div>
            <n-dropdown
              trigger="click"
              placement="bottom-end"
              :options="userMenuOptions"
              :render-option="renderUserMenuOption"
              @select="onUserMenuSelect"
            >
              <button type="button" class="header-user-trigger" :aria-label="t('header.userMenu')">
                <n-avatar round size="small" class="header-user-avatar">
                  {{ userDisplayName[0] || "U" }}
                </n-avatar>
                <span class="header-username">{{ userDisplayName }}</span>
                <n-icon :size="14" :component="ChevronDownOutline" class="header-user-chevron" />
              </button>
            </n-dropdown>
          </div>
        </n-space>
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
            <Transition :name="innerRouteTransition" mode="out-in">
              <component :is="Component" :key="viewRoute.path" />
            </Transition>
          </router-view>
        </div>
      </n-layout-content>
    </n-layout>
    <AssistantChatFab v-model:open="assistantOpen" />
  </n-layout>
</template>

<style scoped>
.app-shell {
  height: 100vh;
  min-height: 100vh;
  overflow: hidden;
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
  padding: 12px 0;
  box-sizing: border-box;
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 600;
  font-size: 0.95rem;
  letter-spacing: -0.02em;
  padding: 10px 18px 14px;
  color: var(--platform-text);
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
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}
.brand-logo {
  width: 28px;
  height: 28px;
  flex-shrink: 0;
}
.sider-menu {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
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
.app-content {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.header {
  padding: 0 20px;
  height: 52px;
  display: flex;
  align-items: center;
  flex-shrink: 0;
  background: var(--platform-header-bg);
  backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
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

.header-feature-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--platform-text);
}

.header-feature-icon--brand {
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  color: var(--platform-accent);
  background: var(--platform-accent-soft);
  border: 1px solid var(--platform-border);
  border-radius: var(--platform-radius-sm);
}

.header-title {
  font-size: 16px;
  font-weight: 600;
  letter-spacing: -0.02em;
  color: var(--platform-text);
}
.header-actions {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  margin-left: auto;
}

.header-toolbar {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 3px;
  border-radius: 10px;
  background: var(--platform-toolbar-bg);
  border: 1px solid var(--platform-border);
}

.header-icon-btn {
  width: 32px;
  height: 32px;
}

.header-user-trigger {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  max-width: 180px;
  padding: 4px 10px 4px 4px;
  border: 1px solid var(--platform-border);
  border-radius: var(--platform-radius-pill);
  background: var(--platform-toolbar-bg);
  cursor: pointer;
  font: inherit;
  color: inherit;
  transition:
    background 0.2s ease,
    border-color 0.2s ease;
}

.header-user-trigger:hover {
  background: var(--platform-bg-elevated);
  border-color: var(--platform-border-strong);
}

.header-user-avatar {
  flex-shrink: 0;
  background: var(--platform-accent-soft) !important;
  color: var(--platform-accent) !important;
  font-weight: 600;
}

.header-username {
  max-width: 96px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 500;
  color: var(--platform-text);
}

.header-user-chevron {
  flex-shrink: 0;
  color: var(--platform-text-tertiary);
}
.app-content--full {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-sizing: border-box;
}
.app-view-host--full {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  width: 100%;
}
.app-view-host--full > * {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  width: 100%;
}
</style>
