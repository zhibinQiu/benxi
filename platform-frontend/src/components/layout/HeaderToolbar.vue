<script setup>
import { computed, h, onMounted, onUnmounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  NAvatar,
  NBadge,
  NButton,
  NDropdown,
  NIcon } from "naive-ui";
import {
  ChatbubbleEllipsesOutline,
  ChevronDownOutline,
  LanguageOutline,
  ListOutline,
  LogOutOutline,
  MoonOutline,
  NotificationsOutline,
  PersonOutline,
  SunnyOutline,
  TimeOutline } from "@vicons/ionicons5";
import { useAuth } from "../../composables/useAuth";
import { useAppPreferences } from "../../composables/useAppPreferences";
import { useI18n } from "../../composables/useI18n";
import { fetchJobs, fetchNotifications, fetchTodos } from "../../api/client";
import { PLATFORM_Z } from "../../constants/zIndex.js";
import AssistantChatFab from "../AssistantChatFab.vue";
import HeaderFlyoutShell from "../HeaderFlyoutShell.vue";
import JobsPanel from "../JobsPanel.vue";
import NotificationsPanel from "../NotificationsPanel.vue";
import TodosPanel from "../TodosPanel.vue";

const route = useRoute();
const router = useRouter();
const { displayName, logout } = useAuth();
const { isDark, toggleTheme, toggleLocale } = useAppPreferences();
const { t, localeLabel } = useI18n();

const unreadCount = ref(0);
const activeJobCount = ref(0);
const pendingTodoCount = ref(0);
const todosPopoverOpen = ref(false);
const jobsPopoverOpen = ref(false);
const notificationsPopoverOpen = ref(false);
const assistantOpen = ref(false);
const todosTriggerRef = ref(null);
const jobsTriggerRef = ref(null);
const notificationsTriggerRef = ref(null);
const assistantTriggerRef = ref(null);
const flyoutsReady = ref(false);
let badgeTimer = null;

onMounted(() => {
  flyoutsReady.value = true;
  refreshHeaderBadges();
  badgeTimer = setInterval(() => {
    if (document.hidden) return;
    refreshHeaderBadges();
  }, 60_000);
});

onUnmounted(() => {
  if (badgeTimer) clearInterval(badgeTimer);
});

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
    activeJobCount.value = (data.items || []).filter(
      (job) =>
        (job.progress ?? 0) < 100 &&
        job.status !== "done" &&
        (["pending", "running"].includes(job.status) ||
          (job.type === "document_index" && Boolean(job.payload?.awaiting_parse)))
    ).length;
  } catch {
    activeJobCount.value = 0;
  }
}

async function refreshPendingTodoCount() {
  try {
    const data = await fetchTodos("pending");
    pendingTodoCount.value = Array.isArray(data) ? data.length : 0;
  } catch {
    pendingTodoCount.value = 0;
  }
}

async function refreshHeaderBadges() {
  await Promise.all([refreshUnreadCount(), refreshActiveJobCount(), refreshPendingTodoCount()]);
}

function closeAllFlyouts() {
  todosPopoverOpen.value = false;
  jobsPopoverOpen.value = false;
  notificationsPopoverOpen.value = false;
  assistantOpen.value = false;
}

function toggleFlyout(target) {
  const next = !target.value;
  closeAllFlyouts();
  target.value = next;
}

function toggleTodosPopover() {
  toggleFlyout(todosPopoverOpen);
}

function toggleJobsPopover() {
  toggleFlyout(jobsPopoverOpen);
}

function toggleNotificationsPopover() {
  toggleFlyout(notificationsPopoverOpen);
}

function toggleAssistant() {
  toggleFlyout(assistantOpen);
}

const userDisplayName = computed(() => displayName());

const userMenuOptions = computed(() => [
  {
    label: t("userMenu.profile"),
    key: "profile",
    icon: () => h(NIcon, null, { default: () => h(PersonOutline) })},
  { type: "divider", key: "divider-prefs" },
  {
    label: isDark.value ? t("userMenu.lightMode") : t("userMenu.darkMode"),
    key: "theme",
    icon: () =>
      h(NIcon, null, {
        default: () => h(isDark.value ? SunnyOutline : MoonOutline)})},
  {
    label: localeLabel.value,
    key: "locale",
    icon: () => h(NIcon, null, { default: () => h(LanguageOutline) })},
  { type: "divider", key: "divider-logout" },
  {
    label: t("userMenu.logout"),
    key: "logout",
    icon: () => h(NIcon, null, { default: () => h(LogOutOutline) })},
]);

function headerShellMenuProps() {
  return { class: "header-shell-menu" };
}

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
    closeAllFlyouts();
    logout();
  }
}

function renderUserMenuOption({ node, option }) {
  if (option.type === "divider") return node;
  if (option.key === "logout") {
    return h("div", { class: "platform-dropdown-option--danger" }, node);
  }
  return node;
}

defineExpose({ refreshHeaderBadges, closeAllFlyouts });
</script>

<template>
  <div class="header-actions">
    <div class="header-toolbar">
      <span ref="todosTriggerRef" class="header-icon-wrap">
        <n-button
          quaternary
          circle
          size="small"
          class="header-icon-btn"
          :class="{ 'header-icon-btn--active': todosPopoverOpen || route.name === 'todos' }"
          :aria-label="t('header.todos')"
          @click.stop="toggleTodosPopover"
        >
          <n-icon :size="18" :component="ListOutline" />
        </n-button>
        <n-badge
          v-if="pendingTodoCount > 0"
          class="header-icon-wrap__badge"
          :value="pendingTodoCount"
          :max="99"
        />
      </span>
      <span ref="jobsTriggerRef" class="header-icon-wrap">
        <n-button
          quaternary
          circle
          size="small"
          class="header-icon-btn"
          :class="{ 'header-icon-btn--active': jobsPopoverOpen || route.name === 'jobs' }"
          :aria-label="t('header.jobs')"
          @click.stop="toggleJobsPopover"
        >
          <n-icon :size="18" :component="TimeOutline" />
        </n-button>
        <n-badge
          v-if="activeJobCount > 0"
          class="header-icon-wrap__badge"
          :value="activeJobCount"
          :max="99"
        />
      </span>
      <span ref="notificationsTriggerRef" class="header-icon-wrap">
        <n-button
          quaternary
          circle
          size="small"
          class="header-icon-btn"
          :class="{
            'header-icon-btn--active': notificationsPopoverOpen}"
          :aria-label="t('header.notifications')"
          @click.stop="toggleNotificationsPopover"
        >
          <n-icon :size="18" :component="NotificationsOutline" />
        </n-button>
        <n-badge
          v-if="unreadCount > 0"
          class="header-icon-wrap__badge"
          :value="unreadCount"
          :max="99"
        />
      </span>
      <span ref="assistantTriggerRef" class="header-icon-wrap">
        <n-button
          quaternary
          circle
          size="small"
          class="header-icon-btn"
          :class="{ 'header-icon-btn--active': assistantOpen }"
          :aria-label="t('header.assistant')"
          @click.stop="toggleAssistant"
        >
          <n-icon :size="18" :component="ChatbubbleEllipsesOutline" />
        </n-button>
      </span>
    </div>
    <n-dropdown
      trigger="click"
      placement="bottom-end"
      to="body"
      :z-index="PLATFORM_Z.dropdown"
      :options="userMenuOptions"
      :render-option="renderUserMenuOption"
      :menu-props="headerShellMenuProps"
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

    <template v-if="flyoutsReady">
      <HeaderFlyoutShell
        v-model:show="todosPopoverOpen"
        :anchor-el="todosTriggerRef"
        width="min(560px, calc(100vw - 32px))"
        aria-label="待办事项"
      >
        <TodosPanel
          variant="popover"
          :active="todosPopoverOpen"
          @updated="refreshPendingTodoCount"
          @navigate="todosPopoverOpen = false"
        />
      </HeaderFlyoutShell>
      <HeaderFlyoutShell
        v-model:show="jobsPopoverOpen"
        :anchor-el="jobsTriggerRef"
        aria-label="后台任务"
      >
        <JobsPanel
          variant="popover"
          :active="jobsPopoverOpen"
          @updated="refreshActiveJobCount"
          @navigate="jobsPopoverOpen = false"
        />
      </HeaderFlyoutShell>
      <HeaderFlyoutShell
        v-model:show="notificationsPopoverOpen"
        :anchor-el="notificationsTriggerRef"
        aria-label="通知"
      >
        <NotificationsPanel
          :active="notificationsPopoverOpen"
          @updated="refreshUnreadCount"
          @navigate="notificationsPopoverOpen = false"
        />
      </HeaderFlyoutShell>
      <AssistantChatFab
        v-model:open="assistantOpen"
        :anchor-el="assistantTriggerRef"
      />
    </template>
  </div>
</template>

<style scoped>
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
  border-radius: var(--platform-radius-sm);
  position: relative;
  z-index: 2;
}

.header-icon-btn {
  width: 32px;
  height: 32px;
  position: relative;
  z-index: 1;
}

.header-icon-wrap {
  position: relative;
  display: inline-flex;
  vertical-align: middle;
}

.header-icon-wrap__badge {
  position: absolute;
  top: -2px;
  right: -2px;
  pointer-events: none;
  z-index: 2;
}

.header-user-trigger {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  max-width: 180px;
  padding: 4px 10px 4px 4px;
  border: none;
  background: transparent;
  border-radius: var(--platform-radius-pill);
  cursor: pointer;
  font: inherit;
  color: inherit;
  transition:
    opacity var(--platform-duration-smooth) ease,
    border-color var(--platform-duration-smooth) ease;
}

.header-user-trigger:hover {
  opacity: 0.92;
}

.header-user-trigger:active {
  opacity: 0.82;
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
</style>
