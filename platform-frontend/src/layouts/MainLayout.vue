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
  LibraryOutline,
  GitNetworkOutline,
  ArrowBackOutline,
} from "@vicons/ionicons5";
import { NIcon } from "naive-ui";
import { useAuth } from "../composables/useAuth";
import { resolveFeatureIcon } from "../constants/featureIcons";
import { PLATFORM_APP_NAME } from "../constants/platform";
import { fetchNotifications } from "../api/client";
import AssistantChatFab from "../components/AssistantChatFab.vue";
import { consumeSkipInnerRouteMotion } from "../utils/routeTransition";

const route = useRoute();
const router = useRouter();
const { user, loadUser, logout, hasPerm } = useAuth();

const innerRouteTransition = ref(
  consumeSkipInnerRouteMotion() ? "route-instant" : "route-fade",
);

const SETTINGS_KEY = "system-settings";
const KNOWLEDGE_CENTER_KEY = "knowledge-center";
const expandedKeys = ref([]);

const unreadCount = ref(0);
const siderCollapsed = ref(false);

async function refreshUnreadCount() {
  try {
    const data = await fetchNotifications({ page: 1, page_size: 1, unread_only: true });
    unreadCount.value = data.total ?? 0;
  } catch {
    unreadCount.value = 0;
  }
}

onMounted(async () => {
  await loadUser();
  refreshUnreadCount();
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
      label: "系统功能",
      key: "system-functions",
      icon: () => h(NIcon, null, { default: () => h(GridOutline) }),
    },
    {
      label: "待办事项",
      key: "todos",
      icon: () => h(NIcon, null, { default: () => h(ListOutline) }),
    },
    {
      label: "后台任务",
      key: "jobs",
      icon: () => h(NIcon, null, { default: () => h(TimeOutline) }),
    },
    {
      label: "知识中心",
      key: KNOWLEDGE_CENTER_KEY,
      icon: () => h(NIcon, null, { default: () => h(LibraryOutline) }),
      children: [
        {
          label: "文档库",
          key: "documents",
          icon: () => h(NIcon, null, { default: () => h(DocumentTextOutline) }),
        },
        {
          label: "知识图谱",
          key: "knowledge-graph",
          icon: () => h(NIcon, null, { default: () => h(GitNetworkOutline) }),
        },
      ],
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
  "smart-forecast",
  "speech",
  "ocr",
  "compare",
  "assist-writing",
  "knowledge-graph",
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
  if (route.name === "knowledge-graph") return "knowledge-graph";
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
  router.push({ name: "system-functions" });
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
    route.name === "documents" ||
    route.name === "document-detail" ||
    route.name === "knowledge-graph"
  ) {
    if (!keys.includes(KNOWLEDGE_CENTER_KEY)) keys.push(KNOWLEDGE_CENTER_KEY);
  }
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
    if (name && name !== "login") refreshUnreadCount();
  }
);

function onExpandedKeysUpdate(keys) {
  expandedKeys.value = keys;
}

function onMenuSelect(key) {
  const map = {
    "ai-home": "/ai-home",
    documents: "/documents",
    "knowledge-graph": "/knowledge-graph",
    "system-functions": "/system/functions",
    jobs: "/jobs",
    notifications: "/notifications",
    todos: "/todos",
    "admin-users": "/admin/users",
    "admin-departments": "/admin/departments",
    "admin-monitor": "/admin/monitor",
    "admin-model-settings": "/admin/model-settings",
  };
  if (map[key]) router.push(map[key]);
}

function goNotifications() {
  router.push({ name: "notifications" });
}

function doLogout() {
  logout();
  router.push({ name: "login" });
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
          <img src="/logo.svg" alt="" class="brand-logo" />
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
          <n-space align="center" :size="8" class="header-actions">
            <n-avatar round size="small">{{ user?.username?.[0] || "U" }}</n-avatar>
            <n-text class="header-username">{{ user?.username }}</n-text>
            <n-badge :value="unreadCount" :max="99" :show="unreadCount > 0">
              <n-button
                quaternary
                size="small"
                :type="route.name === 'notifications' ? 'primary' : 'default'"
                aria-label="消息"
                @click="goNotifications"
              >
                <template #icon>
                  <n-icon :component="NotificationsOutline" />
                </template>
                消息
              </n-button>
            </n-badge>
            <n-button quaternary size="small" @click="doLogout">
              <template #icon>
                <n-icon :component="LogOutOutline" />
              </template>
              退出
            </n-button>
          </n-space>
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
}
.header-username {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
