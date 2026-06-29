<script setup>
import { computed } from "vue";
import { useI18n } from "../composables/useI18n.js";
import { sanitizeWorkflowDisplayText } from "../utils/agentWorkflow.js";

const props = defineProps({
  workflow: { type: Object, default: null },
  compact: { type: Boolean, default: false },
  /** 流程结束后仍展示已完成步骤（如流式回答阶段） */
  keepVisibleAfterDone: { type: Boolean, default: false },
  /** 流程已结束或步骤间空档，仍在等待正文流式输出 */
  awaitingReply: { type: Boolean, default: false },
  /** 为 false 时不展示顶部/底部「当前步骤」行（由父级回答区承接） */
  showLiveStatus: { type: Boolean, default: true },
});

const { t } = useI18n();

const visible = computed(() => {
  if (!props.workflow) return false;
  const hasSteps = (props.workflow.steps?.length ?? 0) > 0;
  const hasTaskSteps = (props.workflow.taskPlan || []).some((task) => (task.steps?.length ?? 0) > 0);
  const hasTasks = (props.workflow.taskPlan?.length ?? 0) > 0;
  const hasCurrent = Boolean(sanitizeWorkflowDisplayText(props.workflow.currentTitle));
  if (props.keepVisibleAfterDone && (hasSteps || hasTasks || hasTaskSteps)) return true;
  return props.workflow.running && (hasCurrent || hasSteps || hasTasks || hasTaskSteps);
});

const steps = computed(() => props.workflow?.steps || []);
const taskPlan = computed(() => props.workflow?.taskPlan || []);

const executionModeLabel = computed(() => {
  const mode = props.workflow?.executionMode;
  if (mode === "parallel") return t("agentWorkflow.executionMode.parallel");
  if (mode === "sequential") return t("agentWorkflow.executionMode.sequential");
  return "";
});

const isParallelMode = computed(() => props.workflow?.executionMode === "parallel");

function effectiveTaskStatus(task, taskIndex) {
  const status = task.status || "pending";
  if (isParallelMode.value) return status;
  if (status === "done" || status === "failed") return status;
  const firstActive = taskPlan.value.findIndex(
    (item) => item.status === "running" || item.status === "pending"
  );
  if (status === "running" && taskIndex === firstActive) return "running";
  if (taskIndex > firstActive) return "pending";
  return status;
}

function effectiveStepStatus(step, stepIndex, stepList) {
  const status = step.status || "pending";
  if (isParallelMode.value || !props.workflow?.running) return status;
  const firstOpen = stepList.findIndex(
    (item) => item.status !== "done" && item.status !== "failed"
  );
  if (status === "done" || status === "failed") return status;
  if (stepIndex === firstOpen && status === "running") return "running";
  if (stepIndex > firstOpen) return "pending";
  return status;
}

function taskStatusIcon(status) {
  if (status === "running") return "spinner";
  if (status === "failed") return "failed";
  if (status === "done") return "done";
  return "pending";
}

function stepIcon(step, stepIndex, stepList) {
  const status = effectiveStepStatus(step, stepIndex, stepList);
  if (status === "running") return "spinner";
  if (status === "failed") return "failed";
  if (status === "pending") return "pending";
  return "done";
}

function stepBody(step) {
  const lines = [];
  const callText = sanitizeWorkflowDisplayText(step.callDetail);
  const resultText = sanitizeWorkflowDisplayText(step.resultDetail);
  const detailText = sanitizeWorkflowDisplayText(step.detail);
  if (callText) {
    lines.push({ label: t("agentWorkflow.call"), text: callText });
  }
  if (resultText) {
    lines.push({ label: t("agentWorkflow.result"), text: resultText });
  }
  if (!lines.length && detailText) {
    lines.push({ label: "", text: detailText });
  }
  return lines;
}

const footerTitle = computed(() =>
  sanitizeWorkflowDisplayText(props.workflow?.currentTitle || "")
);

const showFooterLoading = computed(() => {
  if (props.awaitingReply) return true;
  if (!props.workflow?.running) return false;
  const hasRunningStep = steps.value.some((s) => s.status === "running");
  const hasRunningTask = taskPlan.value.some((item) => item.status === "running");
  const hasRunningNested = taskPlan.value.some((item) =>
    (item.steps || []).some((s) => s.status === "running")
  );
  if (hasRunningStep || hasRunningTask || hasRunningNested) return true;
  if (footerTitle.value) return true;
  return false;
});

const footerLabel = computed(() => footerTitle.value || t("agentWorkflow.executing"));
</script>

<template>
  <div
    v-if="visible"
    class="agent-workflow"
    :class="{ 'agent-workflow--compact': compact, 'agent-workflow--failed': workflow.failed }"
    role="status"
    aria-live="polite"
  >
    <div
      v-if="showLiveStatus && footerTitle && !steps.length && !taskPlan.length"
      class="agent-workflow__current platform-inline-loading"
    >
      <n-spin size="tiny" />
      <span v-if="workflow.currentAgentTitle" class="agent-workflow__agent-tag">
        {{ workflow.currentAgentTitle }}
      </span>
      <span>{{ footerTitle }}</span>
    </div>

    <div v-if="executionModeLabel && taskPlan.length" class="agent-workflow__mode">
      {{ executionModeLabel }}
    </div>

    <ul v-if="taskPlan.length" class="agent-workflow__checklist">
      <li
        v-for="(task, taskIndex) in taskPlan"
        :key="task.id"
        class="agent-workflow__check-item"
        :class="`agent-workflow__check-item--${effectiveTaskStatus(task, taskIndex)}`"
      >
        <span
          class="agent-workflow__checkbox"
          :class="{
            'agent-workflow__checkbox--running': taskStatusIcon(effectiveTaskStatus(task, taskIndex)) === 'spinner',
            'agent-workflow__checkbox--done': taskStatusIcon(effectiveTaskStatus(task, taskIndex)) === 'done',
            'agent-workflow__checkbox--failed': taskStatusIcon(effectiveTaskStatus(task, taskIndex)) === 'failed',
          }"
          aria-hidden="true"
        >
          <n-spin
            v-if="taskStatusIcon(effectiveTaskStatus(task, taskIndex)) === 'spinner'"
            size="tiny"
            class="agent-workflow__loader"
          />
          <span v-else-if="taskStatusIcon(effectiveTaskStatus(task, taskIndex)) === 'failed'" class="agent-workflow__check-mark">!</span>
          <span v-else-if="taskStatusIcon(effectiveTaskStatus(task, taskIndex)) === 'done'" class="agent-workflow__check-mark">✓</span>
        </span>
        <div class="agent-workflow__body">
          <div class="agent-workflow__title">{{ task.title }}</div>
          <div v-if="task.summary" class="agent-workflow__detail">{{ task.summary }}</div>
          <ol v-if="task.steps?.length" class="agent-workflow__substeps">
            <li
              v-for="(step, stepIndex) in task.steps"
              :key="step.id"
              class="agent-workflow__substep"
              :class="`agent-workflow__substep--${effectiveStepStatus(step, stepIndex, task.steps)}`"
            >
              <span
                class="agent-workflow__checkbox agent-workflow__checkbox--sm"
                :class="{
                  'agent-workflow__checkbox--running': stepIcon(step, stepIndex, task.steps) === 'spinner',
                  'agent-workflow__checkbox--done': stepIcon(step, stepIndex, task.steps) === 'done',
                  'agent-workflow__checkbox--failed': stepIcon(step, stepIndex, task.steps) === 'failed',
                }"
                aria-hidden="true"
              >
                <n-spin v-if="stepIcon(step, stepIndex, task.steps) === 'spinner'" size="tiny" class="agent-workflow__loader" />
                <span v-else-if="stepIcon(step, stepIndex, task.steps) === 'failed'" class="agent-workflow__check-mark">!</span>
                <span v-else-if="stepIcon(step, stepIndex, task.steps) === 'done'" class="agent-workflow__check-mark">✓</span>
              </span>
              <div class="agent-workflow__body">
                <div class="agent-workflow__title-row">
                  <span v-if="step.agentTitle" class="agent-workflow__agent-tag">{{ step.agentTitle }}</span>
                  <div class="agent-workflow__title">{{ step.title }}</div>
                </div>
                <template v-for="(row, idx) in stepBody(step)" :key="idx">
                  <div v-if="row.label" class="agent-workflow__label">{{ row.label }}</div>
                  <div class="agent-workflow__detail">{{ row.text }}</div>
                </template>
              </div>
            </li>
          </ol>
        </div>
      </li>
    </ul>

    <ol v-if="steps.length" class="agent-workflow__steps">
      <li
        v-for="(step, stepIndex) in steps"
        :key="step.id"
        class="agent-workflow__step"
        :class="`agent-workflow__step--${effectiveStepStatus(step, stepIndex, steps)}`"
      >
        <span
          class="agent-workflow__checkbox"
          :class="{
            'agent-workflow__checkbox--running': stepIcon(step, stepIndex, steps) === 'spinner',
            'agent-workflow__checkbox--done': stepIcon(step, stepIndex, steps) === 'done',
            'agent-workflow__checkbox--failed': stepIcon(step, stepIndex, steps) === 'failed',
          }"
          aria-hidden="true"
        >
          <n-spin v-if="stepIcon(step, stepIndex, steps) === 'spinner'" size="tiny" class="agent-workflow__loader" />
          <span v-else-if="stepIcon(step, stepIndex, steps) === 'failed'" class="agent-workflow__check-mark">!</span>
          <span v-else-if="stepIcon(step, stepIndex, steps) === 'done'" class="agent-workflow__check-mark">✓</span>
        </span>
        <div class="agent-workflow__body">
          <div class="agent-workflow__title-row">
            <span v-if="step.agentTitle" class="agent-workflow__agent-tag">{{ step.agentTitle }}</span>
            <div class="agent-workflow__title">{{ step.title }}</div>
          </div>
          <template v-for="(row, idx) in stepBody(step)" :key="idx">
            <div v-if="row.label" class="agent-workflow__label">{{ row.label }}</div>
            <div class="agent-workflow__detail">{{ row.text }}</div>
          </template>
        </div>
      </li>
    </ol>

    <div
      v-if="showLiveStatus && showFooterLoading && (steps.length || taskPlan.length || awaitingReply)"
      class="agent-workflow__footer platform-inline-loading"
    >
      <n-spin size="tiny" class="agent-workflow__loader" />
      <span v-if="workflow.currentAgentTitle" class="agent-workflow__agent-tag">
        {{ workflow.currentAgentTitle }}
      </span>
      <span>{{ footerLabel }}</span>
    </div>
  </div>
</template>

<style scoped>
.agent-workflow {
  margin-bottom: 10px;
  padding: 10px 12px;
  border-radius: var(--platform-radius-sm, 8px);
  background: var(--platform-accent-gradient-soft, rgba(24, 160, 88, 0.06));
  border: 1px dashed var(--platform-accent-border-soft, rgba(24, 160, 88, 0.25));
  font-size: 13px;
  color: var(--platform-text);
}

.agent-workflow--failed {
  border-color: rgba(239, 68, 68, 0.35);
  background: rgba(254, 242, 242, 0.5);
}

.agent-workflow__mode {
  margin-bottom: 8px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--platform-text-secondary, #64748b);
}

.agent-workflow__current,
.agent-workflow__footer {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
  color: var(--platform-accent-pressed, #0c7a43);
}

.agent-workflow--failed .agent-workflow__current,
.agent-workflow--failed .agent-workflow__footer {
  color: #b91c1c;
}

.agent-workflow__steps {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.agent-workflow__step {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.agent-workflow__checkbox {
  flex-shrink: 0;
  width: 16px;
  height: 16px;
  margin-top: 2px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1.5px solid var(--platform-text-secondary, #94a3b8);
  border-radius: 3px;
  background: var(--platform-surface, #fff);
}

.agent-workflow__checkbox--sm {
  width: 14px;
  height: 14px;
  margin-top: 3px;
}

.agent-workflow__checkbox--running {
  border-color: var(--platform-accent, #18a058);
}

.agent-workflow__checkbox--done {
  border-color: var(--platform-accent, #18a058);
  background: rgba(24, 160, 88, 0.08);
}

.agent-workflow__checkbox--failed {
  border-color: #dc2626;
  background: rgba(254, 242, 242, 0.8);
}

.agent-workflow__check-mark {
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
  color: var(--platform-accent, #18a058);
}

.agent-workflow__checkbox--failed .agent-workflow__check-mark {
  color: #dc2626;
}

.agent-workflow__loader {
  flex-shrink: 0;
}

.agent-workflow__step--failed .agent-workflow__title,
.agent-workflow__substep--failed .agent-workflow__title {
  color: #b91c1c;
}

.agent-workflow__step--running .agent-workflow__title,
.agent-workflow__substep--running .agent-workflow__title {
  color: var(--platform-accent-pressed, #0c7a43);
}

.agent-workflow__body {
  min-width: 0;
  flex: 1;
}

.agent-workflow__title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.agent-workflow__agent-tag {
  flex-shrink: 0;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  line-height: 1.4;
  color: var(--platform-accent-pressed, #0c7a43);
  background: rgba(24, 160, 88, 0.12);
}

.agent-workflow__title {
  font-weight: 500;
  line-height: 1.35;
}

.agent-workflow__label {
  margin-top: 4px;
  font-size: 11px;
  font-weight: 600;
  color: var(--platform-text-secondary, #64748b);
  letter-spacing: 0.02em;
}

.agent-workflow__detail {
  margin-top: 2px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--platform-text-secondary, #64748b);
  word-break: break-word;
  white-space: pre-wrap;
}

.agent-workflow__footer {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--platform-accent-border-soft, rgba(24, 160, 88, 0.2));
  font-size: 12px;
}

.agent-workflow--compact {
  padding: 8px 10px;
}

.agent-workflow__checklist {
  list-style: none;
  margin: 0 0 10px;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.agent-workflow__check-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.agent-workflow__check-item--done > .agent-workflow__body > .agent-workflow__title {
  color: var(--platform-accent-pressed, #0c7a43);
}

.agent-workflow__check-item--failed > .agent-workflow__body > .agent-workflow__title {
  color: #b91c1c;
}

.agent-workflow__substeps {
  list-style: none;
  margin: 8px 0 0;
  padding: 0 0 0 4px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  border-left: 2px solid var(--platform-accent-border-soft, rgba(24, 160, 88, 0.15));
}

.agent-workflow__substep {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding-left: 8px;
}
</style>
