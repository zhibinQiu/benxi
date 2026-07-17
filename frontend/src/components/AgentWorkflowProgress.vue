<script setup>
import { computed } from "vue";
import { useI18n } from "../composables/useI18n.js";
import RoseLoader from "./RoseLoader.vue";
import {
  sanitizeWorkflowDisplayText,
} from "../utils/agentWorkflow.js";
import { confirmToolExecution, chooseToolOption } from "../api/chat.js";

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

const emit = defineEmits(["confirm", "reject", "choose"]);

const { t } = useI18n();

const visible = computed(() => {
  if (!props.workflow) return false;
  const hasSteps = (props.workflow.steps?.length ?? 0) > 0;
  const hasTaskSteps = (props.workflow.taskPlan || []).some((task) => (task.steps?.length ?? 0) > 0);
  const hasTasks = (props.workflow.taskPlan?.length ?? 0) > 0;
  const hasCurrent = Boolean(sanitizeWorkflowDisplayText(props.workflow.currentTitle));
  const hasPending = props.workflow.pendingConfirmation?.status === "awaiting";
  const hasChoice = props.workflow.pendingChoice?.status === "awaiting";
  if (props.keepVisibleAfterDone && (hasSteps || hasTasks || hasTaskSteps || hasPending || hasChoice)) return true;
  return props.workflow.running && (hasCurrent || hasSteps || hasTasks || hasTaskSteps || hasPending || hasChoice);
});

const steps = computed(() => props.workflow?.steps || []);
const taskPlan = computed(() => props.workflow?.taskPlan || []);

/* Human-in-the-Loop 确认状态 */
const pendingConfirm = computed(() => {
  const pc = props.workflow?.pendingConfirmation;
  if (!pc) return null;
  return {
    ...pc,
    disabled: pc.status !== "awaiting" || pc.accepting || pc.rejecting,
  };
});

async function onConfirm() {
  const pc = props.workflow?.pendingConfirmation;
  if (!pc || !pc.id || pc.status !== "awaiting") return;
  pc.accepting = true;
  emit("confirm", pc);
  try {
    await confirmToolExecution(pc.id, true);
    pc.status = "accepted";
  } catch (_e) {
    pc.accepting = false;
  }
}

async function onReject() {
  const pc = props.workflow?.pendingConfirmation;
  if (!pc || !pc.id || pc.status !== "awaiting") return;
  pc.rejecting = true;
  emit("reject", pc);
  try {
    await confirmToolExecution(pc.id, false);
    pc.status = "rejected";
  } catch (_e) {
    pc.rejecting = false;
  }
}

/* Human-in-the-Loop 方案选择状态 */
const pendingChoice = computed(() => {
  const pc = props.workflow?.pendingChoice;
  if (!pc) return null;
  return { ...pc, disabled: pc.status !== "awaiting" || pc.choosing };
});

async function onChoose(index) {
  const pc = props.workflow?.pendingChoice;
  if (!pc || !pc.id || pc.status !== "awaiting") return;
  const option = pc.options[index];
  if (!option) return;
  pc.choosing = true;
  emit("choose", { id: pc.id, choice: option });
  try {
    await chooseToolOption(pc.id, option);
    pc.status = "chosen";
    pc.selected = option;
  } catch (_e) {
    pc.choosing = false;
  }
}

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
  const titleText = sanitizeWorkflowDisplayText(step.title) || "";
  if (callText && !titleText.includes(callText)) {
    lines.push({ label: t("agentWorkflow.call"), text: callText });
  }
  if (resultText) {
    lines.push({ label: t("agentWorkflow.result"), text: resultText });
  }
  if (!lines.length && detailText) {
    lines.push({ label: "", text: detailText });
  }
  /* 缓存命中提示 */
  if (step.cached) {
    lines.push({ label: "", text: "（使用缓存结果，无需重复请求）" });
  }
  return lines;
}

/** 工具类型 CSS class */
function toolKindClass(step) {
  if (!step) return "";
  const tool = step.tool || "";
  if (tool.includes("web_search")) return "step-kind--web";
  if (tool.includes("knowledge_retrieve") || tool.includes("retrieve")) return "step-kind--kb";
  if (tool.includes("kg_query") || tool.includes("kg.")) return "step-kind--kg";
  if (tool.includes("skill")) return "step-kind--skill";
  if (tool.includes("planner") || tool.includes("plan")) return "step-kind--plan";
  if (tool.includes("synthesize") || tool.includes("synth")) return "step-kind--synth";
  if (tool.includes("llm")) return "step-kind--llm";
  if (tool.includes("document")) return "step-kind--doc";
  return "";
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

const footerLabel = computed(() => {
  const ft = footerTitle.value;
  if (!ft) return t("agentWorkflow.executing");
  // 如果已有 running 步骤的 title 与 currentTitle 相同，不重复显示
  const runningDup = steps.value.some((s) => s.status === "running" && s.title === ft);
  if (runningDup) return t("agentWorkflow.executing");
  return ft;
});
</script>

<template>
  <div
    v-if="visible"
    class="agent-workflow"
    :class="{ 'agent-workflow--compact': compact }"
    role="status"
    aria-live="polite"
  >
    <div
      v-if="showLiveStatus && footerTitle && !steps.length && !taskPlan.length && !awaitingReply"
      class="agent-workflow__current platform-inline-loading"
    >
      <RoseLoader class="agent-workflow__loader" :size="14" />
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
          <RoseLoader
            v-if="taskStatusIcon(effectiveTaskStatus(task, taskIndex)) === 'spinner'"
            class="agent-workflow__loader"
            :size="14"
          />
          <span v-else-if="taskStatusIcon(effectiveTaskStatus(task, taskIndex)) === 'failed'" class="agent-workflow__check-mark">!</span>
          <span v-else-if="taskStatusIcon(effectiveTaskStatus(task, taskIndex)) === 'done'" class="agent-workflow__check-mark">✓</span>
        </span>
        <div class="agent-workflow__body">
          <div class="agent-workflow__title-row">
            <span v-if="task.agentId" class="agent-workflow__agent-tag">{{ task.agentId }}</span>
            <div class="agent-workflow__title">{{ task.title }}</div>
            <span v-if="task.attempts > 1" class="agent-workflow__attempt-badge" :title="`第${task.attempts}次尝试`">
              重试 {{ task.attempts - 1 }}/{{ task.maxAttempts || 3 }}
            </span>
            <span v-if="task.status === 'failed' && task.lastError" class="agent-workflow__error-tag">
              失败
            </span>
          </div>
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
                <RoseLoader v-if="stepIcon(step, stepIndex, task.steps) === 'spinner'" class="agent-workflow__loader" :size="14" />
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
        :class="[
          `agent-workflow__step--${effectiveStepStatus(step, stepIndex, steps)}`,
          toolKindClass(step),
        ]"
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
          <RoseLoader v-if="stepIcon(step, stepIndex, steps) === 'spinner'" class="agent-workflow__loader" :size="14" />
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
            <div class="agent-workflow__detail agent-workflow__detail--rich">{{ row.text }}</div>
          </template>
        </div>
      </li>
    </ol>

    <div
      v-if="showLiveStatus && showFooterLoading && (steps.length || taskPlan.length || awaitingReply)"
      class="agent-workflow__footer platform-inline-loading"
    >
      <RoseLoader class="agent-workflow__loader" :size="14" />
      <span v-if="workflow.currentAgentTitle" class="agent-workflow__agent-tag">
        {{ workflow.currentAgentTitle }}
      </span>
      <span>{{ footerLabel }}</span>
    </div>

    <!-- Human-in-the-Loop 确认弹窗 -->
    <div
      v-if="pendingConfirm?.status === 'awaiting'"
      class="agent-workflow__confirmation"
    >
      <div class="agent-workflow__confirmation-icon">?</div>
      <div class="agent-workflow__confirmation-body">
        <div class="agent-workflow__confirmation-title">
          需要您确认：{{ pendingConfirm.title }}
        </div>
        <div v-if="pendingConfirm.detail" class="agent-workflow__confirmation-detail">
          {{ pendingConfirm.detail }}
        </div>
        <div class="agent-workflow__confirmation-actions">
          <button
            class="agent-workflow__btn agent-workflow__btn--confirm"
            :disabled="pendingConfirm.disabled"
            @click="onConfirm"
          >
            <RoseLoader v-if="pendingConfirm.accepting" class="agent-workflow__loader" :size="14" />
            <template v-else>确认执行</template>
          </button>
          <button
            class="agent-workflow__btn agent-workflow__btn--reject"
            :disabled="pendingConfirm.disabled"
            @click="onReject"
          >
            <RoseLoader v-if="pendingConfirm.rejecting" class="agent-workflow__loader" :size="14" />
            <template v-else>取消</template>
          </button>
        </div>
      </div>
    </div>
    <div
      v-else-if="pendingConfirm?.status === 'accepted'"
      class="agent-workflow__confirmation agent-workflow__confirmation--done"
    >
      <div class="agent-workflow__confirmation-icon">&#x2713;</div>
      <div class="agent-workflow__confirmation-body">
        <div class="agent-workflow__confirmation-title">已确认：{{ pendingConfirm.title }}</div>
        <div v-if="pendingConfirm.detail" class="agent-workflow__confirmation-detail">
          {{ pendingConfirm.detail }}
        </div>
      </div>
    </div>
    <div
      v-else-if="pendingConfirm?.status === 'rejected'"
      class="agent-workflow__confirmation agent-workflow__confirmation--rejected"
    >
      <div class="agent-workflow__confirmation-icon">&#x2717;</div>
      <div class="agent-workflow__confirmation-body">
        <div class="agent-workflow__confirmation-title">已取消：{{ pendingConfirm.title }}</div>
        <div v-if="pendingConfirm.detail" class="agent-workflow__confirmation-detail">
          {{ pendingConfirm.detail }}
        </div>
      </div>
    </div>

    <!-- Human-in-the-Loop 方案选择 -->
    <div
      v-if="pendingChoice?.status === 'awaiting'"
      class="agent-workflow__choice"
    >
      <div class="agent-workflow__choice-icon">?</div>
      <div class="agent-workflow__choice-body">
        <div class="agent-workflow__choice-question">{{ pendingChoice.question }}</div>
        <div class="agent-workflow__choice-options">
          <button
            v-for="(option, optIndex) in pendingChoice.options"
            :key="optIndex"
            class="agent-workflow__choice-btn"
            :disabled="pendingChoice.choosing"
            @click="onChoose(optIndex)"
          >
            <RoseLoader
              v-if="pendingChoice.choosing"
              class="agent-workflow__loader"
              :size="14"
            />
            <span v-else class="agent-workflow__choice-opt-text">{{ option }}</span>
          </button>
        </div>
      </div>
    </div>
    <div
      v-else-if="pendingChoice?.status === 'chosen'"
      class="agent-workflow__choice agent-workflow__choice--done"
    >
      <div class="agent-workflow__choice-icon">&#x2713;</div>
      <div class="agent-workflow__choice-body">
        <div class="agent-workflow__choice-question">{{ pendingChoice.question }}</div>
        <div class="agent-workflow__choice-result">已选择：{{ pendingChoice.selected }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.agent-workflow {
  margin-bottom: 10px;
  padding: 10px 12px;
  font-size: 12px;
  color: var(--platform-text);
}

.agent-workflow__mode {
  margin-bottom: 8px;
  font-size: 11px;
  letter-spacing: 0.02em;
  color: var(--platform-text-secondary, #64748b);
}

.agent-workflow__current,
.agent-workflow__footer {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
  color: var(--platform-text-secondary, #64748b);
}

.agent-workflow--failed .agent-workflow__current,
.agent-workflow--failed .agent-workflow__footer {
  color: var(--platform-text-secondary, #64748b);
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
  gap: 10px;
}

.agent-workflow__checkbox {
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

.agent-workflow__checkbox--sm {
  width: 18px;
  height: 18px;
  margin-top: 2px;
}

.agent-workflow__checkbox--running {
  animation: awf-pulse 1.6s ease-in-out infinite;
}

.agent-workflow__checkbox--done {
  background: color-mix(in srgb, var(--platform-accent) 12%, transparent);
  color: var(--platform-accent);
}

.agent-workflow__checkbox--failed {
  background: color-mix(in srgb, var(--platform-danger, #ef4444) 12%, transparent);
  color: var(--platform-danger, #ef4444);
}

@keyframes awf-pulse {
  0%, 100% {
    box-shadow: 0 0 0 0 color-mix(in srgb, var(--platform-accent) 20%, transparent);
  }
  50% {
    box-shadow: 0 0 0 4px color-mix(in srgb, var(--platform-accent) 8%, transparent);
  }
}

.agent-workflow__check-mark {
  font-size: 10px;
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--platform-text-secondary, #64748b);
}

.agent-workflow__checkbox--done .agent-workflow__check-mark {
  color: var(--platform-accent);
}

.agent-workflow__checkbox--failed .agent-workflow__check-mark {
  color: var(--platform-danger, #ef4444);
}

.agent-workflow__loader {
  flex-shrink: 0;
  line-height: 0;
}

.agent-workflow__step--failed .agent-workflow__title,
.agent-workflow__substep--failed .agent-workflow__title,
.agent-workflow__step--failed .agent-workflow__detail,
.agent-workflow__substep--failed .agent-workflow__detail {
  color: var(--platform-text-secondary, #64748b);
}

.agent-workflow__step--running .agent-workflow__title,
.agent-workflow__substep--running .agent-workflow__title {
  color: var(--platform-text, #0f172a);
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

.agent-workflow__attempt-badge {
  flex-shrink: 0;
  padding: 0 5px;
  border-radius: 3px;
  font-size: 11px;
  line-height: 1.5;
  color: #f59e0b;
  background: rgba(245, 158, 11, 0.12);
}

.agent-workflow__error-tag {
  flex-shrink: 0;
  padding: 0 5px;
  border-radius: 3px;
  font-size: 11px;
  line-height: 1.5;
  color: var(--platform-danger, #ef4444);
  background: color-mix(in srgb, var(--platform-danger, #ef4444) 10%, transparent);
}

.agent-workflow__agent-tag {
  flex-shrink: 0;
  padding: 1px 7px;
  border-radius: 4px;
  font-size: 10px;
  line-height: 1.5;
  color: var(--platform-accent);
  background: color-mix(in srgb, var(--platform-accent) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--platform-accent) 18%, transparent);
}

.agent-workflow__title {
  font-weight: 400;
  font-size: 11px;
  line-height: 1.35;
  color: var(--platform-text-secondary, #64748b);
}

.agent-workflow__label {
  margin-top: 4px;
  font-size: 10px;
  color: var(--platform-text-secondary, #64748b);
  letter-spacing: 0.02em;
}

.agent-workflow__detail {
  margin-top: 2px;
  font-size: 10px;
  line-height: 1.5;
  color: var(--platform-text-secondary, #64748b);
  word-break: break-word;
  white-space: pre-wrap;
}

/* 正在执行的步骤详情：扫描动效 */
.agent-workflow__step--running .agent-workflow__detail,
.agent-workflow__substep--running .agent-workflow__detail {
  background: linear-gradient(
    to right,
    var(--platform-text-tertiary) 0%,
    var(--platform-text-tertiary) 15%,
    var(--platform-text) 35%,
    var(--platform-text) 55%,
    var(--platform-text-tertiary) 75%,
    var(--platform-text-tertiary) 100%
  );
  background-size: 200% 100%;
  background-clip: text;
  -webkit-background-clip: text;
  color: transparent;
  animation: agent-wf-scan 3s ease-in-out infinite;
}

@keyframes agent-wf-scan {
  0% { background-position: 200% 0%; }
  100% { background-position: -200% 0%; }
}

.agent-workflow__detail--rich {
  padding: 4px 8px;
  margin-top: 4px;
  border-radius: 4px;
  background: color-mix(in srgb, var(--platform-accent) 4%, transparent);
}

/* ── 工具类型统一灰色 ── */

.agent-workflow__footer {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--platform-border, rgba(15, 23, 42, 0.1));
  font-size: 13px;
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
  gap: 10px;
}

.agent-workflow__check-item--done > .agent-workflow__body > .agent-workflow__title {
  color: var(--platform-text-secondary, #64748b);
}

.agent-workflow__check-item--failed > .agent-workflow__body > .agent-workflow__title {
  color: var(--platform-text-secondary, #64748b);
}

.agent-workflow__substeps {
  list-style: none;
  margin: 8px 0 0;
  padding: 0 0 0 4px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  border-left: 2px solid color-mix(in srgb, var(--platform-accent) 15%, transparent);
}

.agent-workflow__substep {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding-left: 8px;
}

/* ── Human-in-the-Loop 确认弹窗 ── */

.agent-workflow__confirmation {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: var(--platform-radius-sm, 8px);
  background: rgba(59, 130, 246, 0.06);
  border: 1px solid rgba(59, 130, 246, 0.2);
}

.agent-workflow__confirmation--done {
  background: rgba(34, 197, 94, 0.06);
  border-color: rgba(34, 197, 94, 0.2);
}

.agent-workflow__confirmation--rejected {
  background: rgba(239, 68, 68, 0.06);
  border-color: rgba(239, 68, 68, 0.2);
}

.agent-workflow__confirmation-icon {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-size: 12px;
  background: rgba(59, 130, 246, 0.15);
  color: #3b82f6;
}

.agent-workflow__confirmation--done .agent-workflow__confirmation-icon {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
}

.agent-workflow__confirmation--rejected .agent-workflow__confirmation-icon {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}

.agent-workflow__confirmation-body {
  flex: 1;
  min-width: 0;
}

.agent-workflow__confirmation-title {
  font-weight: 600;
  font-size: 13px;
  line-height: 1.4;
  color: var(--platform-text, #0f172a);
}

.agent-workflow__confirmation-detail {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--platform-text-secondary, #64748b);
  word-break: break-word;
}

.agent-workflow__confirmation-actions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}

.agent-workflow__btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 16px;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  transition: opacity 0.15s;
  line-height: 1.4;
}

.agent-workflow__btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.agent-workflow__btn--confirm {
  background: #3b82f6;
  color: #fff;
}

.agent-workflow__btn--confirm:hover:not(:disabled) {
  background: #2563eb;
}

.agent-workflow__btn--reject {
  background: rgba(15, 23, 42, 0.06);
  color: var(--platform-text, #0f172a);
}

.agent-workflow__btn--reject:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}

/* ── Human-in-the-Loop 方案选择 ── */

.agent-workflow__choice {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: var(--platform-radius-sm, 8px);
  background: rgba(139, 92, 246, 0.06);
  border: 1px solid rgba(139, 92, 246, 0.2);
}

.agent-workflow__choice--done {
  background: rgba(34, 197, 94, 0.06);
  border-color: rgba(34, 197, 94, 0.2);
}

.agent-workflow__choice-icon {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  margin-top: 1px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-size: 12px;
  background: rgba(139, 92, 246, 0.15);
  color: #8b5cf6;
}

.agent-workflow__choice--done .agent-workflow__choice-icon {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
}

.agent-workflow__choice-body {
  flex: 1;
  min-width: 0;
}

.agent-workflow__choice-question {
  font-size: 13px;
  line-height: 1.5;
  color: var(--platform-text, #0f172a);
  margin-bottom: 8px;
}

.agent-workflow__choice-result {
  margin-top: 4px;
  font-size: 13px;
  color: var(--platform-text-secondary, #64748b);
}

.agent-workflow__choice-options {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.agent-workflow__choice-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 8px 18px;
  border: 1px solid rgba(139, 92, 246, 0.3);
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  line-height: 1.4;
  background: rgba(139, 92, 246, 0.06);
  color: var(--platform-text, #0f172a);
  white-space: nowrap;
}

.agent-workflow__choice-btn:hover:not(:disabled) {
  background: rgba(139, 92, 246, 0.15);
  border-color: #8b5cf6;
}

.agent-workflow__choice-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.agent-workflow__choice-opt-text {
  white-space: nowrap;
}
</style>
