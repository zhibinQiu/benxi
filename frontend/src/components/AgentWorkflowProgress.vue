<script setup>
import { computed } from "vue";
import { useI18n } from "../composables/useI18n.js";
import RoseLoader from "./RoseLoader.vue";
import { confirmToolExecution, chooseToolOption } from "../api/chat.js";

const props = defineProps({
  workflow: { type: Object, default: null },
  /** 流程结束后仍展示（如流式回答阶段） */
  keepVisibleAfterDone: { type: Boolean, default: false },
});

const emit = defineEmits(["confirm", "reject", "choose"]);

const { t } = useI18n();

const running = computed(() => props.workflow?.running ?? false);
const summary = computed(() => props.workflow?.summary || "");
const liveThinking = computed(() => String(props.workflow?.liveThinking || "").trim());
const parsingUrls = computed(() => {
  const list = props.workflow?.parsingUrls;
  return Array.isArray(list) ? list : [];
});

const visible = computed(() => {
  if (!props.workflow) return false;
  if (running.value) return true;
  if (props.workflow.failed) return true;
  if (props.workflow.pendingConfirmation || props.workflow.pendingChoice) return true;
  if (props.keepVisibleAfterDone && summary.value) return true;
  return false;
});

const showLiveStatus = computed(() => running.value);

function statusLabel(status) {
  if (status === "done") return "已解析";
  if (status === "skipped") return "已跳过";
  if (status === "parsing") return "解析中";
  return "排队";
}

function shortUrl(url) {
  const u = String(url || "").trim();
  if (!u) return "";
  try {
    const parsed = new URL(u);
    const path = `${parsed.hostname}${parsed.pathname || ""}`.replace(/\/$/, "");
    return path.length > 64 ? `${path.slice(0, 61)}…` : path;
  } catch {
    return u.length > 64 ? `${u.slice(0, 61)}…` : u;
  }
}

/* Human-in-the-Loop 确认 */
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

/* Human-in-the-Loop 方案选择 */
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
    <!-- 上行：黑色较大「正在执行」；下行：灰色较小流式思考 -->
    <div v-if="showLiveStatus" class="aw__main">
      <RoseLoader class="aw__loader" :size="24" :rotation-duration="12000" />
      <div class="aw__body">
        <div class="aw__status">
          {{ summary || t("agentWorkflow.executing") }}
        </div>

        <div v-if="liveThinking" class="aw__thinking" aria-label="思考过程">
          {{ liveThinking }}
        </div>

        <ul v-if="parsingUrls.length" class="aw__urls">
          <li
            v-for="(item, idx) in parsingUrls"
            :key="`${item.url}-${idx}`"
            class="aw__url"
            :class="`aw__url--${item.status || 'pending'}`"
          >
            <span class="aw__url-status">{{ statusLabel(item.status) }}</span>
            <span class="aw__url-text" :title="item.url">{{ shortUrl(item.url) }}</span>
          </li>
        </ul>
      </div>
    </div>

    <!-- Human-in-the-Loop 确认 -->
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
          <button class="aw__btn aw__btn--reject" :disabled="pendingConfirm.disabled" @click="onReject">
            取消
          </button>
        </div>
      </div>
    </div>
    <div v-else-if="pendingConfirm?.status === 'accepted'" class="aw__hitl aw__hitl--done">
      <div class="aw__hitl-icon aw__hitl-icon--done">&#x2713;</div>
      <div class="aw__hitl-body">
        <div class="aw__hitl-title">已确认：{{ pendingConfirm.title }}</div>
        <div v-if="pendingConfirm.detail" class="aw__hitl-detail">{{ pendingConfirm.detail }}</div>
      </div>
    </div>
    <div v-else-if="pendingConfirm?.status === 'rejected'" class="aw__hitl aw__hitl--rejected">
      <div class="aw__hitl-icon aw__hitl-icon--rejected">&#x2717;</div>
      <div class="aw__hitl-body">
        <div class="aw__hitl-title">已取消：{{ pendingConfirm.title }}</div>
        <div v-if="pendingConfirm.detail" class="aw__hitl-detail">{{ pendingConfirm.detail }}</div>
      </div>
    </div>

    <!-- Human-in-the-Loop 方案选择 -->
    <div v-if="pendingChoice?.status === 'awaiting'" class="aw__choice">
      <div class="aw__choice-icon">?</div>
      <div class="aw__choice-body">
        <div class="aw__choice-question">{{ pendingChoice.question }}</div>
        <div class="aw__choice-options">
          <button v-for="(option, optIndex) in pendingChoice.options" :key="optIndex"
            class="aw__choice-btn" :disabled="pendingChoice.choosing" @click="onChoose(optIndex)">
            <RoseLoader v-if="pendingChoice.choosing" class="aw__btn-loader" :size="16" />
            <span v-else>{{ option }}</span>
          </button>
        </div>
      </div>
    </div>
    <div v-else-if="pendingChoice?.status === 'chosen'" class="aw__choice aw__choice--done">
      <div class="aw__choice-icon aw__choice-icon--done">&#x2713;</div>
      <div class="aw__choice-body">
        <div class="aw__choice-question">{{ pendingChoice.question }}</div>
        <div class="aw__choice-result">已选择：{{ pendingChoice.selected }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.aw {
  margin-bottom: 10px;
  padding: 10px 12px;
  font-size: 13px;
  color: var(--platform-text);
}

.aw__main {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  line-height: 1.5;
}

.aw__loader {
  flex-shrink: 0;
  margin-top: -2px;
  line-height: 0;
}

.aw__body {
  flex: 1;
  min-width: 0;
}

.aw__btn-loader {
  flex-shrink: 0;
  line-height: 0;
}

.aw__status {
  font-size: 14px;
  font-weight: 500;
  line-height: 1.5;
  color: var(--platform-text, #0f172a);
  word-break: break-word;
}

.aw__thinking {
  margin-top: 6px;
  max-height: 5.4em;
  overflow: hidden;
  font-size: 13px;
  font-weight: 400;
  line-height: 1.5;
  color: var(--platform-text-secondary, #64748b);
  white-space: pre-wrap;
  word-break: break-word;
  mask-image: linear-gradient(to bottom, transparent 0%, #000 14%, #000 100%);
}

.aw__urls {
  margin: 8px 0 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.aw__url {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 12px;
  line-height: 1.4;
  color: var(--platform-text-secondary, #64748b);
}

.aw__url-status {
  flex-shrink: 0;
  min-width: 3em;
  font-size: 11px;
  color: var(--platform-text-tertiary, #94a3b8);
}

.aw__url--parsing .aw__url-status {
  color: var(--platform-primary, #2563eb);
}

.aw__url--done .aw__url-status {
  color: #16a34a;
}

.aw__url--skipped .aw__url-status {
  color: #b45309;
}

.aw__url-text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── HITL ── */

.aw__hitl {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: var(--platform-radius-sm, 8px);
  background: rgba(59, 130, 246, 0.06);
  border: 1px solid rgba(59, 130, 246, 0.2);
}

.aw__hitl--done {
  background: rgba(34, 197, 94, 0.06);
  border-color: rgba(34, 197, 94, 0.2);
}

.aw__hitl--rejected {
  background: rgba(239, 68, 68, 0.06);
  border-color: rgba(239, 68, 68, 0.2);
}

.aw__hitl-icon {
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

.aw__hitl-icon--done {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
}

.aw__hitl-icon--rejected {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}

.aw__hitl-body {
  flex: 1;
  min-width: 0;
}

.aw__hitl-title {
  font-weight: 600;
  font-size: 13px;
  line-height: 1.4;
  color: var(--platform-text, #0f172a);
}

.aw__hitl-detail {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--platform-text-secondary, #64748b);
  word-break: break-word;
}

.aw__hitl-actions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}

.aw__btn {
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

.aw__btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.aw__btn--confirm {
  background: #3b82f6;
  color: #fff;
}

.aw__btn--confirm:hover:not(:disabled) {
  background: #2563eb;
}

.aw__btn--reject {
  background: rgba(15, 23, 42, 0.06);
  color: var(--platform-text, #0f172a);
}

.aw__btn--reject:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}

/* ── Choice ── */

.aw__choice {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: var(--platform-radius-sm, 8px);
  background: rgba(139, 92, 246, 0.06);
  border: 1px solid rgba(139, 92, 246, 0.2);
}

.aw__choice--done {
  background: rgba(34, 197, 94, 0.06);
  border-color: rgba(34, 197, 94, 0.2);
}

.aw__choice-icon {
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

.aw__choice-icon--done {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
}

.aw__choice-body {
  flex: 1;
  min-width: 0;
}

.aw__choice-question {
  font-size: 13px;
  line-height: 1.5;
  color: var(--platform-text, #0f172a);
  margin-bottom: 8px;
}

.aw__choice-result {
  margin-top: 4px;
  font-size: 13px;
  color: var(--platform-text-secondary, #64748b);
}

.aw__choice-options {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.aw__choice-btn {
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

.aw__choice-btn:hover:not(:disabled) {
  background: rgba(139, 92, 246, 0.15);
  border-color: #8b5cf6;
}

.aw__choice-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
