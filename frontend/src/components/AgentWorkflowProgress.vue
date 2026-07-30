<script setup>
import { computed } from "vue";
import { NIcon } from "naive-ui";
import { useI18n } from "../composables/useI18n.js";
import RoseLoader from "./RoseLoader.vue";
import { confirmToolExecution, chooseToolOption } from "../api/chat.js";
import {
  scrubThinkingDisplayText,
  resolveAgentDisplayName,
  workflowRunningTasks,
} from "../utils/agentWorkflow.js";
import {
  agentBadgeStyle,
  agentRoleLabel,
  resolveAgentCardIcon,
} from "../utils/agentDisplay.js";

const props = defineProps({
  workflow: { type: Object, default: null },
  keepVisibleAfterDone: { type: Boolean, default: false },
});

const emit = defineEmits(["confirm", "reject", "choose"]);
const { t } = useI18n();

const running = computed(() => props.workflow?.running ?? false);
const summary = computed(() => props.workflow?.summary || "");
const stage = computed(() => props.workflow?.stage || "");
const activeAgentId = computed(() => String(props.workflow?.activeAgentId || "").trim());
const activeAgent = computed(() =>
  resolveAgentDisplayName(
    activeAgentId.value,
    props.workflow?.activeAgentTitle,
  ),
);
const liveThinking = computed(() =>
  scrubThinkingDisplayText(props.workflow?.liveThinking || ""),
);
const parallelTasks = computed(() => workflowRunningTasks(props.workflow));
const showParallel = computed(() => parallelTasks.value.length > 1);

function taskAgentLabel(task) {
  return resolveAgentDisplayName(task?.agentId, task?.agentTitle);
}

function taskAgentId(task) {
  return String(task?.agentId || "").trim();
}

const visible = computed(() => {
  if (!props.workflow) return false;
  if (running.value) return true;
  if (props.workflow.failed) return true;
  if (props.workflow.pendingConfirmation || props.workflow.pendingChoice) return true;
  if (props.keepVisibleAfterDone && (summary.value || liveThinking.value)) return true;
  return false;
});

const showLiveStatus = computed(() => running.value || Boolean(liveThinking.value));

const pendingConfirm = computed(() => {
  const pc = props.workflow?.pendingConfirmation;
  if (!pc) return null;
  return { ...pc, disabled: pc.status !== "awaiting" || pc.accepting || pc.rejecting };
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
</script>

<template>
  <div v-if="visible" class="aw" role="status" aria-live="polite">
    <div v-if="showLiveStatus" class="aw__main">
      <RoseLoader v-if="running" class="aw__loader" :size="24" :rotation-duration="12000" />
      <div class="aw__body">
        <div v-if="running || summary" class="aw__status" :data-stage="stage">
          <span
            v-if="activeAgent"
            class="aw__agent"
            :data-agent="activeAgentId || 'unknown'"
            :style="agentBadgeStyle(activeAgentId)"
          >
            <NIcon class="aw__agent-icon" :size="13" :component="resolveAgentCardIcon(activeAgentId)" />
            <span class="aw__agent-role">{{ agentRoleLabel(activeAgentId) }}</span>
            <span class="aw__agent-name">{{ activeAgent }}</span>
          </span>
          <span>{{ summary || t("agentWorkflow.executing") }}</span>
        </div>
        <ul v-if="showParallel" class="aw__parallel" aria-label="并行执行">
          <li
            v-for="(task, idx) in parallelTasks"
            :key="task.id || idx"
            class="aw__parallel-item"
          >
            <span class="aw__parallel-dot" aria-hidden="true" />
            <span
              v-if="taskAgentLabel(task)"
              class="aw__agent aw__agent--inline"
              :data-agent="taskAgentId(task) || 'unknown'"
              :style="agentBadgeStyle(taskAgentId(task))"
            >
              <NIcon class="aw__agent-icon" :size="12" :component="resolveAgentCardIcon(taskAgentId(task))" />
              <span class="aw__agent-role">{{ agentRoleLabel(taskAgentId(task)) }}</span>
              <span class="aw__agent-name">{{ taskAgentLabel(task) }}</span>
            </span>
            <span>{{ task.title }}</span>
          </li>
        </ul>
        <div v-if="liveThinking" class="aw__thinking">{{ liveThinking }}</div>
      </div>
    </div>

    <div v-if="pendingConfirm?.status === 'awaiting'" class="aw__hitl">
      <div class="aw__hitl-icon">?</div>
      <div class="aw__hitl-body">
        <div class="aw__hitl-title">需要您确认：{{ pendingConfirm.title }}</div>
        <div v-if="pendingConfirm.detail" class="aw__hitl-detail">{{ pendingConfirm.detail }}</div>
        <div class="aw__hitl-actions">
          <button class="aw__btn aw__btn--confirm" :disabled="pendingConfirm.disabled" @click="onConfirm">
            <RoseLoader v-if="pendingConfirm.accepting" class="aw__btn-loader" :size="16" />
            <template v-else>确认执行</template>
          </button>
          <button class="aw__btn aw__btn--reject" :disabled="pendingConfirm.disabled" @click="onReject">取消</button>
        </div>
      </div>
    </div>
    <div v-else-if="pendingConfirm?.status === 'accepted'" class="aw__hitl aw__hitl--done">
      <div class="aw__hitl-icon aw__hitl-icon--done">&#x2713;</div>
      <div class="aw__hitl-body"><div class="aw__hitl-title">已确认：{{ pendingConfirm.title }}</div></div>
    </div>
    <div v-else-if="pendingConfirm?.status === 'rejected'" class="aw__hitl aw__hitl--rejected">
      <div class="aw__hitl-icon aw__hitl-icon--rejected">&#x2717;</div>
      <div class="aw__hitl-body"><div class="aw__hitl-title">已取消：{{ pendingConfirm.title }}</div></div>
    </div>

    <div v-if="pendingChoice?.status === 'awaiting'" class="aw__choice">
      <div class="aw__choice-icon">?</div>
      <div class="aw__choice-body">
        <div class="aw__choice-question">{{ pendingChoice.question }}</div>
        <div class="aw__choice-options">
          <button
            v-for="(opt, idx) in pendingChoice.options"
            :key="idx"
            class="aw__btn aw__btn--choice"
            :disabled="pendingChoice.disabled"
            @click="onChoose(idx)"
          >{{ opt }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.aw { display: flex; flex-direction: column; gap: 10px; margin: 4px 0 10px; }
.aw__main { display: flex; align-items: flex-start; gap: 10px; min-height: 28px; }
.aw__loader { flex: 0 0 auto; margin-top: 2px; }
.aw__body { flex: 1; min-width: 0; }
.aw__status { color: var(--n-text-color); font-size: 15px; font-weight: 500; line-height: 1.4; display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px; }
.aw__agent {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 8px 2px 6px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.4;
  color: var(--card-accent, var(--n-primary-color));
  background: var(--card-accent-soft, color-mix(in srgb, var(--n-primary-color) 12%, transparent));
  border: 1px solid color-mix(in srgb, var(--card-accent, var(--n-primary-color)) 28%, transparent);
  flex: 0 0 auto;
  max-width: 100%;
}
.aw__agent-icon {
  flex: 0 0 auto;
  opacity: 0.95;
}
.aw__agent-role {
  flex: 0 0 auto;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.02em;
  padding: 0 5px;
  border-radius: 999px;
  color: #fff;
  background: var(--card-accent, var(--n-primary-color));
  line-height: 1.5;
}
.aw__agent-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.aw__agent--inline {
  padding: 1px 6px 1px 4px;
  font-size: 11px;
  gap: 4px;
}
.aw__agent--inline .aw__agent-role {
  font-size: 9px;
  padding: 0 4px;
}
.aw__parallel { list-style: none; margin: 8px 0 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.aw__parallel-item { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--n-text-color-2); line-height: 1.35; }
.aw__parallel-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--n-primary-color); flex: 0 0 auto; animation: aw-pulse 1.2s ease-in-out infinite; }
@keyframes aw-pulse { 0%, 100% { opacity: 0.45; } 50% { opacity: 1; } }
.aw__thinking {
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.65;
  color: var(--n-text-color-3, #64748b);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: normal;
  font-family: inherit;
  max-height: none;
  overflow: visible;
}
.aw__hitl, .aw__choice { display: flex; gap: 10px; padding: 12px 14px; border-radius: 10px; background: var(--n-color-embedded, rgba(0,0,0,0.03)); border: 1px solid var(--n-border-color); }
.aw__hitl-icon, .aw__choice-icon { width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center; font-size: 13px; font-weight: 700; background: var(--n-primary-color); color: #fff; flex: 0 0 auto; }
.aw__hitl-icon--done { background: #18a058; }
.aw__hitl-icon--rejected { background: #d03050; }
.aw__hitl-body, .aw__choice-body { flex: 1; min-width: 0; }
.aw__hitl-title, .aw__choice-question { font-size: 14px; font-weight: 500; margin-bottom: 6px; }
.aw__hitl-detail { font-size: 12px; color: var(--n-text-color-3); margin-bottom: 8px; }
.aw__hitl-actions, .aw__choice-options { display: flex; flex-wrap: wrap; gap: 8px; }
.aw__btn { border: 1px solid var(--n-border-color); background: var(--n-color); border-radius: 8px; padding: 6px 12px; font-size: 13px; cursor: pointer; }
.aw__btn:disabled { opacity: 0.6; cursor: not-allowed; }
.aw__btn--confirm { background: var(--n-primary-color); border-color: var(--n-primary-color); color: #fff; }
.aw__btn--reject { color: var(--n-text-color-2); }
.aw__btn--choice:hover:not(:disabled) { border-color: var(--n-primary-color); }
.aw__btn-loader { display: inline-block; vertical-align: middle; }
</style>
