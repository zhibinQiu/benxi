<script setup>
import { defineAsyncComponent, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import {
  NBadge,
  NButton,
  NIcon } from "naive-ui";
import { TimeOutline } from "@vicons/ionicons5";
import { fetchJobs } from "../../api/client";
import HeaderFlyoutShell from "../HeaderFlyoutShell.vue";

const JobsPanel = defineAsyncComponent(() => import("../JobsPanel.vue"));

const route = useRoute();
const activeJobCount = ref(0);
const jobsPopoverOpen = ref(false);
const jobsTriggerRef = ref(null);
const flyoutsReady = ref(false);
const jobsPanelMounted = ref(false);
const isMobile = ref(window.innerWidth < 768);
let badgeTimer = null;
let jobsUnmountTimer = null;

const FLYOUT_UNMOUNT_DELAY_MS = 320;

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
  jobsUnmountTimer = null;
  jobsPanelMounted.value = false;
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
});

onUnmounted(() => {
  if (badgeTimer) clearInterval(badgeTimer);
  releaseFlyoutPanels();
  window.removeEventListener("resize", onViewportResize);
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

defineExpose({ refreshHeaderBadges: refreshActiveJobCount, closeAllFlyouts });
</script>

<template>
  <div class="header-actions">
    <div class="header-toolbar">
      <span ref="jobsTriggerRef" class="header-icon-wrap">
        <n-button
          quaternary
          circle
          size="small"
          class="header-icon-btn"
          :class="{ 'header-icon-btn--active': jobsPopoverOpen || route.name === 'jobs' }"
          :aria-label="'后台任务'"
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
  padding: 4px;
  border-radius: var(--platform-radius-sm);
  position: relative;
  z-index: 2;
}

.header-icon-btn {
  width: 32px;
  height: 32px;
  position: relative;
  z-index: 1;
  color: var(--platform-icon);
}

.header-icon-wrap {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
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

@media (max-width: 768px) {
  .header-actions :deep(.n-dropdown-menu) {
    max-width: calc(100vw - 24px);
    min-width: 140px;
  }
}
</style>
