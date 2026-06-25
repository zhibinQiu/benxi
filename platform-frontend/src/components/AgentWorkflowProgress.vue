<script setup>
import { computed } from "vue";
import { useI18n } from "../composables/useI18n.js";
import { sanitizeWorkflowDisplayText } from "../utils/agentWorkflow.js";

const props = defineProps({
  workflow: { type: Object, default: null },
  compact: { type: Boolean, default: false },
  /** 流程结束后仍展示已完成步骤（如流式回答阶段） */
  keepVisibleAfterDone: { type: Boolean, default: false },
});

const { t } = useI18n();

const visible = computed(() => {
  if (!props.workflow) return false;
  const hasSteps = (props.workflow.steps?.length ?? 0) > 0;
  const hasTasks = (props.workflow.taskPlan?.length ?? 0) > 0;
  const hasCurrent = Boolean(sanitizeWorkflowDisplayText(props.workflow.currentTitle));
  if (props.keepVisibleAfterDone && (hasSteps || hasTasks)) return true;
  return props.workflow.running && (hasCurrent || hasSteps || hasTasks);
});

const steps = computed(() => props.workflow?.steps || []);
const taskPlan = computed(() => props.workflow?.taskPlan || []);

function taskStatusIcon(status) {
  if (status === "running") return "spinner";
  if (status === "failed") return "failed";
  if (status === "done") return "done";
  return "pending";
}

function stepIcon(step) {
  if (step.status === "running") return "spinner";
  if (step.status === "failed") return "failed";
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
      v-if="footerTitle && !steps.length && !taskPlan.length"
      class="agent-workflow__current platform-inline-loading"
    >
      <n-spin size="tiny" />
      <span v-if="workflow.currentAgentTitle" class="agent-workflow__agent-tag">
        {{ workflow.currentAgentTitle }}
      </span>
      <span>{{ footerTitle }}</span>
    </div>

    <ul v-if="taskPlan.length" class="agent-workflow__checklist">
      <li
        v-for="task in taskPlan"
        :key="task.id"
        class="agent-workflow__check-item"
        :class="`agent-workflow__check-item--${task.status || 'pending'}`"
      >
        <span class="agent-workflow__marker" aria-hidden="true">
          <n-spin
            v-if="taskStatusIcon(task.status) === 'spinner'"
            size="tiny"
            class="agent-workflow__loader"
          />
          <span v-else-if="taskStatusIcon(task.status) === 'failed'" class="agent-workflow__icon">!</span>
          <span v-else-if="taskStatusIcon(task.status) === 'done'" class="agent-workflow__icon">✓</span>
          <span v-else class="agent-workflow__check-pending">○</span>
        </span>
        <div class="agent-workflow__body">
          <div class="agent-workflow__title">{{ task.title }}</div>
          <div v-if="task.summary" class="agent-workflow__detail">{{ task.summary }}</div>
        </div>
      </li>
    </ul>

    <ol v-if="steps.length" class="agent-workflow__steps">
      <li
        v-for="step in steps"
        :key="step.id"
        class="agent-workflow__step"
        :class="`agent-workflow__step--${step.status}`"
      >
        <span class="agent-workflow__marker" aria-hidden="true">
          <n-spin v-if="stepIcon(step) === 'spinner'" size="tiny" class="agent-workflow__loader" />
          <span v-else-if="stepIcon(step) === 'failed'" class="agent-workflow__icon">!</span>
          <span v-else class="agent-workflow__icon">✓</span>
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
      v-if="workflow.running && footerTitle && (steps.length || taskPlan.length)"
      class="agent-workflow__footer platform-inline-loading"
    >
      <n-spin size="tiny" class="agent-workflow__loader" />
      <span v-if="workflow.currentAgentTitle" class="agent-workflow__agent-tag">
        {{ workflow.currentAgentTitle }}
      </span>
      <span>{{ footerTitle }}</span>
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

.agent-workflow__marker {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 1px;
}

.agent-workflow__loader {
  flex-shrink: 0;
}

.agent-workflow__icon {
  font-size: 11px;
  font-weight: 700;
  color: var(--platform-accent, #18a058);
}

.agent-workflow__step--failed .agent-workflow__icon {
  color: #dc2626;
}

.agent-workflow__step--running .agent-workflow__title {
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
  gap: 8px;
}

.agent-workflow__check-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.agent-workflow__check-item--done .agent-workflow__title {
  color: var(--platform-accent-pressed, #0c7a43);
}

.agent-workflow__check-item--failed .agent-workflow__title {
  color: #b91c1c;
}

.agent-workflow__check-pending {
  font-size: 14px;
  line-height: 1;
  color: var(--platform-text-secondary, #94a3b8);
}
</style>
