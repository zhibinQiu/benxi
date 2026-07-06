<script setup>
defineOptions({ inheritAttrs: false });

import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { usePlatformUi } from "../composables/usePlatformUi";
import { useI18n } from "../composables/useI18n.js";
import { useAppPreferences } from "../composables/useAppPreferences";
import {
  CloseOutline,
  SparklesOutline,
  PlayOutline,
  DocumentTextOutline,
  ListOutline,
  ChatbubbleEllipsesOutline,
  CalendarOutline,
  TimeOutline,
  RefreshOutline,
  TrashOutline,
  AddSharp,
  SettingsOutline,
} from "@vicons/ionicons5";
import {
  NButton,
  NIcon,
  NSpin,
  NModal,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NSelect,
  NDatePicker,
  NPopconfirm,
  NTag,
  NEmpty,
} from "naive-ui";
import ChatComposer from "./ChatComposer.vue";
import ChatDisclaimer from "./ChatDisclaimer.vue";
import ChatBubbleActions from "./ChatBubbleActions.vue";
import ChatMarkdownBody from "./ChatMarkdownBody.vue";
import { PLATFORM_APP_NAME } from "../constants/platform";
import {
  clearChatSession,
  loadChatSession,
  saveChatSession,
  serializeChatMessages,
} from "../utils/chatSessionPersist";
import { MAX_CHAT_MESSAGES, MAX_VISIBLE_CHAT_MESSAGES, trimChatMessages } from "../utils/chatMessageLimits.js";
import { trimHistoryForApi } from "../utils/chatHistoryBudget.js";
import {
  buildChatShareUrl,
  copyChatMessageText,
  shareChatMessageText,
} from "../utils/chatBubbleActions.js";
import {
  isPlainPreviewTruncated,
  plainMessagePreview,
  shouldRenderMessageRich,
} from "../utils/chatMessageRender.js";
import { messages as localeMessages } from "../locales";
import {
  digitalRobotChat,
  digitalRobotConfirm,
  fetchDigitalRobotTasks,
  createDigitalRobotTask,
  updateDigitalRobotTask,
  deleteDigitalRobotTask,
  executeDigitalRobotTaskNow,
} from "../api/chat.js";

const DIGITAL_ROBOT_SCOPE = "digital-robot";

const { t, chatScopeTitle } = useI18n();
const ui = usePlatformUi();
const { locale } = useAppPreferences();

const open = defineModel("open", { type: Boolean, default: false });
const props = defineProps({ anchorEl: { type: Object, default: null } });
const route = useRoute();

// ── Tab 切换: chat | tasks ─────────────────────────
const activeTab = ref("chat"); // "chat" | "tasks"

// ── 聊天 ────────────────────────────────────────────
const WELCOME_MESSAGE = computed(() => ({
  role: "robot",
  content: t("digitalRobotFab.welcome", { appName: PLATFORM_APP_NAME }),
}));
const quickTaskPrompts = computed(
  () => (localeMessages[locale.value] || localeMessages.zh)?.digitalRobotFab?.quickPrompts || []
);
const sending = ref(false);
const executing = ref(false);
const loadingHistory = ref(false);
const loadingConversationId = ref("");
const conversationId = ref(null);
const input = ref("");
const messages = ref([]);
const messageWindowStart = ref(0);
const expandedMessageIndexes = ref(new Set());
const historyHasOlder = ref(false);
const historyOldestId = ref(null);
const loadingOlderHistory = ref(false);
const pendingPlan = ref(null);

function normalizeMessageRole(m) {
  return { role: m.role === "assistant" ? "robot" : m.role, content: m.content || "", feedback: m.feedback, citations: m.citations, error: m.error };
}

const hiddenOlderCount = computed(() => messageWindowStart.value);
const canLoadOlder = computed(() => hiddenOlderCount.value > 0 || historyHasOlder.value);
const displayEntries = computed(() =>
  messages.value.slice(messageWindowStart.value).map((message, offset) => ({ message, index: messageWindowStart.value + offset }))
);

watch(() => messages.value.length, (len, prevLen) => {
  if (loadingOlderHistory.value) return;
  if (len <= MAX_VISIBLE_CHAT_MESSAGES) { messageWindowStart.value = 0; return; }
  if (len > prevLen) messageWindowStart.value = Math.max(messageWindowStart.value, len - MAX_VISIBLE_CHAT_MESSAGES);
});

function trimMessages() { if (messages.value.length <= MAX_CHAT_MESSAGES) return; messages.value = trimChatMessages(messages.value, MAX_CHAT_MESSAGES); }
function resetWelcomeMessage() { messages.value = [{ ...WELCOME_MESSAGE.value }]; pendingPlan.value = null; }
resetWelcomeMessage();
watch(locale, () => { if (messages.value.length === 1 && messages.value[0]?.role === "robot" && !conversationId.value) resetWelcomeMessage(); });

const messagesRef = ref(null);
const panelRef = ref(null);
const teleportReady = ref(false);
const markdownActive = ref(false);

function resolveAnchorNode() {
  const raw = props.anchorEl;
  if (!raw) return null;
  if (raw instanceof HTMLElement) return raw;
  if (raw.$el instanceof HTMLElement) return raw.$el;
  if (raw.value instanceof HTMLElement) return raw.value;
  if (raw.value?.$el instanceof HTMLElement) return raw.value.$el;
  return null;
}
const OUTSIDE_CLOSE_IGNORE_SELECTOR = ".n-dialog, .n-modal, .n-popover, .n-dropdown, .n-tooltip, .platform-confirm-dialog";
function onDocumentKeydown(event) { if (open.value && event.key === "Escape") open.value = false; }
function onOutsidePointerDown(event) {
  if (!open.value) return;
  const target = event.target;
  if (!(target instanceof Node)) return;
  if (panelRef.value?.contains(target)) return;
  if (resolveAnchorNode()?.contains(target)) return;
  if (target instanceof Element && target.closest(OUTSIDE_CLOSE_IGNORE_SELECTOR)) return;
  open.value = false;
}
function scrollToBottom() { nextTick(() => { const el = messagesRef.value; if (el) el.scrollTop = el.scrollHeight; }); }

watch(open, async (v) => {
  if (v) {
    markdownActive.value = true;
    scrollToBottom();
    document.addEventListener("keydown", onDocumentKeydown);
    document.addEventListener("pointerdown", onOutsidePointerDown, true);
  } else {
    markdownActive.value = false;
    expandedMessageIndexes.value = new Set();
    document.removeEventListener("keydown", onDocumentKeydown);
    document.removeEventListener("pointerdown", onOutsidePointerDown, true);
    trimMessages();
    persistSession();
  }
}, { immediate: true });

function historyForApi() { return trimHistoryForApi(messages.value); }
function shouldRenderRich(entry) { return shouldRenderMessageRich({ messageIndex: entry.index, totalMessages: messages.value.length, message: entry.message, chatDomActive: markdownActive.value, expandedIndexes: expandedMessageIndexes.value }); }
function expandMessage(index) { const next = new Set(expandedMessageIndexes.value); next.add(index); expandedMessageIndexes.value = next; }

async function showOlderMessages() {
  if (hiddenOlderCount.value > 0) { messageWindowStart.value = Math.max(0, messageWindowStart.value - 20); return; }
  if (!historyHasOlder.value || !historyOldestId.value || loadingOlderHistory.value || !conversationId.value) return;
  loadingOlderHistory.value = true;
  try {
    const { fetchChatConversationMessages } = await import("../api/client");
    const data = await fetchChatConversationMessages(DIGITAL_ROBOT_SCOPE, conversationId.value, { limit: 24, beforeId: historyOldestId.value });
    const older = Array.isArray(data?.messages) ? data.messages : [];
    historyHasOlder.value = Boolean(data?.has_older);
    historyOldestId.value = data?.oldest_id || historyOldestId.value;
    if (!older.length) { historyHasOlder.value = false; return; }
    messages.value = trimChatMessages([...older.map(normalizeMessageRole), ...messages.value]);
    messageWindowStart.value += older.length;
  } finally { loadingOlderHistory.value = false; }
}

let chatAbort = null;
function stopGeneration() { if (!sending.value) return; chatAbort?.abort(); chatAbort = null; sending.value = false; }

async function sendMessage(text) {
  const msg = (text || input.value).trim();
  if (!msg || sending.value || executing.value) return;
  input.value = "";
  messages.value.push({ role: "user", content: msg });
  scrollToBottom();
  sending.value = true;
  pendingPlan.value = null;
  chatAbort = new AbortController();
  try {
    const history = historyForApi().slice(0, -1);
    const data = await digitalRobotChat({ message: msg, history, conversationId: conversationId.value, signal: chatAbort.signal });
    if (data?.conversation_id) conversationId.value = data.conversation_id;
    const plan = data?.plan || null;
    const replyMsg = { role: "robot", content: data.reply, plan };
    messages.value.push(replyMsg);
    if (plan) pendingPlan.value = plan;
    trimMessages();
  } catch (e) {
    if (e?.name === "AbortError") return;
    messages.value.push({ role: "robot", content: t("digitalRobotFab.errorReply", { error: e.message || t("digitalRobotFab.serviceError") }) });
  } finally { sending.value = false; chatAbort = null; scrollToBottom(); persistSession(); }
}
function onKeydown(e) { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (sending.value || executing.value) return; sendMessage(); } }
function findUserIndexBefore(index) { for (let i = index - 1; i >= 0; i -= 1) { if (messages.value[i]?.role === "user") return i; } return -1; }
function canRetryMessage(index, message) { if (sending.value || executing.value || loadingHistory.value) return false; if (message?.role !== "robot") return false; return findUserIndexBefore(index) >= 0; }
function canShowMessageActions(index, message) { if (sending.value || executing.value || loadingHistory.value) return false; if (message?.role !== "robot") return false; if (!String(message?.content || "").trim()) return false; return findUserIndexBefore(index) >= 0; }
async function copyRobotMessage(message) { await copyChatMessageText(message?.content, { ui, t }); }
async function shareRobotMessage(message) { await shareChatMessageText(message?.content, { ui, t, title: chatScopeTitle(DIGITAL_ROBOT_SCOPE), shareUrl: buildChatShareUrl(conversationId.value, DIGITAL_ROBOT_SCOPE) }); }
function setMessageFeedback(index, value) { const message = messages.value[index]; if (!message) return; message.feedback = value; }
async function retryMessage(index) {
  const message = messages.value[index];
  if (!message || !canRetryMessage(index, message)) return;
  const userIndex = findUserIndexBefore(index);
  if (userIndex < 0) return;
  const content = (messages.value[userIndex]?.content || "").trim();
  if (!content) return;
  messages.value = messages.value.slice(0, userIndex);
  await sendMessage(content);
}

async function confirmExecutePlan() {
  if (!pendingPlan.value || !conversationId.value || executing.value) return;
  executing.value = true;
  messages.value.push({ role: "robot", content: `🤖 开始执行 RPA 任务：**${pendingPlan.value.summary || "浏览器自动化"}**`, isExecutionStart: true });
  scrollToBottom();
  try {
    const data = await digitalRobotConfirm({ conversationId: conversationId.value, plan: pendingPlan.value });
    const status = data?.success ? "✅" : "❌";
    const logText = (data?.execution_log || []).map((l) => `- ${l}`).join("\n");
    const screenshotSection = (data?.screenshot_urls || []).length > 0 ? "\n\n**截图预览：**\n" + data.screenshot_urls.map((url) => `![](${url})`).join("\n") : "";
    messages.value.push({ role: "robot", content: `${status} RPA 任务执行完成\n\n**执行日志：**\n${logText}${screenshotSection}`, isExecutionResult: true });
    pendingPlan.value = null;
  } catch (e) {
    messages.value.push({ role: "robot", content: `❌ RPA 执行失败：${e.message || "服务异常"}`, isExecutionResult: true });
  } finally { executing.value = false; scrollToBottom(); persistSession(); }
}
function cancelPlan() { pendingPlan.value = null; messages.value.push({ role: "robot", content: "已取消 RPA 任务。如需其他帮助，请继续描述。" }); scrollToBottom(); }

function persistSession() {
  const serialized = serializeChatMessages(messages.value);
  if (!conversationId.value && serialized.length <= 1 && !input.value.trim()) { clearChatSession(DIGITAL_ROBOT_SCOPE); return; }
  saveChatSession(DIGITAL_ROBOT_SCOPE, { conversationId: conversationId.value, messages: serialized, input: input.value });
}

async function loadConversationFromId(id) {
  if (!id) return;
  loadingConversationId.value = id;
  loadingHistory.value = true;
  open.value = true;
  try {
    const { fetchChatConversationMessages } = await import("../api/client");
    const data = await fetchChatConversationMessages(DIGITAL_ROBOT_SCOPE, id, { limit: MAX_CHAT_MESSAGES });
    if (loadingConversationId.value !== id) return;
    const rows = Array.isArray(data?.messages) ? data.messages : [];
    historyHasOlder.value = Boolean(data?.has_older);
    historyOldestId.value = data?.oldest_id || null;
    expandedMessageIndexes.value = new Set();
    conversationId.value = id;
    messages.value = rows.length > 0 ? trimChatMessages(rows.map(normalizeMessageRole), MAX_CHAT_MESSAGES) : [{ ...WELCOME_MESSAGE.value }];
    messageWindowStart.value = Math.max(0, messages.value.length - MAX_VISIBLE_CHAT_MESSAGES);
    await scrollToBottom();
    persistSession();
  } catch (e) {
    messages.value.push({ role: "robot", content: t("digitalRobotFab.loadHistoryFailed", { error: e.message || t("digitalRobotFab.retryLater") }) });
  } finally { loadingHistory.value = false; if (loadingConversationId.value === id) loadingConversationId.value = ""; }
}
watch(() => route.query.digitalRobotConversation, (id) => { const cid = typeof id === "string" ? id : ""; if (cid) loadConversationFromId(cid); });

onMounted(() => {
  requestAnimationFrame(() => { teleportReady.value = true; });
  const cid = typeof route.query.digitalRobotConversation === "string" ? route.query.digitalRobotConversation : "";
  if (cid) { loadConversationFromId(cid); return; }
  const saved = loadChatSession(DIGITAL_ROBOT_SCOPE);
  if (!saved) return;
  if (saved.input) input.value = saved.input;
  if (saved.conversationId) { loadConversationFromId(saved.conversationId); return; }
  if (Array.isArray(saved.messages) && saved.messages.length) messages.value = trimChatMessages(saved.messages.map((m) => ({ role: m.role, content: m.content || "" })), MAX_CHAT_MESSAGES);
});
onBeforeUnmount(() => { chatAbort?.abort(); document.removeEventListener("keydown", onDocumentKeydown); document.removeEventListener("pointerdown", onOutsidePointerDown, true); });

// ── 任务管理 ────────────────────────────────────────
const tasks = ref([]);
const tasksLoading = ref(false);
const taskFilter = ref("all");

const scheduleModeOptions = [
  { value: "immediate", label: "立即执行" },
  { value: "scheduled", label: "定时执行" },
  { value: "periodic", label: "周期执行" },
];

const statusBadgeMap = {
  pending: { type: "default", text: "待执行" },
  running: { type: "warning", text: "执行中" },
  scheduled: { type: "info", text: "已调度" },
  done: { type: "success", text: "已完成" },
  failed: { type: "error", text: "失败" },
  cancelled: { type: "default", text: "已取消" },
};

// 任务创建/编辑弹窗
const showTaskDialog = ref(false);
const editingTask = ref(null);
const taskForm = ref({
  title: "",
  description: "",
  schedule_mode: "immediate",
  scheduled_at: null,
  cron_expression: "",
  interval_seconds: null,
  plan: null,
});
const taskSaving = ref(false);

async function loadTasks() {
  tasksLoading.value = true;
  try {
    const data = await fetchDigitalRobotTasks({ status: taskFilter.value });
    tasks.value = Array.isArray(data) ? data : [];
  } catch (e) {
    tasks.value = [];
  } finally { tasksLoading.value = false; }
}

function openCreateTask(plan) {
  editingTask.value = null;
  taskForm.value = {
    title: plan?.summary || "未命名任务",
    description: "",
    schedule_mode: "immediate",
    scheduled_at: null,
    cron_expression: "",
    interval_seconds: null,
    plan: plan || null,
  };
  showTaskDialog.value = true;
}

function openEditTask(task) {
  editingTask.value = task;
  taskForm.value = {
    title: task.title,
    description: task.description || "",
    schedule_mode: task.schedule_mode || "immediate",
    scheduled_at: task.scheduled_at ? new Date(task.scheduled_at) : null,
    cron_expression: task.cron_expression || "",
    interval_seconds: task.interval_seconds || null,
    plan: task.plan_json || null,
  };
  showTaskDialog.value = true;
}

async function saveTask() {
  taskSaving.value = true;
  try {
    const payload = {
      title: taskForm.value.title,
      description: taskForm.value.description,
      schedule_mode: taskForm.value.schedule_mode,
      cron_expression: taskForm.value.schedule_mode === "periodic" ? (taskForm.value.cron_expression || null) : null,
      interval_seconds: taskForm.value.schedule_mode === "periodic" ? (taskForm.value.interval_seconds || null) : null,
      scheduled_at: taskForm.value.schedule_mode === "scheduled" ? (taskForm.value.scheduled_at?.toISOString() || null) : null,
      plan: taskForm.value.plan,
    };
    if (editingTask.value) {
      await updateDigitalRobotTask(editingTask.value.id, payload);
    } else {
      await createDigitalRobotTask(payload);
    }
    showTaskDialog.value = false;
    await loadTasks();
  } catch (e) {
    ui.message?.error?.("保存任务失败: " + (e.message || "未知错误"));
  } finally { taskSaving.value = false; }
}

/** 从聊天计划存入任务 */
async function savePlanAsTask() {
  if (!pendingPlan.value) return;
  openCreateTask(pendingPlan.value);
}

async function handleDeleteTask(taskId) {
  try {
    await deleteDigitalRobotTask(taskId);
    await loadTasks();
  } catch (e) {
    ui.message?.error?.("删除失败");
  }
}

async function handleExecuteNow(taskId) {
  try {
    await executeDigitalRobotTaskNow(taskId);
    ui.message?.success?.("已开始执行");
    await loadTasks();
  } catch (e) {
    ui.message?.error?.("执行失败: " + (e.message || "未知错误"));
  }
}

function formatDatetime(val) {
  if (!val) return "-";
  const d = new Date(val);
  return d.toLocaleString(locale.value === "zh" ? "zh-CN" : "en-US");
}

// 切换 tab 时加载任务列表
watch(activeTab, (v) => { if (v === "tasks") loadTasks(); });
</script>

<template>
  <Teleport v-if="teleportReady" to="body">
    <div class="digital-robot-root">
      <Transition name="digital-robot-panel">
        <div v-if="open" ref="panelRef" class="digital-robot-panel" role="dialog" :aria-label="t('digitalRobotFab.ariaDialog')">
          <!-- 头部：含 Tab 切换 -->
          <header class="digital-robot-header">
            <div class="digital-robot-header-brand">
              <div class="digital-robot-avatar">
                <n-icon :size="24" :component="SparklesOutline" />
              </div>
              <div>
                <div class="digital-robot-title">数字机器人</div>
                <div class="digital-robot-sub">RPA 自动化 · {{ activeTab === 'chat' ? '对话' : '任务管理' }}</div>
              </div>
            </div>
            <div class="digital-robot-header-actions">
              <!-- Tab 切换 -->
              <button
                type="button"
                class="digital-robot-tab-btn"
                :class="{ 'digital-robot-tab-btn--active': activeTab === 'chat' }"
                title="对话"
                @click="activeTab = 'chat'"
              >
                <n-icon :size="18" :component="ChatbubbleEllipsesOutline" />
              </button>
              <button
                type="button"
                class="digital-robot-tab-btn"
                :class="{ 'digital-robot-tab-btn--active': activeTab === 'tasks' }"
                title="任务管理"
                @click="activeTab = 'tasks'"
              >
                <n-icon :size="18" :component="ListOutline" />
              </button>
              <n-button quaternary circle size="small" :aria-label="t('digitalRobotFab.ariaClose')" @click="open = false">
                <template #icon><n-icon :component="CloseOutline" /></template>
              </n-button>
            </div>
          </header>

          <!-- ===================== 聊天 Tab ===================== -->
          <template v-if="activeTab === 'chat'">
            <div v-if="loadingHistory" class="digital-robot-history-loading">
              <n-spin size="small" /><span>{{ t("chat.loadingConversation") }}</span>
            </div>
            <div v-else ref="messagesRef" class="digital-robot-messages">
              <div v-if="canLoadOlder" class="digital-robot-load-older">
                <button type="button" class="digital-robot-load-older__btn" :disabled="loadingOlderHistory" @click="showOlderMessages">
                  <n-spin v-if="loadingOlderHistory" :size="17" />
                  <span v-else-if="hiddenOlderCount > 0">{{ t("chat.loadOlderMessages", { count: hiddenOlderCount }) }}</span>
                  <span v-else>{{ t("chat.loadOlderFromServer") }}</span>
                </button>
              </div>
              <div v-for="entry in displayEntries" :key="entry.index" class="digital-robot-msg" :class="entry.message.role === 'user' ? 'digital-robot-msg--user' : 'digital-robot-msg--bot'">
                <div class="digital-robot-msg-stack" :class="entry.message.role === 'user' ? 'digital-robot-msg-stack--user' : 'digital-robot-msg-stack--bot'">
                  <div v-if="entry.message.role === 'robot'" class="digital-robot-bubble digital-robot-bubble--bot">
                    <div v-if="shouldRenderRich(entry)" :key="`robot-md-${entry.index}`">
                      <ChatMarkdownBody :content="entry.message.content" />
                      <!-- RPA 计划确认卡片 -->
                      <div v-if="entry.message.plan && !entry.message.isExecutionStart && !entry.message.isExecutionResult" class="plan-confirm-card">
                        <div class="plan-confirm-title">
                          <n-icon :size="18" :component="DocumentTextOutline" />
                          <span>执行计划确认</span>
                        </div>
                        <div class="plan-summary">{{ entry.message.plan.summary || "浏览器自动化任务" }}</div>
                        <div class="plan-steps">
                          <div v-for="(step, si) in entry.message.plan.steps" :key="si" class="plan-step">
                            <span class="plan-step-num">{{ si + 1 }}</span>
                            <span class="plan-step-desc">{{ step.operation }} — {{ step.description }}</span>
                          </div>
                        </div>
                        <div class="plan-actions">
                          <n-button type="primary" :loading="executing" :disabled="executing" @click="confirmExecutePlan">
                            <template #icon><n-icon :component="PlayOutline" /></template>
                            立即执行
                          </n-button>
                          <n-button :disabled="executing" @click="savePlanAsTask">
                            <template #icon><n-icon :component="CalendarOutline" /></template>
                            定时执行
                          </n-button>
                          <n-button quaternary :disabled="executing" @click="cancelPlan">取消</n-button>
                        </div>
                      </div>
                    </div>
                    <div v-else class="digital-robot-msg-collapsed">
                      <span class="digital-robot-msg-plain">{{ plainMessagePreview(entry.message.content) }}</span>
                      <button v-if="isPlainPreviewTruncated(entry.message.content)" type="button" class="digital-robot-msg-expand" @click="expandMessage(entry.index)">{{ t("chat.expandMessage") }}</button>
                    </div>
                  </div>
                  <div v-else class="digital-robot-bubble digital-robot-bubble--user">{{ entry.message.content }}</div>
                  <ChatBubbleActions v-if="canShowMessageActions(entry.index, entry.message)" align="start" :show-retry="canRetryMessage(entry.index, entry.message)" :retry-disabled="sending || executing || loadingHistory" :feedback="entry.message.feedback || null" @copy="copyRobotMessage(entry.message)" @share="shareRobotMessage(entry.message)" @retry="retryMessage(entry.index)" @feedback="setMessageFeedback(entry.index, $event)" />
                </div>
              </div>
              <div v-if="sending" class="digital-robot-msg digital-robot-msg--bot">
                <div class="digital-robot-bubble digital-robot-bubble--bot digital-robot-bubble--typing">
                  <n-spin size="small" /><span>{{ t("chat.thinking") }}</span>
                </div>
              </div>
            </div>
            <div v-if="!sending && !executing && quickTaskPrompts.length > 0" class="digital-robot-quick">
              <button v-for="q in quickTaskPrompts" :key="q" type="button" class="digital-robot-chip" @click="sendMessage(q)">{{ q }}</button>
            </div>
            <footer class="digital-robot-footer">
              <ChatComposer v-model="input" :placeholder="t('digitalRobotFab.inputPlaceholder')" :loading="sending || executing" :min-rows="1" :max-rows="3" @keydown="onKeydown" @send="sendMessage()" @stop="stopGeneration" />
              <ChatDisclaimer />
            </footer>
          </template>

          <!-- ===================== 任务管理 Tab ===================== -->
          <template v-if="activeTab === 'tasks'">
            <div class="digital-robot-task-toolbar">
              <div class="digital-robot-task-filter">
                <button
                  v-for="opt in [{value:'all',label:'全部'},{value:'scheduled',label:'已调度'},{value:'done',label:'已完成'},{value:'failed',label:'失败'}]"
                  :key="opt.value"
                  type="button"
                  class="digital-robot-filter-btn"
                  :class="{ 'digital-robot-filter-btn--active': taskFilter === opt.value }"
                  @click="taskFilter = opt.value; loadTasks()"
                >{{ opt.label }}</button>
              </div>
              <n-button size="tiny" quaternary @click="openCreateTask(null)">
                <template #icon><n-icon :component="AddSharp" /></template>
                新建
              </n-button>
            </div>
            <div class="digital-robot-task-list">
              <div v-if="tasksLoading" class="digital-robot-task-loading"><n-spin size="small" /><span>加载中...</span></div>
              <div v-else-if="tasks.length === 0" class="digital-robot-task-empty">
                <n-empty description="暂无 RPA 任务">
                  <template #extra>
                    <n-button size="small" @click="activeTab = 'chat'">去创建任务</n-button>
                  </template>
                </n-empty>
              </div>
              <div v-else v-for="task in tasks" :key="task.id" class="digital-robot-task-item">
                <div class="digital-robot-task-item-header">
                  <span class="digital-robot-task-item-title">{{ task.title }}</span>
                  <n-tag :type="(statusBadgeMap[task.status] || {}).type || 'default'" size="tiny">
                    {{ (statusBadgeMap[task.status] || {}).text || task.status }}
                  </n-tag>
                </div>
                <div v-if="task.description" class="digital-robot-task-item-desc">{{ task.description }}</div>
                <div class="digital-robot-task-item-meta">
                  <span v-if="task.schedule_mode === 'scheduled' && task.scheduled_at">
                    <n-icon :size="12" :component="CalendarOutline" /> {{ formatDatetime(task.scheduled_at) }}
                  </span>
                  <span v-else-if="task.schedule_mode === 'periodic'">
                    <n-icon :size="12" :component="RefreshOutline" />
                    {{ task.cron_expression ? `Cron: ${task.cron_expression}` : `每 ${task.interval_seconds}s` }}
                  </span>
                  <span v-else><n-icon :size="12" :component="TimeOutline" /> 立即</span>
                  <span v-if="task.last_run_at" class="digital-robot-task-item-last">上次: {{ formatDatetime(task.last_run_at) }}</span>
                </div>
                <div class="digital-robot-task-item-steps" v-if="task.plan_json?.steps">
                  {{ task.plan_json.steps.length }} 步
                </div>
                <div class="digital-robot-task-item-actions">
                  <n-button size="tiny" quaternary circle :disabled="task.status === 'running'" @click="handleExecuteNow(task.id)">
                    <template #icon><n-icon :size="16" :component="PlayOutline" /></template>
                  </n-button>
                  <n-button size="tiny" quaternary circle @click="openEditTask(task)">
                    <template #icon><n-icon :size="16" :component="SettingsOutline" /></template>
                  </n-button>
                  <n-popconfirm @positive-click="handleDeleteTask(task.id)">
                    <template #trigger>
                      <n-button size="tiny" quaternary circle>
                        <template #icon><n-icon :size="16" :component="TrashOutline" /></template>
                      </n-button>
                    </template>
                    确认删除该任务？
                  </n-popconfirm>
                </div>
              </div>
            </div>
          </template>

        </div>
      </Transition>

      <!-- 任务创建/编辑弹窗 -->
      <n-modal v-model:show="showTaskDialog" preset="card" title="RPA 任务设置" :bordered="false" style="max-width: 520px;" :mask-closable="false">
        <n-form :model="taskForm" label-placement="top" size="small">
          <n-form-item label="任务名称">
            <n-input v-model:value="taskForm.title" placeholder="输入任务名称" />
          </n-form-item>
          <n-form-item label="任务描述">
            <n-input v-model:value="taskForm.description" type="textarea" :rows="2" placeholder="可选描述" />
          </n-form-item>
          <n-form-item label="执行方式">
            <n-select v-model:value="taskForm.schedule_mode" :options="scheduleModeOptions" />
          </n-form-item>

          <!-- 定时执行 -->
          <template v-if="taskForm.schedule_mode === 'scheduled'">
            <n-form-item label="执行时间">
              <n-date-picker
                v-model:value="taskForm.scheduled_at"
                type="datetime"
                clearable
                style="width: 100%;"
                :is-date-disabled="(ts) => Date.now() > ts"
              />
            </n-form-item>
          </template>

          <!-- 周期执行 -->
          <template v-if="taskForm.schedule_mode === 'periodic'">
            <n-form-item label="Cron 表达式">
              <n-input v-model:value="taskForm.cron_expression" placeholder="如: 0 9 * * 1-5 (工作日9点)" />
            </n-form-item>
            <n-form-item label="或 间隔秒数">
              <n-input-number v-model:value="taskForm.interval_seconds" :min="10" :max="86400" :step="60" placeholder="如 3600=每小时" style="width: 100%;" />
            </n-form-item>
          </template>

          <div v-if="taskForm.plan" class="digital-robot-task-plan-preview">
            <div class="digital-robot-task-plan-title">执行计划预览</div>
            <div class="plan-steps" style="margin-bottom: 0;">
              <div v-for="(step, si) in taskForm.plan.steps" :key="si" class="plan-step">
                <span class="plan-step-num">{{ si + 1 }}</span>
                <span class="plan-step-desc">{{ step.operation }} — {{ step.description || step.operation }}</span>
              </div>
            </div>
          </div>

          <div class="digital-robot-dialog-actions">
            <n-button :loading="taskSaving" type="primary" @click="saveTask">保存</n-button>
            <n-button quaternary @click="showTaskDialog = false">取消</n-button>
          </div>
        </n-form>
      </n-modal>
    </div>
  </Teleport>
</template>

<style scoped>
.digital-robot-root { position: fixed; right: 29px; bottom: 29px; z-index: var(--platform-z-flyout); display: flex; flex-direction: column; align-items: flex-end; gap: 14px; pointer-events: none; }
.digital-robot-root > * { pointer-events: auto; }
.digital-robot-panel { width: min(520px, calc(100vw - 38px)); height: min(660px, calc(100vh - 144px)); min-height: 400px; display: flex; flex-direction: column; overflow: hidden; background: var(--platform-bg-elevated-solid, #fff); border-radius: var(--platform-radius, 17px); border: 1px solid var(--platform-glass-border, rgba(15, 23, 42, 0.08)); box-shadow: var(--platform-shadow-lg); }
.digital-robot-header { flex-shrink: 0; display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; background: linear-gradient(135deg, var(--platform-accent-soft) 0%, rgba(241, 245, 249, 0.9) 100%); border-bottom: 1px solid var(--platform-border); }
.digital-robot-header-brand { display: flex; align-items: center; gap: 10px; }
.digital-robot-avatar { width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; color: var(--platform-accent); background: #fff; box-shadow: 0 1px 5px color-mix(in srgb, var(--platform-accent) 20%, transparent); }
.digital-robot-title { font-size: 15px; font-weight: 600; color: #0f172a; line-height: 1.2; }
.digital-robot-sub { font-size: 11px; color: #64748b; }
.digital-robot-header-actions { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.digital-robot-tab-btn { width: 32px; height: 32px; border-radius: 8px; display: flex; align-items: center; justify-content: center; border: 1px solid transparent; background: transparent; color: #64748b; cursor: pointer; transition: all 0.15s; }
.digital-robot-tab-btn:hover { background: rgba(0,0,0,0.04); }
.digital-robot-tab-btn--active { background: #fff; color: var(--platform-accent); border-color: var(--platform-border); box-shadow: 0 1px 3px rgba(0,0,0,0.06); }

/* 聊天区域 */
.digital-robot-history-loading { flex: 1; min-height: 96px; display: flex; align-items: center; justify-content: center; gap: 10px; color: #64748b; font-size: 16px; background: #f8fafc; }
.digital-robot-messages { flex: 1; min-height: 0; overflow-y: auto; contain: layout style paint; padding: 14px; display: flex; flex-direction: column; gap: 12px; background: #f8fafc; }
.digital-robot-load-older { display: flex; justify-content: center; }
.digital-robot-load-older__btn { border: 1px solid var(--platform-border); background: #fff; color: #64748b; font-size: 14px; padding: 5px 12px; border-radius: 1199px; cursor: pointer; }
.digital-robot-msg-collapsed { display: flex; flex-direction: column; align-items: flex-start; gap: 7px; }
.digital-robot-msg-expand { border: none; background: transparent; color: var(--platform-accent); font-size: 14px; cursor: pointer; }
.digital-robot-msg { display: flex; }
.digital-robot-msg--user { justify-content: flex-end; }
.digital-robot-msg--bot { justify-content: flex-start; }
.digital-robot-msg-stack { display: flex; flex-direction: column; max-width: 92%; }
.digital-robot-msg-stack--user { align-items: flex-end; }
.digital-robot-msg-stack--bot { align-items: flex-start; }
.digital-robot-bubble { width: 100%; max-width: 100%; padding: 12px 14px; font-size: 16px; line-height: 1.55; border-radius: 14px; word-break: break-word; }
.digital-robot-bubble--user { width: fit-content; max-width: 100%; background: var(--platform-bg-tertiary); color: var(--platform-text); border: 1px solid var(--platform-border); border-bottom-right-radius: 5px; white-space: pre-wrap; }
.digital-robot-bubble--bot { padding: 0; border-radius: 0; background: transparent; color: var(--platform-text); border: none; box-shadow: none; }
.digital-robot-bubble--typing { display: flex; align-items: center; gap: 10px; padding: 0; color: var(--platform-text-secondary); }
.digital-robot-bubble--bot :deep(p) { margin: 0.35em 0; }
.digital-robot-bubble--bot :deep(code) { font-size: 0.9em; padding: 0.1em 0.35em; border-radius: 5px; background: #f1f5f9; }

/* 计划确认卡片 */
.plan-confirm-card { margin-top: 14px; background: #fff; border: 1px solid var(--platform-border); border-radius: 14px; padding: 14px; }
.plan-confirm-title { display: flex; align-items: center; gap: 8px; font-weight: 600; font-size: 15px; color: #0f172a; margin-bottom: 10px; }
.plan-summary { font-size: 14px; color: #64748b; margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #f1f5f9; }
.plan-steps { display: flex; flex-direction: column; gap: 8px; margin-bottom: 14px; }
.plan-step { display: flex; align-items: center; gap: 10px; font-size: 14px; color: #334155; }
.plan-step-num { width: 22px; height: 22px; border-radius: 50%; background: var(--platform-accent-soft); color: var(--platform-accent); display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600; flex-shrink: 0; }
.plan-step-desc { flex: 1; }
.plan-actions { display: flex; gap: 8px; justify-content: flex-end; flex-wrap: wrap; }

.digital-robot-quick { flex-shrink: 0; display: flex; flex-wrap: wrap; gap: 7px; padding: 10px 14px 0; background: #fff; }
.digital-robot-chip { font-size: 13px; padding: 5px 12px; border-radius: 1199px; border: 1px solid var(--platform-border); background: var(--platform-bg-secondary); color: var(--platform-text); cursor: pointer; }
.digital-robot-chip:hover { color: var(--platform-text); background: var(--platform-bg-tertiary); border-color: var(--platform-border); }
.digital-robot-footer { flex-shrink: 0; padding: 12px 14px 14px; background: #fff; border-top: 1px solid var(--platform-border); }

/* 任务管理 */
.digital-robot-task-toolbar { flex-shrink: 0; display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; background: #fff; border-bottom: 1px solid var(--platform-border); gap: 10px; }
.digital-robot-task-filter { display: flex; gap: 4px; flex-wrap: wrap; }
.digital-robot-filter-btn { font-size: 12px; padding: 3px 10px; border-radius: 1199px; border: 1px solid var(--platform-border); background: transparent; color: #64748b; cursor: pointer; }
.digital-robot-filter-btn--active { background: var(--platform-accent-soft); color: var(--platform-accent); border-color: transparent; }
.digital-robot-task-list { flex: 1; min-height: 0; overflow-y: auto; padding: 10px 14px; display: flex; flex-direction: column; gap: 8px; background: #f8fafc; }
.digital-robot-task-loading { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 40px 0; color: #64748b; }
.digital-robot-task-empty { display: flex; align-items: center; justify-content: center; padding: 40px 0; }
.digital-robot-task-item { background: #fff; border-radius: 12px; border: 1px solid var(--platform-border); padding: 12px; }
.digital-robot-task-item-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 4px; }
.digital-robot-task-item-title { font-weight: 600; font-size: 14px; color: #0f172a; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.digital-robot-task-item-desc { font-size: 12px; color: #64748b; margin-bottom: 6px; }
.digital-robot-task-item-meta { display: flex; align-items: center; gap: 12px; font-size: 12px; color: #64748b; flex-wrap: wrap; }
.digital-robot-task-item-meta span { display: inline-flex; align-items: center; gap: 4px; }
.digital-robot-task-item-steps { font-size: 12px; color: #94a3b8; margin-top: 4px; }
.digital-robot-task-item-actions { display: flex; align-items: center; gap: 4px; margin-top: 8px; justify-content: flex-end; }
.digital-robot-task-plan-preview { background: #f8fafc; border-radius: 8px; padding: 10px; margin-bottom: 12px; }
.digital-robot-task-plan-title { font-size: 13px; font-weight: 600; margin-bottom: 8px; color: #334155; }
.digital-robot-dialog-actions { display: flex; gap: 10px; justify-content: flex-end; }
.digital-robot-panel-enter-active, .digital-robot-panel-leave-active { transition: opacity 0.22s ease, transform 0.22s ease; }
.digital-robot-panel-enter-from, .digital-robot-panel-leave-to { opacity: 0; transform: translateY(14px) scale(0.96); }
</style>
