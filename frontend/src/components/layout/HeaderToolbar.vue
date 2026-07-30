<script setup>
import { computed, defineAsyncComponent, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import {
  NAvatar,
  NBadge,
  NButton,
  NDropdown,
  NIcon,
} from "naive-ui";
import { TimeOutline, NotificationsOutline } from "@vicons/ionicons5";
import { fetchJobs } from "../../api/client";
import HeaderFlyoutShell from "../HeaderFlyoutShell.vue";
import { useAuth } from "../../composables/useAuth";
import { useAppPreferences } from "../../composables/useAppPreferences";
import { useNotificationAlerts } from "../../composables/useNotificationAlerts.js";
import { PLATFORM_JOBS_REFRESH_EVENT } from "../../constants/platformEvents.js";

const JobsPanel = defineAsyncComponent(() => import("../JobsPanel.vue"));
const NotificationsPanel = defineAsyncComponent(() => import("../NotificationsPanel.vue"));

const route = useRoute();
const { user, displayName, logout } = useAuth();
const { toggleTheme, toggleLocale, locale, isDark } = useAppPreferences();
const { unreadCount, refreshNotificationAlerts } = useNotificationAlerts();

const activeJobCount = ref(0);
const jobsPopoverOpen = ref(false);
const notifPopoverOpen = ref(false);
const jobsTriggerRef = ref(null);
const notifTriggerRef = ref(null);
const flyoutsReady = ref(false);
const jobsPanelMounted = ref(false);
const notifPanelMounted = ref(false);
const userMenuOpen = ref(false);
const isMobile = ref(window.innerWidth < 768);
let badgeTimer = null;
let jobsUnmountTimer = null;
let notifUnmountTimer = null;

const FLYOUT_UNMOUNT_DELAY_MS = 320;

const userDisplayName = computed(() => {
  const d = displayName();
  return d || user.value?.nickname || user.value?.phone || "";
});

const roleLabel = computed(() => {
  const u = user.value;
  if (!u) return "";
  if (u.role === "admin" || u.is_system_admin) return "管理员";
  if (u.role === "manager") return "经理";
  return "成员";
});

const userMenuOptions = computed(() => [
  {
    label: "偏好设置",
    key: "preferences-group",
    children: [
      {
        label: locale.value === "zh" ? "English" : "中文",
        key: "toggle_locale",
      },
      {
        label: isDark.value ? "日间模式" : "夜间模式",
        key: "toggle_theme",
      },
    ],
  },
  {
    label: "退出登录",
    key: "logout",
  },
]);

function clearFlyoutUnmountTimer(timer) {
  if (timer) clearTimeout(timer);
}

function scheduleFlyoutUnmount(openRef, mountedRef, setTimer) {
  setTimer(
    setTimeout(() => {
      setTimer(null);
      if (!openRef.value) mountedRef.value = false;
    }, FLYOUT_UNMOUNT_DELAY_MS)
  );
}

function releaseFlyoutPanels() {
  clearFlyoutUnmountTimer(jobsUnmountTimer);
  clearFlyoutUnmountTimer(notifUnmountTimer);
  jobsUnmountTimer = null;
  notifUnmountTimer = null;
  jobsPanelMounted.value = false;
  notifPanelMounted.value = false;
}

watch(jobsPopoverOpen, (open) => {
  if (open) {
    clearFlyoutUnmountTimer(jobsUnmountTimer);
    jobsUnmountTimer = null;
    jobsPanelMounted.value = true;
    return;
  }
  clearFlyoutUnmountTimer(jobsUnmountTimer);
  scheduleFlyoutUnmount(jobsPopoverOpen, jobsPanelMounted, (timer) => {
    jobsUnmountTimer = timer;
  });
});

watch(notifPopoverOpen, (open) => {
  if (open) {
    clearFlyoutUnmountTimer(notifUnmountTimer);
    notifUnmountTimer = null;
    notifPanelMounted.value = true;
    return;
  }
  clearFlyoutUnmountTimer(notifUnmountTimer);
  scheduleFlyoutUnmount(notifPopoverOpen, notifPanelMounted, (timer) => {
    notifUnmountTimer = timer;
  });
});

onMounted(() => {
  flyoutsReady.value = true;
  const scheduleBadges = () => {
    void refreshActiveJobCount();
  };
  if (typeof requestIdleCallback === "function") {
    requestIdleCallback(scheduleBadges, { timeout: 2500 });
  } else {
    setTimeout(scheduleBadges, 1200);
  }
  badgeTimer = setInterval(() => {
    if (!document.hidden) refreshActiveJobCount();
  }, 15_000);
  window.addEventListener("resize", onViewportResize, { passive: true });
  window.addEventListener(PLATFORM_JOBS_REFRESH_EVENT, onJobsRefreshEvent);
});

function onJobsRefreshEvent() {
  void refreshActiveJobCount();
  jobsPopoverOpen.value = true;
}

onUnmounted(() => {
  if (badgeTimer) clearInterval(badgeTimer);
  releaseFlyoutPanels();
  window.removeEventListener("resize", onViewportResize);
  window.removeEventListener(PLATFORM_JOBS_REFRESH_EVENT, onJobsRefreshEvent);
});

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

function closeAllFlyouts({ releasePanels = false } = {}) {
  jobsPopoverOpen.value = false;
  notifPopoverOpen.value = false;
  if (releasePanels) releaseFlyoutPanels();
}

function onViewportResize() {
  isMobile.value = window.innerWidth < 768;
}

function toggleFlyout(target) {
  const next = !target.value;
  closeAllFlyouts();
  target.value = next;
}

function toggleJobsPopover() {
  toggleFlyout(jobsPopoverOpen);
}

function toggleNotifPopover() {
  toggleFlyout(notifPopoverOpen);
}

function onUserMenuSelect(key) {
  userMenuOpen.value = false;
  if (key === "toggle_locale") {
    toggleLocale();
  } else if (key === "toggle_theme") {
    toggleTheme();
  } else if (key === "logout") {
    logout();
  }
}

defineExpose({ refreshHeaderBadges: refreshActiveJobCount, closeAllFlyouts });
</script>

<template>
  <div class="header-actions">
    <div class="header-toolbar">
      <span ref="jobsTriggerRef" class="header-icon-wrap">
        <n-button
          quaternary
          circle
          size="tiny"
          class="header-icon-btn"
          :class="{ 'header-icon-btn--active': jobsPopoverOpen || route.name === 'jobs' }"
          :aria-label="'后台任务'"
          @click.stop="toggleJobsPopover"
        >
          <n-icon :size="16" :component="TimeOutline" />
        </n-button>
        <n-badge
          v-if="activeJobCount > 0"
          class="header-icon-wrap__badge"
          :value="activeJobCount"
          :max="99"
        />
      </span>

      <span ref="notifTriggerRef" class="header-icon-wrap">
        <n-button
          quaternary
          circle
          size="tiny"
          class="header-icon-btn"
          :class="{ 'header-icon-btn--active': notifPopoverOpen || route.name === 'notifications' }"
          :aria-label="'消息'"
          @click.stop="toggleNotifPopover"
        >
          <n-icon :size="16" :component="NotificationsOutline" />
        </n-button>
        <n-badge
          v-if="unreadCount > 0"
          class="header-icon-wrap__badge"
          :value="unreadCount"
          :max="99"
        />
      </span>

      <div class="header-user">
        <n-dropdown
          trigger="click"
          placement="bottom-end"
          to="body"
          :z-index="1050"
          :options="userMenuOptions"
          @update:show="(v) => (userMenuOpen = v)"
          @select="onUserMenuSelect"
        >
          <button type="button" class="header-user__trigger" :aria-label="userDisplayName || '用户菜单'">
            <n-avatar round size="small" class="header-user__avatar">
              {{ (userDisplayName || "U")[0] }}
            </n-avatar>
            <span class="header-user__meta">
              <span class="header-user__name">{{ userDisplayName }}</span>
              <span v-if="!isMobile && roleLabel" class="header-user__role">{{ roleLabel }}</span>
            </span>
          </button>
        </n-dropdown>
      </div>
    </div>

    <template v-if="flyoutsReady">
      <HeaderFlyoutShell
        v-if="jobsPanelMounted"
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
        v-if="notifPanelMounted"
        v-model:show="notifPopoverOpen"
        :anchor-el="notifTriggerRef"
        aria-label="消息"
      >
        <NotificationsPanel
          :active="notifPopoverOpen"
          @updated="refreshNotificationAlerts"
          @navigate="notifPopoverOpen = false"
          @close="notifPopoverOpen = false"
        />
      </HeaderFlyoutShell>
    </template>
  </div>
</template>

<style scoped>
.header-actions {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 12px;
  margin-left: auto;
}

.header-toolbar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 2px;
  border-radius: var(--platform-radius-sm);
  position: relative;
  z-index: 2;
}

.header-icon-btn {
  width: 26px !important;
  height: 26px !important;
  min-width: 26px !important;
  min-height: 26px !important;
  padding: 0 !important;
  position: relative;
  z-index: 1;
  color: var(--platform-icon);
  --n-height: 26px !important;
  --n-icon-size: 16px !important;
}

.header-icon-btn :deep(.n-icon) {
  font-size: 16px !important;
  width: 16px !important;
  height: 16px !important;
}

.header-icon-wrap {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  vertical-align: middle;
  flex-shrink: 0;
}

.header-icon-wrap__badge {
  position: absolute;
  top: -2px;
  right: -2px;
  pointer-events: none;
  z-index: 2;
}

.header-user {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding-left: 4px;
  border-left: 1px solid var(--platform-border, rgba(0, 0, 0, 0.08));
}

.header-user__trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  max-width: 160px;
  padding: 0;
  margin: 0;
  border: none;
  background: transparent;
  cursor: pointer;
  text-align: left;
}

.header-user__avatar {
  flex-shrink: 0;
  width: 28px !important;
  height: 28px !important;
  background: var(--platform-accent, #005A9E) !important;
  color: #fff !important;
  font-size: 11px;
  font-weight: 600;
}

.header-user__meta {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0;
  min-width: 0;
  line-height: 1.25;
  max-width: 120px;
}

.header-user__trigger:hover .header-user__name {
  color: var(--platform-accent, #005A9E);
}

.header-user__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  font-weight: 500;
  color: var(--platform-text);
  max-width: 100%;
}

.header-user__role {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 10px;
  color: var(--platform-text-tertiary);
  max-width: 100%;
}

@media (max-width: 768px) {
  .header-actions :deep(.n-dropdown-menu) {
    max-width: calc(100vw - 24px);
    min-width: 140px;
  }

  .header-user {
    gap: 4px;
    padding-left: 2px;
    border-left: none;
  }

  .header-user__trigger {
    max-width: 120px;
  }

  .header-user__meta {
    max-width: 88px;
  }
}
</style>
