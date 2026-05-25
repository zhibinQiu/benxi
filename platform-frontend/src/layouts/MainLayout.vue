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
} from "@vicons/ionicons5";
import { NIcon } from "naive-ui";
import { useAuth } from "../composables/useAuth";
import { resolveFeatureIcon } from "../constants/featureIcons";
import { PLATFORM_APP_NAME } from "../constants/platform";
import { fetchNotifications } from "../api/client";
import AssistantChatFab from "../components/AssistantChatFab.vue";

const route = useRoute();
const router = useRouter();
const { user, loadUser, logout, hasPerm } = useAuth();

const SETTINGS_KEY = "system-settings";
const expandedKeys = ref([]);

const unreadCount = ref(0);

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
      label: "文档库",
      key: "documents",
      icon: () => h(NIcon, null, { default: () => h(DocumentTextOutline) }),
    },
    {
      label: "任务中心",
      key: "jobs",
      icon: () => h(NIcon, null, { default: () => h(TimeOutline) }),
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

const knowflowNative = computed(() => Boolean(route.meta?.knowflowNative));

const showAssistant = computed(
  () => route.name !== "login" && !route.meta?.public
);

const activeKey = computed(() => {
  if (route.name === "document-detail") return "documents";
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
  return String(route.name || "system-functions");
});

const fullHeightPage = computed(() => Boolean(route.meta?.fullHeight));

const headerTitle = computed(() => String(route.meta?.title || "").trim());

const headerIcon = computed(() => resolveFeatureIcon(route.meta?.featureIcon));

const showAppTitle = computed(
  () => !knowflowNative.value && !headerTitle.value
);

const contentStyle = computed(() => {
  if (knowflowNative.value || route.meta?.fullEmbed) {
    return "padding: 0; height: 100vh; overflow: hidden";
  }
  if (fullHeightPage.value) {
    return "padding: 8px 12px; height: calc(100vh - 52px); overflow: hidden; box-sizing: border-box";
  }
  return "padding: 20px 24px";
});

function ensureSettingsExpanded() {
  if (
    route.name === "admin-users" ||
    route.name === "admin-departments" ||
    route.name === "admin-monitor" ||
    route.name === "admin-model-settings"
  ) {
    if (!expandedKeys.value.includes(SETTINGS_KEY)) {
      expandedKeys.value = [...expandedKeys.value, SETTINGS_KEY];
    }
  }
}

watch(() => route.name, ensureSettingsExpanded, { immediate: true });

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
    documents: "/documents",
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
  <n-layout class="app-shell" :has-sider="!knowflowNative">
    <n-layout-sider
      v-if="!knowflowNative"
      class="app-sider"
      bordered
      collapse-mode="width"
      :collapsed-width="64"
      :width="220"
      show-trigger
    >
      <div class="sider-inner">
        <div class="brand">
          <img src="/logo.svg" alt="" class="brand-logo" />
          <span>{{ PLATFORM_APP_NAME }}</span>
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
      <n-layout-header v-if="!knowflowNative" bordered class="header">
        <n-space align="center" justify="space-between" style="width: 100%">
          <n-space align="center" :size="10" class="header-title-wrap">
            <div v-if="headerIcon" class="header-feature-icon">
              <n-icon :size="22" :component="headerIcon" />
            </div>
            <n-text v-if="headerTitle && !knowflowNative" strong class="header-title">
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
            { 'app-view-host--full': fullHeightPage || knowflowNative },
          ]"
        >
          <router-view />
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
.header-feature-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--n-text-color);
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
