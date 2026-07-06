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

/** 运行步骤的标题文字 */
function runningTitleText() {
  const segment = runningSegment.value;
  if (!segment) {
    return sanitizeWorkflowDisplayText(props.workflow?.currentTitle) || t("agentWorkflow.executing");
  }
  return segmentPrimaryText(segment) || t("agentWorkflow.executing");
}

/** 运行步骤的实时详情内容（与标题不同时显示） */
function runningLiveContent() {
  const segment = runningSegment.value;
  if (!segment) return "";
  const details = getWorkflowFullDetails(segment);
  const title = segmentPrimaryText(segment);
  const live = details.primary;
  if (live && live !== title) return live;
  return "";
}
</script>

<template>
  <div
    v-if="visible"
    class="agent-workflow"
    role="status"
    aria-live="polite"
  >
    <!-- 已完成步骤列表 -->
    <div v-if="doneSegments.length" class="agent-workflow__steps">
      <div
        v-for="(segment, segmentIndex) in doneSegments"
        :key="segment.id || `done-${segmentIndex}`"
        class="agent-workflow__step"
      >
        <span class="agent-workflow__icon" aria-hidden="true">
          <span class="agent-workflow__icon-mark">{{
            segment.status === "failed" ? "!" : "✓"
          }}</span>
        </span>
        <div class="agent-workflow__body">
          <div class="agent-workflow__title-row">
            <span v-if="segmentAgentTitle(segment)" class="agent-workflow__agent-tag">
              {{ segmentAgentTitle(segment) }}
            </span>
            <span class="agent-workflow__title">{{ segmentPrimaryText(segment) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 当前正在执行的步骤 -->
    <div
      v-if="runningSegment"
      class="agent-workflow__running"
      :class="{ 'agent-workflow__running--solo': !doneSegments.length }"
    >
      <div v-if="doneSegments.length" class="agent-workflow__divider"></div>
      <div class="agent-workflow__step agent-workflow__step--active">
        <span class="agent-workflow__icon agent-workflow__icon--running" aria-hidden="true">
          <RoseLoader :size="14" />
        </span>
        <div class="agent-workflow__body">
          <div class="agent-workflow__title-row">
            <span v-if="runningAgentTitle()" class="agent-workflow__agent-tag">
              {{ runningAgentTitle() }}
            </span>
            <span class="agent-workflow__title agent-workflow__title--running">{{ runningTitleText() }}</span>
          </div>
          <div
            v-if="runningLiveContent()"
            class="agent-workflow__live-detail"
          >
            {{ runningLiveContent() }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.agent-workflow {
  margin-bottom: 10px;
  padding: 8px 10px;
  font-size: 15px;
  color: var(--platform-text);
}

/* ── 已完成步骤列表 ── */
.agent-workflow__steps {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.agent-workflow__step {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

/* ── 步骤图标（扁平方框） ── */
.agent-workflow__icon {
  flex-shrink: 0;
  width: 16px;
  height: 16px;
  margin-top: 2px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--platform-text-tertiary, #94a3b8);
  border-radius: 0;
  background: transparent;
}

.agent-workflow__icon--running {
  border-color: var(--platform-text-tertiary, #94a3b8);
  background: transparent;
  border-radius: 0;
  line-height: 0;
}

.agent-workflow__icon-mark {
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
  color: var(--platform-text-secondary, #64748b);
}

/* ── 步骤主体 ── */
.agent-workflow__body {
  min-width: 0;
  flex: 1;
}

.agent-workflow__title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px;
}

.agent-workflow__title {
  font-weight: 500;
  line-height: 1.4;
  font-size: 14.5px;
  color: var(--platform-text-secondary, #64748b);
}

.agent-workflow__title--running {
  color: var(--platform-text, #0f172a);
}

/* ── 智能体标签 ── */
.agent-workflow__agent-tag {
  flex-shrink: 0;
  padding: 1px 6px;
  border: 1px solid var(--platform-border, #e2e8f0);
  border-radius: 0;
  font-size: 11px;
  font-weight: 600;
  line-height: 1.4;
  color: var(--platform-text-secondary, #64748b);
  background: transparent;
}

/* ── 实时详情（运行步骤） ── */
.agent-workflow__live-detail {
  margin-top: 4px;
  padding: 4px 0 2px;
  padding-left: 8px;
  border-left: 1px solid var(--platform-border, #e2e8f0);
  font-size: 13px;
  line-height: 1.5;
  color: var(--platform-text-secondary, #64748b);
  word-break: break-word;
  white-space: pre-wrap;
}

/* ── 当前正在执行区域 ── */
.agent-workflow__running {
  margin-top: 6px;
  padding-top: 6px;
}

.agent-workflow__running--solo {
  margin-top: 0;
  padding-top: 0;
}

.agent-workflow__divider {
  height: 1px;
  width: 60%;
  min-width: 480px;
  background: var(--platform-border, #e2e8f0);
  margin: 0 0 6px;
}

.agent-workflow__step--active .agent-workflow__title-row {
  gap: 6px;
}
</style>
