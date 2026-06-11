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
import { fetchJobs, fetchNotifications } from "../../api/client";
import AssistantChatFab from "../AssistantChatFab.vue";
import HeaderFlyoutShell from "../HeaderFlyoutShell.vue";
import JobsPanel from "../JobsPanel.vue";
import NotificationsPanel from "../NotificationsPanel.vue";

const route = useRoute();
const router = useRouter();
const { user, logout } = useAuth();
const { isDark, toggleTheme, toggleLocale } = useAppPreferences();
const { t, localeLabel } = useI18n();

const unreadCount = ref(0);
const activeJobCount = ref(0);
const jobsPopoverOpen = ref(false);
const notificationsPopoverOpen = ref(false);
const assistantOpen = ref(false);
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
    activeJobCount.value = (data.items || []).filter((job) =>
      ["pending", "running"].includes(job.status),
    ).length;
  } catch {
    activeJobCount.value = 0;
  }
}

async function refreshHeaderBadges() {
  await Promise.all([refreshUnreadCount(), refreshActiveJobCount()]);
}

function closeAllFlyouts() {
  jobsPopoverOpen.value = false;
  notificationsPopoverOpen.value = false;
  assistantOpen.value = false;
}

function toggleAssistant() {
  closeAllFlyouts();
  assistantOpen.value = !assistantOpen.value;
}

function toggleJobsPopover() {
  notificationsPopoverOpen.value = false;
  assistantOpen.value = false;
  jobsPopoverOpen.value = !jobsPopoverOpen.value;
}

function toggleNotificationsPopover() {
  jobsPopoverOpen.value = false;
  assistantOpen.value = false;
  notificationsPopoverOpen.value = !notificationsPopoverOpen.value;
}

function goTodos() {
  closeAllFlyouts();
  router.push({ name: "todos" });
}

const userDisplayName = computed(
  () => user.value?.display_name || user.value?.username || t("userMenu.defaultName"),
);

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
    logout();
    router.push({ name: "login" });
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
      <n-button
        quaternary
        circle
        size="small"
        class="header-icon-btn"
        :class="{ 'header-icon-btn--active': route.name === 'todos' }"
        :aria-label="t('header.todos')"
        @click.stop="goTodos"
      >
        <n-icon :size="18" :component="ListOutline" />
      </n-button>
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
      <n-button
        ref="assistantTriggerRef"
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
    </div>
    <n-dropdown
      trigger="click"
      placement="bottom-end"
      to="body"
      :z-index="10000"
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
