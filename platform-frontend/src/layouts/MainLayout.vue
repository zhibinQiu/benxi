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
} from "@vicons/ionicons5";
import { NIcon } from "naive-ui";
import { useAuth } from "../composables/useAuth";
import { resolveFeatureIcon } from "../constants/featureIcons";
import { PLATFORM_APP_NAME } from "../constants/platform";
import { fetchJobs, fetchNotifications } from "../api/client";
import AssistantChatFab from "../components/AssistantChatFab.vue";
import JobsPanel from "../components/JobsPanel.vue";
import NotificationsPanel from "../components/NotificationsPanel.vue";
import { consumeSkipInnerRouteMotion } from "../utils/routeTransition";
import { publicAsset } from "../utils/appBase";
import { goBackToEntry } from "../utils/navigationReturn";

const route = useRoute();
const router = useRouter();
const { user, loadUser, logout, hasPerm } = useAuth();

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
      label: "用户管理",
      key: "admin-users",
      icon: () => h(NIcon, null, { default: () => h(PeopleOutline) }),
    });
  }
  if (showDeptAdmin.value) {
    children.push({
      label: "部门管理",
      key: "admin-departments",
      icon: () => h(NIcon, null, { default: () => h(BusinessOutline) }),
    });
  }
  if (showMonitor.value) {
    children.push({
      label: "系统监控",
      key: "admin-monitor",
      icon: () => h(NIcon, null, { default: () => h(PulseOutline) }),
    });
  }
  if (showModelSettings.value) {
    children.push({
      label: "模型配置",
      key: "admin-model-settings",
      icon: () => h(NIcon, null, { default: () => h(HardwareChipOutline) }),
    });
  }
  return children;
});

const menuOptions = computed(() => {
  const items = [
    {
      label: "双碳智能体",
      key: "ai-home",
      icon: () => h(NIcon, null, { default: () => h(SparklesOutline) }),
    },
    {
      label: "功能列表",
      key: "system-functions",
      icon: () => h(NIcon, null, { default: () => h(GridOutline) }),
    },
    {
      label: "待办事项",
      key: "todos",
      icon: () => h(NIcon, null, { default: () => h(ListOutline) }),
    },
    {
      label: "文档中心",
      key: "documents",
      icon: () => h(NIcon, null, { default: () => h(DocumentTextOutline) }),
    },
    {
      label: "网站收藏",
      key: "knowledge-subscriptions",
      icon: () => h(NIcon, null, { default: () => h(NewspaperOutline) }),
    },
    {
      label: "切片管理",
      key: "knowledge-graph",
      icon: () => h(NIcon, null, { default: () => h(GitNetworkOutline) }),
    },
  ];
  if (showSystemSettings.value && settingsChildren.value.length) {
    items.push({
      label: "系统设置",
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

/** 主菜单一级页与常用业务页展示悬浮客服；子功能全屏页与双碳首页不展示 */
const showAssistant = computed(() => {
  if (route.meta?.public || route.meta?.hideAssistant) return false;
  if (route.name === "login" || route.name === "ai-home") return false;
  if (isSubsystemPage.value) return false;
  return true;
});

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

const headerTitle = computed(() => String(route.meta?.title || "").trim());

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

function onExpandedKeysUpdate(keys) {
  expandedKeys.value = keys;
}

function onMenuSelect(key) {
  if (key === SETTINGS_KEY) return;
  router.push({ name: key });
}

function doLogout() {
  logout();
  router.push({ name: "login" });
}

const userDisplayName = computed(
  () => user.value?.display_name || user.value?.username || "用户"
);

const userMenuOptions = [
  {
    label: "信息维护",
    key: "profile",
    icon: () => h(NIcon, null, { default: () => h(PersonOutline) }),
  },
  { type: "divider", key: "divider" },
  {
    label: "退出",
    key: "logout",
    icon: () => h(NIcon, null, { default: () => h(LogOutOutline) }),
  },
];

function onUserMenuSelect(key) {
  if (key === "profile") {
    router.push({ name: "profile" });
    return;
  }
  if (key === "logout") {
    doLogout();
  }
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
          <span v-if="!siderCollapsed" class="brand-name">{{ PLATFORM_APP_NAME }}</span>
        </div>
        <n-menu
          class="sider-menu"
          :value="activeKey"
          :options="menuOptions"
          :expanded-keys="expandedKeys"
          @update:expanded-keys="onExpandedKeysUpdate"
          @update:value="onMenuSelect"
        />
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
              aria-label="返回"
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
            <n-text v-else-if="showAppTitle" depth="2">{{ PLATFORM_APP_NAME }}</n-text>
          </n-space>
          <div class="header-actions">
            <div class="header-toolbar">
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
                      aria-label="后台任务"
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
                      aria-label="消息"
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
            </div>
            <n-dropdown
              trigger="click"
              placement="bottom-end"
              :options="userMenuOptions"
              @select="onUserMenuSelect"
            >
              <button type="button" class="header-user-trigger" aria-label="用户菜单">
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
    <AssistantChatFab v-if="showAssistant" />
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
  letter-spacing: 0.02em;
  padding: 10px 18px 14px;
  color: #0f172a;
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
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(8px);
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
  color: #0d9488;
}

.header-back:hover {
  color: #0f766e;
}

.header-feature-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--n-text-color);
}

.header-feature-icon--brand {
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  color: #0d9488;
  background: linear-gradient(160deg, #f0fdfa 0%, #ccfbf1 100%);
  border: 1px solid rgba(13, 148, 136, 0.18);
  border-radius: var(--platform-radius-sm, 8px);
}

.header-title {
  font-size: 16px;
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
  background: rgba(15, 23, 42, 0.04);
  border: 1px solid rgba(15, 23, 42, 0.06);
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
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.8);
  cursor: pointer;
  font: inherit;
  color: inherit;
  transition:
    background 0.2s ease,
    border-color 0.2s ease;
}

.header-user-trigger:hover {
  background: rgba(240, 253, 250, 0.95);
  border-color: rgba(13, 148, 136, 0.22);
}

.header-user-avatar {
  flex-shrink: 0;
}

.header-username {
  max-width: 96px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  color: #334155;
}

.header-user-chevron {
  flex-shrink: 0;
  color: #94a3b8;
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
