<script setup>
import { computed } from "vue";
import RoseLoader from "./RoseLoader.vue";
import { useI18n } from "../composables/useI18n.js";
import {
  getWorkflowDoneSegments,
  getWorkflowRunningSegment,
  getWorkflowFullDetails,
  sanitizeWorkflowDisplayText,
} from "../utils/agentWorkflow.js";

const props = defineProps({
  workflow: { type: Object, default: null },
});

const { t } = useI18n();

const doneSegments = computed(() => getWorkflowDoneSegments(props.workflow));
const runningSegment = computed(() => getWorkflowRunningSegment(props.workflow));

const visible = computed(() => {
  if (!props.workflow) return false;
  return (
    props.workflow.running ||
    doneSegments.value.length > 0 ||
    Boolean(runningSegment.value)
  );
});

function segmentAgentTitle(step) {
  return String(step?.agentTitle || "").trim();
}
function segmentPrimaryText(step) {
  return sanitizeWorkflowDisplayText(step.title) || "";
}

function runningAgentTitle() {
  return String(
    runningSegment.value?.agentTitle || props.workflow?.currentAgentTitle || ""
  ).trim();
}

function runningTitleText() {
  const segment = runningSegment.value;
  if (!segment) {
    return sanitizeWorkflowDisplayText(props.workflow?.currentTitle) || t("agentWorkflow.executing");
  }
  return segmentPrimaryText(segment) || t("agentWorkflow.executing");
}

function runningLiveContent() {
  const segment = runningSegment.value;
  if (!segment) return "";
  const details = getWorkflowFullDetails(segment);
  const title = segmentPrimaryText(segment);
  const live = details.primary;
  if (live && live !== title) return live;
  return "";
}

function segmentDetail(step) {
  const details = getWorkflowFullDetails(step);
  return details.primary || "";
}

/** 动画用延迟偏移 */
function doneStyle(index) {
  return { "--done-delay": `${index * 0.08}s` };
}
</script>

<template>
  <div
    v-if="visible"
    class="aw-c"
    role="status"
    aria-live="polite"
  >
    <!-- 已完成步骤（渐入动画） -->
    <div v-if="doneSegments.length" class="aw-c__done">
      <div
        v-for="(segment, segmentIndex) in doneSegments"
        :key="segment.id || `d-${segmentIndex}`"
        class="aw-c__step aw-c__step--done"
        :style="doneStyle(segmentIndex)"
      >
        <span class="aw-c__icon" aria-hidden="true">
          <svg class="aw-c__icon-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="20 6 9 17 4 12" />
          </svg>
        </span>
        <div class="aw-c__body">
          <div class="aw-c__title-row">
            <span v-if="segmentAgentTitle(segment)" class="aw-c__agent-tag">
              {{ segmentAgentTitle(segment) }}
            </span>
            <span class="aw-c__title">{{ segmentPrimaryText(segment) }}</span>
          </div>
          <div v-if="segmentDetail(segment)" class="aw-c__detail">
            {{ segmentDetail(segment) }}
          </div>
        </div>
      </div>
    </div>

    <!-- 当前正在执行的步骤（脉冲动画 + 实时详情） -->
    <div
      v-if="runningSegment"
      class="aw-c__running"
      :class="{ 'aw-c__running--solo': !doneSegments.length }"
    >
      <div v-if="doneSegments.length" class="aw-c__divider"></div>
      <div class="aw-c__step aw-c__step--active">
        <span class="aw-c__icon aw-c__icon--pulse" aria-hidden="true">
          <RoseLoader :size="14" />
        </span>
        <div class="aw-c__body">
          <div class="aw-c__title-row">
            <span v-if="runningAgentTitle()" class="aw-c__agent-tag">
              {{ runningAgentTitle() }}
            </span>
            <span class="aw-c__title aw-c__title--running">{{ runningTitleText() }}</span>
          </div>
          <div
            v-if="runningLiveContent()"
            class="aw-c__live"
          >
            <span class="aw-c__live-text">{{ runningLiveContent() }}</span>
            <span class="aw-c__live-cursor"></span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.aw-c {
  margin-bottom: 12px;
  font-size: 15px;
}

/* ── 已完成步骤 ── */
.aw-c__done {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.aw-c__step--done {
  animation: aw-c-done-in 0.35s ease-out both;
  animation-delay: var(--done-delay, 0s);
}

@keyframes aw-c-done-in {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.aw-c__step {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

/* ── 图标 ── */
.aw-c__icon {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  margin-top: 1px;
  border-radius: 999px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--platform-accent) 12%, transparent);
  color: var(--platform-accent);
  transition: background 0.2s, color 0.2s;
}

.aw-c__icon-check {
  width: 12px;
  height: 12px;
}

.aw-c__icon--pulse {
  background: color-mix(in srgb, var(--platform-accent) 10%, transparent);
  animation: aw-c-pulse 1.6s ease-in-out infinite;
}

@keyframes aw-c-pulse {
  0%, 100% {
    box-shadow: 0 0 0 0 color-mix(in srgb, var(--platform-accent) 20%, transparent);
  }
  50% {
    box-shadow: 0 0 0 4px color-mix(in srgb, var(--platform-accent) 8%, transparent);
  }
}

/* ── 步骤主体 ── */
.aw-c__body {
  min-width: 0;
  flex: 1;
}

.aw-c__title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px;
}

.aw-c__title {
  font-weight: 500;
  line-height: 1.5;
  font-size: 14px;
  color: var(--platform-text-secondary, #64748b);
}

.aw-c__title--running {
  color: var(--platform-text, #0f172a);
  font-weight: 600;
}

/* ── Agent 标签 ── */
.aw-c__agent-tag {
  flex-shrink: 0;
  padding: 1px 7px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  line-height: 1.5;
  color: var(--platform-accent);
  background: color-mix(in srgb, var(--platform-accent) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--platform-accent) 18%, transparent);
}

/* ── 已完成步骤的 secondary detail ── */
.aw-c__detail {
  margin-top: 2px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--platform-text-tertiary, #94a3b8);
  word-break: break-word;
}

/* ── 实时详情（运行步骤） ── */
.aw-c__live {
  margin-top: 4px;
  padding-left: 10px;
  border-left: 2px solid var(--platform-accent);
  font-size: 13px;
  line-height: 1.5;
  color: var(--platform-text-secondary, #64748b);
  word-break: break-word;
  white-space: pre-wrap;
  display: flex;
  align-items: baseline;
  gap: 2px;
}

.aw-c__live-text {
  flex: 1;
}

.aw-c__live-cursor {
  flex-shrink: 0;
  display: inline-block;
  width: 2px;
  height: 14px;
  background: var(--platform-accent);
  animation: aw-c-blink 1s step-end infinite;
  vertical-align: text-bottom;
}

@keyframes aw-c-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

/* ── 当前正在执行区域 ── */
.aw-c__running {
  margin-top: 8px;
  padding-top: 8px;
}

.aw-c__running--solo {
  margin-top: 0;
  padding-top: 0;
}

.aw-c__divider {
  height: 1px;
  background: linear-gradient(
    to right,
    color-mix(in srgb, var(--platform-border) 60%, transparent),
    color-mix(in srgb, var(--platform-border) 20%, transparent)
  );
  margin: 0 0 8px;
}
</style>
