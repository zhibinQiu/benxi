<script setup>
import { computed, h, onMounted } from "vue";
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
} from "@vicons/ionicons5";
import { NIcon } from "naive-ui";
import { useAuth } from "../composables/useAuth";

const route = useRoute();
const router = useRouter();
const { user, loadUser, logout, hasPerm } = useAuth();

onMounted(() => loadUser());

const menuOptions = computed(() => {
  const items = [
    {
      label: "文档库",
      key: "documents",
      icon: () => h(NIcon, null, { default: () => h(DocumentTextOutline) }),
    },
    {
      label: "系统功能",
      key: "system-functions",
      icon: () => h(NIcon, null, { default: () => h(GridOutline) }),
    },
    {
      label: "任务中心",
      key: "jobs",
      icon: () => h(NIcon, null, { default: () => h(TimeOutline) }),
    },
    {
      label: "消息",
      key: "notifications",
      icon: () => h(NIcon, null, { default: () => h(NotificationsOutline) }),
    },
  ];
  if (hasPerm("admin.user")) {
    items.push({
      label: "用户管理",
      key: "admin-users",
      icon: () => h(NIcon, null, { default: () => h(PeopleOutline) }),
    });
  }
  if (hasPerm("admin.dept")) {
    items.push({
      label: "部门管理",
      key: "admin-departments",
      icon: () => h(NIcon, null, { default: () => h(BusinessOutline) }),
    });
  }
  return items;
});

const activeKey = computed(() => {
  if (route.name === "document-detail") return "documents";
  if (route.name === "translate") return "system-functions";
  return String(route.name || "documents");
});

function onMenuSelect(key) {
  const map = {
    documents: "/documents",
    "system-functions": "/system/functions",
    jobs: "/jobs",
    notifications: "/notifications",
    "admin-users": "/admin/users",
    "admin-departments": "/admin/departments",
  };
  router.push(map[key] || "/documents");
}

function doLogout() {
  logout();
  router.push({ name: "login" });
}
</script>

<template>
  <n-layout has-sider style="min-height: 100vh">
    <n-layout-sider
      bordered
      collapse-mode="width"
      :collapsed-width="64"
      :width="220"
      show-trigger
      content-style="padding: 12px 0"
    >
      <div class="brand">文档平台</div>
      <n-menu
        :value="activeKey"
        :options="menuOptions"
        @update:value="onMenuSelect"
      />
    </n-layout-sider>
    <n-layout>
      <n-layout-header bordered class="header">
        <n-space align="center" justify="space-between" style="width: 100%">
          <n-text depth="2">{{ route.meta?.title || "文档平台" }}</n-text>
          <n-space align="center">
            <n-avatar round size="small">{{ user?.display_name?.[0] || "U" }}</n-avatar>
            <n-text>{{ user?.display_name || user?.username }}</n-text>
            <n-button quaternary size="small" @click="doLogout">
              <template #icon>
                <n-icon :component="LogOutOutline" />
              </template>
              退出
            </n-button>
          </n-space>
        </n-space>
      </n-layout-header>
      <n-layout-content content-style="padding: 24px">
        <router-view />
      </n-layout-content>
    </n-layout>
  </n-layout>
</template>

<style scoped>
.brand {
  font-weight: 600;
  font-size: 1.05rem;
  padding: 8px 20px 16px;
  color: #1a1a2e;
}
.header {
  padding: 0 24px;
  height: 56px;
  display: flex;
  align-items: center;
}
</style>
