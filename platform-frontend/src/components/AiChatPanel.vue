<script setup>
import { usePlatformUi } from "../composables/usePlatformUi";
import {
  computed,
  nextTick,
  onActivated,
  onBeforeUnmount,
  onDeactivated,
  onMounted,
  ref,
  watch,
} from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { TimeOutline, DocumentTextOutline, DocumentOutline, GitNetworkOutline, CloseOutline, AttachOutline } from "@vicons/ionicons5";
import { fetchChatConversationMessages } from "../api/client";
import {
  AI_CHAT_ATTACHMENT_ACCEPT,
  clearAiChatAttachments,
  fetchAiChatAttachments,
  removeAiChatAttachmentFile,
  uploadAiChatAttachments,
} from "../api/chat.js";
import { NButton, NIcon, NSpin } from "naive-ui";
import { marked } from "marked";
import ChatComposer from "./ChatComposer.vue";
import ChatBubbleRetry from "./ChatBubbleRetry.vue";
import IconAction from "./IconAction.vue";
import MarkdownRichContent from "./MarkdownRichContent.vue";
import KnowledgeChatContent from "./KnowledgeChatContent.vue";
import KnowledgeCitationCard from "./KnowledgeCitationCard.vue";
import KnowledgeCitationPreviewModal from "./KnowledgeCitationPreviewModal.vue";
import KnowledgeMindMap from "./KnowledgeMindMap.vue";
import ChatMessageCitations from "./ChatMessageCitations.vue";
import AgentWorkflowProgress from "./AgentWorkflowProgress.vue";
import { useI18n } from "../composables/useI18n.js";
import { emptyAgentWorkflow, applyAgentWorkflowEvent } from "../utils/agentWorkflow.js";
import { splitCitedCitations } from "../utils/reportCitations.js";
import { exportMindmapMarkdown, exportMindmapOpml } from "../utils/mindmapExport.js";
import { useAppDisplayName } from "../composables/usePlatformBranding";
import { navigateWithReturn } from "../utils/navigationReturn";
import {
  clearChatSession,
  loadChatSession,
  saveChatSession,
  serializeChatMessages,
  SERVER_HISTORY_SCOPES,
} from "../utils/chatSessionPersist";

const props = defineProps({
  title: { type: String, required: true },
  description: { type: String, default: "" },
  subtitle: { type: String, default: "" },
  suggestions: { type: Array, default: () => [] },
  /** { title, description?, route, icon? } */
  toolLinks: { type: Array, default: () => [] },
  icon: { type: Object, required: true },
  streaming: { type: Boolean, default: true },
  streamChat: { type: Function, default: null },
  chatSend: { type: Function, default: null },
  richMarkdown: { type: Boolean, default: false },
  showWorkflowProgress: { type: Boolean, default: false },
  showCitations: { type: Boolean, default: false },
  /** 将回答中的 [1][2] 与引用列表联动，并支持溯源弹窗 */
  linkifyCitations: { type: Boolean, default: false },
  chatHeaderSub: { type: String, default: "" },
  /** 对话中顶栏是否展示图标、标题与小标题（false 时仅保留操作按钮） */
  showChatHeaderBrand: { type: Boolean, default: true },
  /** 标题使用系统渐变色 */
  titleGradient: { type: Boolean, default: false },
  /** 进入对话后输入框占位文案 */
  replyPlaceholder: { type: String, default: "" },
  /** 对话历史 scope：ai-home | carbon-qa | smart-data-query */
  chatScope: { type: String, default: "" },
  /** 是否展示历史对话 / 新对话（知识检索等单次会话场景设为 false） */
  showSessionActions: { type: Boolean, default: true },
  /** 报告生成：最新报告支持思维导图与 Word 导出 */
  showReportTools: { type: Boolean, default: false },
  reportMindmapFetch: { type: Function, default: null },
  reportWordExport: { type: Function, default: null },
  /** { id, label, description?, prompt } */
  reportOptimizePresets: { type: Array, default: () => [] },
  /** 流式回复期间仍允许编辑输入框（Enter 发送会先停止当前生成） */
  composerInputWhileLoading: { type: Boolean, default: false },
  /** AI 智能体：支持上传临时附件（不入库） */
  enableAttachments: { type: Boolean, default: false },
});

const conversationId = defineModel("conversationId", { type: String, default: null });

const emit = defineEmits(["new-chat"]);

const ui = usePlatformUi();
const { t } = useI18n();
const appDisplayName = useAppDisplayName();
const route = useRoute();
const router = useRouter();

marked.setOptions({ gfm: true, breaks: true });

const started = ref(false);
const loadingHistory = ref(false);
const input = ref("");
const sending = ref(false);
const messages = ref([]);
const messagesRef = ref(null);
const composerRef = ref(null);
const citationPreviewShow = ref(false);
const citationPreviewTarget = ref(null);
const reportViewMode = ref("answer");
const reportMindmapRef = ref(null);
const exportingWord = ref(false);
const exportingMindmap = ref("");
let streamAbort = null;
let streamGeneration = 0;

const attachmentSessionId = ref(null);
const attachmentFiles = ref([]);
const uploadingAttachments = ref(false);
const attachmentInputRef = ref(null);
const hasAttachments = computed(() => attachmentFiles.value.length > 0);

function openAttachmentPicker() {
  if (uploadingAttachments.value || sending.value) return;
  attachmentInputRef.value?.click?.();
}

async function refreshAttachmentList(sessionId = attachmentSessionId.value) {
  if (!sessionId) {
    attachmentFiles.value = [];
    return;
  }
  try {
    const data = await fetchAiChatAttachments(sessionId);
    attachmentSessionId.value = data?.attachment_session_id || sessionId;
    attachmentFiles.value = Array.isArray(data?.files) ? data.files : [];
  } catch {
    attachmentSessionId.value = null;
    attachmentFiles.value = [];
  }
}

async function onAttachmentInputChange(event) {
  const picked = Array.from(event?.target?.files || []);
  if (event?.target) event.target.value = "";
  if (!picked.length) return;
  uploadingAttachments.value = true;
  try {
    const data = await uploadAiChatAttachments(picked, {
      attachmentSessionId: attachmentSessionId.value,
    });
    attachmentSessionId.value = data?.attachment_session_id || attachmentSessionId.value;
    const added = Array.isArray(data?.files) ? data.files : [];
    if (added.length) {
      const existingIds = new Set(attachmentFiles.value.map((f) => f.file_id));
      attachmentFiles.value = [
        ...attachmentFiles.value,
        ...added.filter((f) => f?.file_id && !existingIds.has(f.file_id)),
      ];
    } else if (attachmentSessionId.value) {
      await refreshAttachmentList(attachmentSessionId.value);
    }
    const count = added.length || picked.length;
    ui.success(t("chat.attachments.uploadSuccess", { count }));
  } catch (e) {
    const msg = (e?.message || "").trim();
    if (/not\s*found/i.test(msg)) {
      ui.error(t("chat.attachments.serviceUnavailable"));
    } else {
      ui.error(msg || t("chat.attachments.uploadFailed"));
    }
  } finally {
    uploadingAttachments.value = false;
  }
}

async function removeAttachment(fileId) {
  const sid = attachmentSessionId.value;
  if (!sid || !fileId) return;
  uploadingAttachments.value = true;
  try {
    const data = await removeAiChatAttachmentFile(sid, fileId);
    attachmentFiles.value = Array.isArray(data?.files) ? data.files : [];
    if (!attachmentFiles.value.length) {
      attachmentSessionId.value = null;
    }
  } catch (e) {
    ui.error(e.message || t("chat.attachments.removeFailed"));
  } finally {
    uploadingAttachments.value = false;
  }
}

async function clearAttachmentState({ remote = true } = {}) {
  const sid = attachmentSessionId.value;
  attachmentSessionId.value = null;
  attachmentFiles.value = [];
  if (remote && sid) {
    try {
      await clearAiChatAttachments(sid);
    } catch {
      /* ignore */
    }
  }
}

const lastAssistantIndex = computed(() => {
  for (let i = messages.value.length - 1; i >= 0; i -= 1) {
    const m = messages.value[i];
    if (m.role === "assistant" && (m.content || "").trim() && !m.streaming) {
      return i;
    }
  }
  return -1;
});

const lastReportQuestion = computed(() => {
  const idx = lastAssistantIndex.value;
  if (idx < 0) return "";
  for (let i = idx - 1; i >= 0; i -= 1) {
    if (messages.value[i].role === "user") {
      return messages.value[i].content || "";
    }
  }
  return "";
});

const lastReportTitle = computed(() => {
  const q = lastReportQuestion.value.trim();
  if (!q) return t("chat.researchReport");
  return q.length > 48 ? `${q.slice(0, 47)}…` : q;
});

watch(lastAssistantIndex, () => {
  reportViewMode.value = "answer";
});

function isReportMessage(index, message) {
  return (
    props.showReportTools &&
    index === lastAssistantIndex.value &&
    message.role === "assistant" &&
    !message.streaming &&
    (message.content || "").trim()
  );
}

async function showReportMindmap() {
  reportViewMode.value = "mindmap";
  await nextTick();
  reportMindmapRef.value?.loadMindmap?.();
}

async function exportReportWord(content) {
  if (!props.reportWordExport) return;
  exportingWord.value = true;
  try {
    await props.reportWordExport({
      title: lastReportTitle.value,
      markdown: content,
    });
    ui.success(t("reportGeneration.exportWordSuccess"));
  } catch (e) {
    ui.error(e.message || t("reportGeneration.exportWordFailed"));
  } finally {
    exportingWord.value = false;
  }
}

function exportReportMindmap(format, messageIndex) {
  if (exportingMindmap.value) return;
  exportingMindmap.value = format;
  try {
    const payload = {
      mermaid: reportMindmapRef.value?.getMermaidSource?.() || "",
      question: reportQuestionForMessage(messageIndex),
      answer: messages.value[messageIndex]?.content || "",
      title: lastReportTitle.value,
    };
    if (format === "md") {
      exportMindmapMarkdown(payload);
      ui.success(t("reportGeneration.exportMindmapMdSuccess"));
    } else {
      exportMindmapOpml(payload);
      ui.success(t("reportGeneration.exportMindmapOpmlSuccess"));
    }
  } catch (e) {
    ui.error(e.message || t("reportGeneration.exportMindmapFailed"));
  } finally {
    exportingMindmap.value = "";
  }
}

function reportCitationGroups(message) {
  return splitCitedCitations(message?.content, message?.citations || []);
}

function reportQuestionForMessage(index) {
  for (let i = index - 1; i >= 0; i -= 1) {
    if (messages.value[i]?.role === "user") {
      return messages.value[i].content || "";
    }
  }
  return "";
}

function onReportCitationClick(index) {
  const el = document.getElementById(`report-cite-card-${index}`);
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }
  openCitationPreview(index);
}

function useReportOptimizePreset(preset) {
  const prompt = (preset?.prompt || preset?.description || preset?.label || "").trim();
  if (!prompt) return;
  input.value = prompt;
  nextTick(() => composerRef.value?.focus?.());
}

function openCitationPreview(citationOrIndex, citations = []) {
  let citation = citationOrIndex;
  if (typeof citationOrIndex === "number") {
    citation = (citations || []).find((c) => Number(c.index) === citationOrIndex);
  }
  if (!citation) return;
  if (citation.source === "kg" && citation.entity_id) {
    router.push({
      name: "kg-palantir",
      query: { focusEntityId: citation.entity_id },
    });
    return;
  }
  if (citation.source === "web" && citation.url) {
    window.open(citation.url, "_blank", "noopener,noreferrer");
    return;
  }
  citationPreviewTarget.value = citation;
  citationPreviewShow.value = true;
}

const displaySubtitle = computed(
  () => props.subtitle || t("chat.defaultSubtitle", { appName: appDisplayName.value })
);

const headerSub = computed(
  () =>
    props.chatHeaderSub ||
    (props.streaming ? t("chat.defaultHeaderSubStreaming") : t("chat.defaultHeaderSubStatic"))
);

const composerPlaceholder = computed(() =>
  started.value
    ? props.replyPlaceholder || t("chat.continueAsk")
    : t("chat.enterQuestion")
);

const landingComposerRows = computed(() => ({ minRows: 3, maxRows: 8 }));
/** 对话中输入框固定 1 行 */
const chatComposerRows = computed(() => ({ minRows: 1, maxRows: 1 }));

function emptyWorkflow() {
  return emptyAgentWorkflow();
}

function applyWorkflowEvent(workflow, ev) {
  return applyAgentWorkflowEvent(workflow, ev, t);
}

function renderMarkdown(text) {
  try {
    return marked.parse(text || "");
  } catch {
    return `<p>${text || ""}</p>`;
  }
}

async function scrollToBottom() {
  await nextTick();
  const el = messagesRef.value;
  if (el) el.scrollTop = el.scrollHeight;
}

function buildChatHistory() {
  return messages.value
    .filter((m) => m.role === "user" || m.role === "assistant")
    .map((m) => ({ role: m.role, content: m.content }));
}

async function sendMessageStreaming(content, assistantIdx, history) {
  streamAbort?.abort();
  streamAbort = new AbortController();

  let scrollTick = 0;
  try {
    await props.streamChat(
      {
        message: content,
        history,
        conversationId: conversationId.value,
        attachmentSessionId: attachmentSessionId.value,
      },
      {
        signal: streamAbort.signal,
        onWorkflow: (ev) => {
          if (!props.showWorkflowProgress) return;
          const row = messages.value[assistantIdx];
          if (!row) return;
          if (!row.workflow) row.workflow = emptyWorkflow();
          applyWorkflowEvent(row.workflow, ev);
          scrollTick += 1;
          if (scrollTick % 2 === 0) scrollToBottom();
        },
        onReplace: (text) => {
          const row = messages.value[assistantIdx];
          if (!row) return;
          row.content = text;
          scrollToBottom();
        },
        onCitations: (citations) => {
          if ((!props.showCitations && !props.showReportTools) || !Array.isArray(citations)) return;
          const row = messages.value[assistantIdx];
          if (row) row.citations = citations;
        },
        onDelta: (delta) => {
          const row = messages.value[assistantIdx];
          if (!row) return;
          row.content += delta;
          scrollTick += 1;
          if (scrollTick % 4 === 0) scrollToBottom();
        },
        onError: (err) => {
          const row = messages.value[assistantIdx];
          if (row?.content?.trim()) {
            row.streaming = false;
            if (row.workflow) {
              row.workflow.running = false;
              row.workflow.failed = false;
            }
            return;
          }
          throw err;
        },
        onDone: (payload) => {
          const row = messages.value[assistantIdx];
          if (row) {
            const full = (payload?.reply || "").trim();
            if (full) {
              row.content = full;
            }
            row.streaming = false;
            if (row.workflow) {
              row.workflow.running = false;
              row.workflow.failed = false;
            }
            if (props.showCitations || props.showReportTools) {
              if (Array.isArray(payload?.citations)) {
                row.citations = payload.citations;
              }
            }
          }
          if (payload?.conversation_id) {
            conversationId.value = payload.conversation_id;
          }
        }}
    );
    const row = messages.value[assistantIdx];
    if (row && !row.content.trim()) {
      row.streaming = false;
    }
  } catch (e) {
    if (e?.name === "AbortError") {
      finalizeStoppedAssistant(assistantIdx);
      return;
    }
    throw e;
  }
}

function finalizeStoppedAssistant(assistantIdx) {
  const row = messages.value[assistantIdx];
  if (!row || row.role !== "assistant") return;
  row.streaming = false;
  if (row.workflow) row.workflow.running = false;
  if (!row.content.trim()) {
    row.content = t("chat.stoppedGeneration");
  }
}

function stopGeneration() {
  if (!sending.value) return;
  streamGeneration += 1;
  const assistantIdx = messages.value.length - 1;
  streamAbort?.abort();
  finalizeStoppedAssistant(assistantIdx);
  sending.value = false;
  streamAbort = null;
}

async function revealContentTypewriter(row, fullText) {
  const text = (fullText || "").trim();
  if (!text) {
    row.streaming = false;
    row.content = "";
    return;
  }
  row.content = "";
  row.streaming = true;
  const step = Math.max(1, Math.floor(text.length / 100));
  for (let i = 0; i < text.length; i += step) {
    row.content = text.slice(0, Math.min(i + step, text.length));
    if (i % (step * 4) === 0) await scrollToBottom();
    await new Promise((r) => setTimeout(r, 14));
  }
  row.content = text;
  row.streaming = false;
}

async function sendMessageBlocking(content, assistantIdx, history) {
  messages.value.push({ role: "assistant", content: "", streaming: true });
  await scrollToBottom();

  const data = await props.chatSend({
    message: content,
    history,
    conversationId: conversationId.value});

  const row = messages.value[assistantIdx];
  if (row) {
    const reply = (data?.reply || "").trim();
    if (props.showCitations && Array.isArray(data?.citations)) {
      row.citations = data.citations;
    }
    if (data?.conversation_id) {
      conversationId.value = data.conversation_id;
    }
    if (reply) {
      await revealContentTypewriter(row, reply);
    } else {
      row.streaming = false;
      row.content = "";
    }
  }
}

async function sendMessage(text) {
  const content = (text ?? input.value).trim();
  if (!content) return;

  if (sending.value) {
    if (!props.composerInputWhileLoading) return;
    streamGeneration += 1;
    streamAbort?.abort();
    finalizeStoppedAssistant(messages.value.length - 1);
  }

  if (props.streaming && !props.streamChat) {
    ui.error(t("chat.streamNotConfigured"));
    return;
  }
  if (!props.streaming && !props.chatSend) {
    ui.error(t("chat.chatNotConfigured"));
    return;
  }

  const generation = ++streamGeneration;
  const firstTurn = !started.value;
  if (firstTurn) started.value = true;

  const history = buildChatHistory();
  messages.value.push({ role: "user", content });
  input.value = "";
  sending.value = true;

  if (firstTurn) {
    await nextTick();
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  }
  await scrollToBottom();

  const assistantIdx = messages.value.length;

  try {
    if (props.streaming) {
      messages.value.push({
        role: "assistant",
        content: "",
        streaming: true,
        workflow: props.showWorkflowProgress ? emptyWorkflow() : null});
      await scrollToBottom();
      await sendMessageStreaming(content, assistantIdx, history);
    } else {
      await sendMessageBlocking(content, assistantIdx, history);
    }
  } catch (e) {
    if (e?.name === "AbortError") {
      finalizeStoppedAssistant(assistantIdx);
      return;
    }
    ui.error(e.message || t("chat.sendFailed"));
    const row = messages.value[assistantIdx];
    if (row) {
      row.streaming = false;
      row.error = true;
      if (!row.content.trim()) {
        row.content = t("chat.sorryRetry");
      }
    } else {
      messages.value.push({
        role: "assistant",
        content: t("chat.sorryRetry"),
        error: true});
    }
  } finally {
    if (generation === streamGeneration) {
      sending.value = false;
      streamAbort = null;
    }
    await scrollToBottom();
    persistSessionState();
  }
}

function onComposerKeydown(e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

function findUserIndexBefore(index) {
  for (let i = index - 1; i >= 0; i -= 1) {
    if (messages.value[i]?.role === "user") return i;
  }
  return -1;
}

function canRetryMessage(index, message) {
  if (sending.value || loadingHistory.value || message?.streaming) return false;
  if (message?.role !== "assistant") return false;
  return findUserIndexBefore(index) >= 0;
}

async function retryMessage(index) {
  const message = messages.value[index];
  if (!message || !canRetryMessage(index, message)) return;

  const userIndex = findUserIndexBefore(index);
  if (userIndex < 0) return;

  const content = (messages.value[userIndex]?.content || "").trim();
  if (!content) return;

  streamAbort?.abort();
  streamGeneration += 1;
  sending.value = false;
  streamAbort = null;

  messages.value = messages.value.slice(0, userIndex);
  if (!messages.value.length) {
    started.value = false;
  }

  await sendMessage(content);
}

function useSuggestion(text) {
  input.value = text;
  sendMessage(text);
}

function persistSessionState() {
  if (!props.chatScope) return;
  const serialized = serializeChatMessages(messages.value);
  if (!serialized.length && !conversationId.value && !input.value.trim() && !attachmentSessionId.value) {
    clearChatSession(props.chatScope);
    return;
  }
  saveChatSession(props.chatScope, {
    conversationId: conversationId.value,
    messages: serialized,
    started: started.value,
    input: input.value,
    attachmentSessionId: attachmentSessionId.value,
    attachmentFiles: attachmentFiles.value,
  });
}

function newChat() {
  streamAbort?.abort();
  streamAbort = null;
  sending.value = false;
  started.value = false;
  messages.value = [];
  input.value = "";
  conversationId.value = null;
  clearAttachmentState();
  if (props.chatScope) clearChatSession(props.chatScope);
  emit("new-chat");
  if (route.query.conversationId) {
    const { conversationId: _cid, ...rest } = route.query;
    router.replace({ ...route, query: rest });
  }
}

function goToHistory() {
  if (!props.chatScope) return;
  navigateWithReturn(
    router,
    { name: "chat-history", params: { scope: props.chatScope } },
    route
  );
}

async function loadConversationFromId(id) {
  if (!props.chatScope || !id) return;
  if (!SERVER_HISTORY_SCOPES.has(props.chatScope)) return;
  loadingHistory.value = true;
  try {
    const rows = (await fetchChatConversationMessages(props.chatScope, id)) || [];
    streamAbort?.abort();
    streamAbort = null;
    sending.value = false;
    messages.value = rows.map((m) => ({
      role: m.role,
      content: m.content,
      streaming: false}));
    conversationId.value = id;
    started.value = messages.value.length > 0;
    input.value = "";
    await scrollToBottom();
    persistSessionState();
  } catch (e) {
    ui.error(e.message || t("chat.loadFailed"));
  } finally {
    loadingHistory.value = false;
  }
}

async function restorePersistedSession() {
  if (!props.chatScope) return;
  const saved = loadChatSession(props.chatScope);
  if (!saved) return;

  if (saved.input) input.value = saved.input;

  if (saved.attachmentSessionId) {
    attachmentSessionId.value = saved.attachmentSessionId;
    if (Array.isArray(saved.attachmentFiles) && saved.attachmentFiles.length) {
      attachmentFiles.value = saved.attachmentFiles;
    }
    await refreshAttachmentList(saved.attachmentSessionId);
  }

  if (SERVER_HISTORY_SCOPES.has(props.chatScope) && saved.conversationId) {
    await loadConversationFromId(saved.conversationId);
    return;
  }

  const rows = Array.isArray(saved.messages) ? saved.messages : [];
  if (!rows.length) return;

  messages.value = rows.map((m) => ({
    role: m.role,
    content: m.content || "",
    streaming: false,
    citations: m.citations,
    error: m.error,
  }));
  conversationId.value = saved.conversationId || null;
  started.value = Boolean(saved.started ?? messages.value.length > 0);
  await scrollToBottom();
}

watch(
  () => route.query.conversationId,
  (id) => {
    const cid = typeof id === "string" ? id : "";
    if (cid) loadConversationFromId(cid);
  }
);

onMounted(async () => {
  const cid = typeof route.query.conversationId === "string" ? route.query.conversationId : "";
  if (cid) {
    await loadConversationFromId(cid);
    return;
  }
  await restorePersistedSession();
});

onDeactivated(() => {
  // 切到其他页面时不中断流式请求；KeepAlive 下组件仍在内存中继续接收增量
  if (!sending.value) persistSessionState();
});

onActivated(() => {
  if (started.value) scrollToBottom();
  if (sending.value) persistSessionState();
});

onBeforeUnmount(() => {
  persistSessionState();
  streamAbort?.abort();
});

defineExpose({ newChat });
</script>

<template>
  <div
    class="ai-home"
    :class="{ 'ai-home--active': started }"
  >
    <div v-if="!started && chatScope && showSessionActions" class="ai-home-landing-topbar">
      <IconAction
        :label="t('chat.viewHistory')"
        :icon="TimeOutline"
        :disabled="loadingHistory"
        @click="goToHistory"
      />
    </div>

    <Transition name="ai-chat-header">
      <header
        v-if="started && (showChatHeaderBrand || showSessionActions)"
        class="ai-home-chat-header"
        :class="{ 'ai-home-chat-header--minimal': !showChatHeaderBrand }"
      >
        <div v-if="showChatHeaderBrand" class="ai-home-chat-brand">
          <div class="ai-home-icon ai-home-icon--sm">
            <n-icon :size="20" :component="icon" />
          </div>
          <div>
            <div class="ai-home-chat-title">{{ title }}</div>
            <div class="ai-home-chat-sub">{{ headerSub }}</div>
          </div>
        </div>
        <div v-if="showSessionActions" class="ai-home-chat-actions">
          <IconAction
            v-if="chatScope"
            :label="t('chat.history')"
            :icon="TimeOutline"
            :disabled="loadingHistory"
            @click="goToHistory"
          />
          <n-button size="small" quaternary @click="newChat">{{ t("chat.newChat") }}</n-button>
        </div>
      </header>
    </Transition>

    <div class="ai-home-main" :class="{ 'ai-home-main--landing': !started }">
      <Transition name="ai-welcome">
        <div v-if="!started" key="welcome" class="ai-home-welcome">
          <div class="ai-home-hero">
            <div class="ai-home-icon">
              <n-icon :size="36" :component="icon" />
            </div>
            <h1 class="ai-home-title" :class="{ 'platform-text-gradient': titleGradient }">
              {{ title }}
            </h1>
            <p v-if="description" class="ai-home-desc">{{ description }}</p>
            <p class="ai-home-sub">{{ displaySubtitle }}</p>
          </div>
        </div>
      </Transition>

      <div v-if="loadingHistory" class="ai-home-history-loading platform-inline-loading">
        <n-spin size="small" />
        <span>{{ t("chat.loadingConversation") }}</span>
      </div>

      <div
        v-else-if="started"
        ref="messagesRef"
        class="ai-home-messages"
        role="log"
        aria-live="polite"
      >
        <TransitionGroup name="ai-msg" tag="div" class="ai-home-messages-inner">
          <div
            v-for="(m, i) in messages"
            :key="`msg-${i}`"
            class="ai-home-msg"
            :class="m.role === 'user' ? 'ai-home-msg--user' : 'ai-home-msg--bot'"
          >
            <div
              class="ai-home-msg-stack"
              :class="m.role === 'user' ? 'ai-home-msg-stack--user' : 'ai-home-msg-stack--bot'"
            >
            <div
              v-if="m.role === 'assistant'"
              class="ai-home-bubble ai-home-bubble--bot"
              :class="{
                'ai-home-bubble--error': m.error,
                'ai-home-bubble--streaming': m.streaming}"
            >
              <AgentWorkflowProgress
                v-if="
                  showWorkflowProgress &&
                  m.streaming &&
                  !m.content &&
                  m.workflow?.running
                "
                :workflow="m.workflow"
                compact
              />
              <div v-else-if="m.streaming && !m.content" class="ai-thinking platform-inline-loading">
                <n-spin size="tiny" />
                {{ t("chat.thinking") }}
              </div>
              <div v-else-if="m.streaming" class="ai-home-stream-text">
                {{ m.content }}<span class="ai-home-cursor">▍</span>
              </div>
              <template v-else-if="isReportMessage(i, m)">
                <div class="ai-report-tools">
                  <div class="ai-report-tools__tabs" role="tablist">
                    <button
                      type="button"
                      class="ai-report-tools__tab"
                      :class="{ 'ai-report-tools__tab--active': reportViewMode === 'answer' }"
                      role="tab"
                      :aria-selected="reportViewMode === 'answer'"
                      @click="reportViewMode = 'answer'"
                    >
                      {{ t("reportGeneration.reportTab") }}
                    </button>
                    <button
                      type="button"
                      class="ai-report-tools__tab"
                      :class="{ 'ai-report-tools__tab--active': reportViewMode === 'mindmap' }"
                      role="tab"
                      :aria-selected="reportViewMode === 'mindmap'"
                      @click="showReportMindmap"
                    >
                      {{ t("reportGeneration.mindmapTab") }}
                    </button>
                  </div>
                </div>
                <KnowledgeMindMap
                  v-show="reportViewMode === 'mindmap'"
                  ref="reportMindmapRef"
                  :question="reportQuestionForMessage(i)"
                  :answer="m.content"
                  :fetch-mindmap="reportMindmapFetch"
                  :auto-load="true"
                  :active="reportViewMode === 'mindmap'"
                />
                <template v-if="reportViewMode !== 'mindmap'">
                  <KnowledgeChatContent
                    v-if="linkifyCitations && m.content"
                    :key="`kc-report-${i}`"
                    :content="m.content"
                    :citations="reportCitationGroups(m).cited"
                    @open-citation="onReportCitationClick"
                  />
                  <MarkdownRichContent
                    v-else-if="richMarkdown && m.content"
                    :key="`md-report-${i}`"
                    :content="m.content"
                  />
                  <div v-else-if="m.content" v-html="renderMarkdown(m.content)" />
                  <section
                    v-if="reportCitationGroups(m).local.length"
                    class="ai-report-citations"
                  >
                    <div class="ai-report-citations__head">
                      <span class="ai-report-citations__icon" aria-hidden="true">📎</span>
                      <span>{{ t("knowledgeSearch.citationsSection") }}</span>
                    </div>
                    <div class="ai-report-citations__list">
                      <KnowledgeCitationCard
                        v-for="c in reportCitationGroups(m).local"
                        :id="`report-cite-card-${c.index}`"
                        :key="`${c.index}-${c.chunk_id || c.document_id}`"
                        :citation="c"
                        :question="reportQuestionForMessage(i)"
                      />
                    </div>
                  </section>
                  <section
                    v-if="reportCitationGroups(m).web.length"
                    class="ai-report-web-cites"
                  >
                    <div class="ai-report-citations__head">
                      <span>{{ t("reportGeneration.webCitations") }}</span>
                    </div>
                    <ul class="ai-report-web-cites__list">
                      <li v-for="c in reportCitationGroups(m).web" :key="`web-${c.index}`">
                        <span class="ai-report-web-cites__num">[{{ c.index }}]</span>
                        <a
                          v-if="c.url"
                          :href="c.url"
                          target="_blank"
                          rel="noopener noreferrer"
                          class="ai-report-web-cites__link"
                        >
                          {{ c.title }}
                        </a>
                        <span v-else>{{ c.title }}</span>
                      </li>
                    </ul>
                  </section>
                </template>
                <div v-if="reportWordExport || reportViewMode === 'mindmap'" class="ai-report-export">
                  <template v-if="reportViewMode === 'answer' && reportWordExport">
                    <button
                      type="button"
                      class="ai-report-export__btn"
                      :disabled="exportingWord"
                      @click="exportReportWord(m.content)"
                    >
                      <n-spin v-if="exportingWord" :size="14" />
                      <n-icon v-else :size="15" :component="DocumentTextOutline" />
                      <span>{{ t("reportGeneration.exportWord") }}</span>
                    </button>
                  </template>
                  <template v-else-if="reportViewMode === 'mindmap'">
                    <button
                      type="button"
                      class="ai-report-export__btn"
                      :disabled="Boolean(exportingMindmap)"
                      @click="exportReportMindmap('md', i)"
                    >
                      <n-spin v-if="exportingMindmap === 'md'" :size="14" />
                      <n-icon v-else :size="15" :component="DocumentOutline" />
                      <span>{{ t("reportGeneration.exportMindmapMd") }}</span>
                    </button>
                    <button
                      type="button"
                      class="ai-report-export__btn"
                      :disabled="Boolean(exportingMindmap)"
                      @click="exportReportMindmap('opml', i)"
                    >
                      <n-spin v-if="exportingMindmap === 'opml'" :size="14" />
                      <n-icon v-else :size="15" :component="GitNetworkOutline" />
                      <span>{{ t("reportGeneration.exportMindmapOpml") }}</span>
                    </button>
                  </template>
                </div>
              </template>
              <KnowledgeChatContent
                v-else-if="linkifyCitations && m.content"
                :key="`kc-${i}`"
                :content="m.content"
                :citations="m.citations || []"
                @open-citation="openCitationPreview($event, m.citations)"
              />
              <MarkdownRichContent
                v-else-if="richMarkdown && m.content"
                :key="`md-${i}`"
                :content="m.content"
              />
              <div v-else-if="m.content" v-html="renderMarkdown(m.content)" />
              <div v-else class="ai-workflow-wait ai-workflow-wait--empty">{{ t("chat.noAnswer") }}</div>
              <ChatMessageCitations
                v-if="
                  showCitations &&
                  !showReportTools &&
                  !m.streaming &&
                  m.citations?.length
                "
                :citations="m.citations"
                :preview-on-click="linkifyCitations"
                @open-citation="openCitationPreview($event, m.citations)"
              />
            </div>
            <div v-else class="ai-home-bubble ai-home-bubble--user">
              {{ m.content }}
            </div>
            <ChatBubbleRetry
              v-if="m.role === 'assistant' && canRetryMessage(i, m)"
              align="start"
              @retry="retryMessage(i)"
            />
            </div>
          </div>
        </TransitionGroup>
      </div>

      <div class="ai-home-dock" :class="{ 'ai-home-dock--chat': started }">
        <div class="ai-home-dock-inner">
          <input
            v-if="enableAttachments"
            ref="attachmentInputRef"
            type="file"
            class="ai-home-attachment-input"
            :accept="AI_CHAT_ATTACHMENT_ACCEPT"
            multiple
            @change="onAttachmentInputChange"
          />
          <div
            v-if="(!started && toolLinks.length) || enableAttachments"
            class="ai-home-tools"
          >
            <template v-if="!started">
              <RouterLink
                v-for="tool in toolLinks"
                :key="tool.title"
                :to="tool.route"
                class="ai-home-tool-link"
              >
                <n-icon v-if="tool.icon" :size="13" :component="tool.icon" />
                <span>{{ tool.title }}</span>
              </RouterLink>
            </template>
            <button
              v-if="enableAttachments"
              type="button"
              class="ai-home-tool-link ai-home-tool-action"
              :disabled="uploadingAttachments || sending"
              @click="openAttachmentPicker"
            >
              <n-spin v-if="uploadingAttachments" :size="12" />
              <n-icon v-else :size="13" :component="AttachOutline" />
              <span>{{ t("chat.attachments.add") }}</span>
            </button>
          </div>
          <div v-if="enableAttachments && hasAttachments" class="ai-home-attachments">
            <div class="ai-home-attachments__label">{{ t("chat.attachments.label") }}</div>
            <div class="ai-home-attachments__list">
              <div
                v-for="file in attachmentFiles"
                :key="file.file_id"
                class="ai-home-attachment-chip"
                :title="file.warning || file.file_name"
              >
                <n-icon :size="14" :component="DocumentTextOutline" />
                <span class="ai-home-attachment-chip__name">{{ file.file_name }}</span>
                <button
                  type="button"
                  class="ai-home-attachment-chip__remove"
                  :disabled="uploadingAttachments || sending"
                  :aria-label="t('chat.attachments.remove')"
                  @click="removeAttachment(file.file_id)"
                >
                  <n-icon :size="12" :component="CloseOutline" />
                </button>
              </div>
            </div>
          </div>
          <div class="ai-home-composer">
            <ChatComposer
              ref="composerRef"
              v-model="input"
              :placeholder="composerPlaceholder"
              :disabled="!composerInputWhileLoading && sending"
              :loading="sending"
              :disable-input-while-loading="!composerInputWhileLoading"
              :min-rows="started ? chatComposerRows.minRows : landingComposerRows.minRows"
              :max-rows="started ? chatComposerRows.maxRows : landingComposerRows.maxRows"
              @keydown="onComposerKeydown"
              @send="sendMessage()"
              @stop="stopGeneration"
            />
          </div>
          <div
            v-if="showReportTools && started && reportOptimizePresets.length"
            class="ai-report-presets"
          >
            <div class="ai-report-presets__head">
              <span class="ai-report-presets__label">{{ t("reportGeneration.optimizePresets") }}</span>
            </div>
            <div class="ai-report-presets__list">
              <button
                v-for="p in reportOptimizePresets"
                :key="p.id"
                type="button"
                class="ai-report-presets__chip"
                :disabled="!composerInputWhileLoading && sending"
                :title="p.description || p.label"
                @click="useReportOptimizePreset(p)"
              >
                {{ p.label }}
              </button>
            </div>
          </div>
          <div v-if="!started && suggestions.length" class="ai-home-suggestions">
            <button
              v-for="s in suggestions"
              :key="s"
              type="button"
              class="ai-home-chip"
              :disabled="sending"
              @click="useSuggestion(s)"
            >
              {{ s }}
            </button>
          </div>
        </div>
        </div>
      </div>
    </div>

    <KnowledgeCitationPreviewModal
      v-if="linkifyCitations"
      v-model:show="citationPreviewShow"
      :citation="citationPreviewTarget"
    />
</template>

<style scoped>
.ai-home {
  position: relative;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--platform-chat-gradient);
  border-radius: var(--platform-radius);
  overflow: hidden;
}

.ai-home-landing-topbar {
  position: absolute;
  top: 12px;
  right: 16px;
  left: auto;
  z-index: 3;
}

.ai-home-main {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  position: relative;
  z-index: 1;
  overflow: hidden;
}

/* 首屏：标题 + 输入区作为整体，垂直居中偏下 */
.ai-home-main--landing {
  justify-content: center;
  align-items: center;
  padding-bottom: min(9vh, 64px);
  overflow: auto;
}

.ai-home-welcome {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 24px 24px 8px;
  overflow: auto;
}

.ai-home-main--landing .ai-home-welcome {
  flex: 0 0 auto;
  justify-content: center;
  padding: 0 24px;
  overflow: visible;
}

.ai-home-hero {
  text-align: center;
  max-width: 560px;
  margin-bottom: 12px;
}

.ai-home-icon {
  width: 72px;
  height: 72px;
  margin: 0 auto 16px;
  border-radius: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--platform-accent);
  background: var(--platform-accent-gradient-soft);
  border: 1px solid var(--platform-accent-border-soft);
  box-shadow: 0 4px 16px color-mix(in srgb, var(--platform-accent) 10%, transparent);
}

.ai-home-icon--sm {
  width: 40px;
  height: 40px;
  margin: 0;
  border-radius: 12px;
}

.ai-home-title {
  margin: 0 0 12px;
  font-size: 28px;
  font-weight: 700;
  color: var(--platform-text);
  letter-spacing: 0.02em;
}

.ai-home-title.platform-text-gradient {
  background-image: var(--platform-accent-gradient);
  background-size: 120% 100%;
  background-position: 0% 50%;
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  -webkit-text-fill-color: transparent;
}

.ai-home-desc {
  margin: 0 0 10px;
  font-size: 15px;
  line-height: 1.65;
  color: var(--platform-muted);
}

.ai-home-sub {
  margin: 0;
  font-size: 13px;
  color: #94a3b8;
}

.ai-home-dock {
  flex-shrink: 0;
  width: 100%;
  padding: 0 20px 20px;
  box-sizing: border-box;
  transition: transform 0.42s cubic-bezier(0.22, 1, 0.36, 1);
  will-change: transform;
}

.ai-home-dock-inner {
  width: min(640px, calc(100% - 8px));
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
}

.ai-home-main--landing .ai-home-dock {
  flex-shrink: 0;
  margin-top: 20px;
  padding: 0 20px;
  transform: none;
}

/* 对话中：输入区与消息区 flex 分区，视觉上悬浮但不遮挡内容 */
.ai-home-dock--chat {
  flex-shrink: 0;
  margin-top: 10px;
  padding: 0 20px 14px;
  transform: none;
  background: transparent;
}

.ai-home-tools {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-start;
  gap: 6px;
  width: 100%;
  padding-left: 2px;
  margin-bottom: 2px;
}

.ai-home-tool-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  font-size: 12px;
  line-height: 1.4;
  color: var(--platform-accent-pressed);
  text-decoration: none;
  border-radius: 999px;
  border: 1px solid var(--platform-accent-border);
  background: rgba(255, 255, 255, 0.85);
  transition:
    background 0.15s ease,
    border-color 0.15s ease;
}

.ai-home-tool-link:hover {
  background: var(--platform-accent-soft);
  border-color: var(--platform-accent-border);
}

.ai-home-tool-action {
  cursor: pointer;
  font-family: inherit;
}

.ai-home-tool-action:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.ai-home-suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: flex-start;
  width: 100%;
  padding-left: 2px;
  margin-top: 2px;
}

.ai-home-chip {
  padding: 6px 12px;
  font-size: 12px;
  color: var(--platform-accent-pressed);
  background: var(--platform-accent-muted);
  border: 1px solid var(--platform-accent-border-soft);
  border-radius: 999px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.ai-home-chip:hover:not(:disabled) {
  background: var(--platform-accent-soft);
  border-color: var(--platform-accent-border);
}

.ai-home-chip:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.ai-home-attachments {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ai-home-attachments__label {
  font-size: 12px;
  color: #64748b;
  padding-left: 4px;
}

.ai-home-attachments__list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.ai-home-attachment-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  padding: 4px 8px 4px 10px;
  border-radius: 999px;
  background: color-mix(in srgb, #fff 92%, var(--platform-accent, #0f766e));
  border: 1px solid color-mix(in srgb, var(--platform-accent, #0f766e) 18%, #e2e8f0);
  color: #334155;
  font-size: 12px;
}

.ai-home-attachment-chip__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 220px;
}

.ai-home-attachment-chip__remove {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: #94a3b8;
  cursor: pointer;
  padding: 0;
}

.ai-home-attachment-chip__remove:hover:not(:disabled) {
  color: #ef4444;
  background: color-mix(in srgb, #ef4444 10%, transparent);
}

.ai-home-attachment-chip__remove:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.ai-home-attachment-input {
  display: none;
}

.ai-home-composer {
  width: 100%;
}

.ai-home-dock--chat .ai-home-composer :deep(.chat-composer) {
  border-radius: 16px;
}

.ai-home :deep(.ai-chat-textarea.n-input) {
  --n-padding-left: 16px;
  --n-padding-right: 16px;
  --n-line-height-textarea: 1.55;
  font-size: 15px;
}

.ai-home :deep(.ai-chat-textarea .n-input__textarea-el),
.ai-home :deep(.ai-chat-textarea .n-input__placeholder),
.ai-home :deep(.ai-chat-textarea .n-input__textarea-mirror) {
  font-size: 15px;
  line-height: 1.55;
  padding-top: 14px;
  padding-left: 0;
  padding-right: 0;
}

.ai-home-chat-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--platform-border);
  background: var(--platform-surface);
  position: relative;
  z-index: 2;
}

.ai-home-chat-header--minimal {
  justify-content: flex-end;
  padding: 10px 16px 4px;
  background: transparent;
  border-bottom: none;
}

.ai-home-chat-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.ai-home-history-loading {
  flex: 1;
  min-height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--platform-text-secondary);
  font-size: 14px;
}

.ai-home-chat-brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.ai-home-chat-title {
  font-size: 15px;
  font-weight: 600;
  color: #0f172a;
}

.ai-home-chat-sub {
  font-size: 12px;
  color: var(--platform-muted);
}

.ai-home-messages {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px 20px 12px;
  -webkit-overflow-scrolling: touch;
  box-sizing: border-box;
}

.ai-home-messages-inner {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.ai-home-msg {
  display: flex;
}

.ai-home-msg--user {
  justify-content: flex-end;
}

.ai-home-msg--bot {
  justify-content: flex-start;
}

.ai-home-msg-stack {
  display: flex;
  flex-direction: column;
  max-width: min(720px, 88%);
}

.ai-home-msg-stack--user {
  align-items: flex-end;
}

.ai-home-msg-stack--bot {
  align-items: flex-start;
}

.ai-home-bubble {
  width: 100%;
  max-width: 100%;
  padding: 12px 16px;
  border-radius: 14px;
  font-size: 14px;
  line-height: 1.6;
  word-break: break-word;
}

.ai-home-bubble--user {
  background: var(--platform-accent-gradient);
  color: #fff;
  border-bottom-right-radius: 4px;
}

.ai-home-bubble--bot {
  background: var(--platform-surface);
  color: #334155;
  border: 1px solid var(--platform-border);
  border-bottom-left-radius: 4px;
  box-shadow: var(--platform-shadow);
}

.ai-home-bubble--error {
  border-color: rgba(239, 68, 68, 0.3);
  background: #fef2f2;
}

.ai-home-stream-text {
  white-space: pre-wrap;
  word-break: break-word;
}

.ai-home-cursor {
  display: inline-block;
  color: var(--platform-accent);
  animation: ai-home-blink 1s step-end infinite;
  margin-left: 1px;
}

@keyframes ai-home-blink {
  50% {
    opacity: 0;
  }
}

.ai-home-bubble--streaming {
  min-height: 2.5em;
}

.ai-home-bubble--bot :deep(p) {
  margin: 0 0 0.5em;
}

.ai-home-bubble--bot :deep(p:last-child) {
  margin-bottom: 0;
}

.ai-home-bubble--bot :deep(ul),
.ai-home-bubble--bot :deep(ol) {
  margin: 0.4em 0;
  padding-left: 1.25em;
}

.ai-home-bubble--bot :deep(code) {
  font-size: 0.9em;
  padding: 2px 6px;
  border-radius: 4px;
  background: rgba(15, 23, 42, 0.06);
}

.ai-workflow-current {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 500;
  color: var(--platform-accent-pressed);
  margin-bottom: 10px;
  padding-bottom: 10px;
  border-bottom: 1px dashed var(--platform-accent-border);
}

.ai-workflow-current--failed {
  color: #b91c1c;
  border-bottom-color: rgba(239, 68, 68, 0.25);
}

.ai-workflow-wait {
  font-size: 13px;
  color: #94a3b8;
  padding: 4px 0;
}

.ai-thinking {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--platform-accent-pressed);
  padding: 4px 0;
}

.ai-workflow-wait--empty {
  color: #94a3b8;
}

.ai-report-tools {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--platform-accent-border-soft);
}

.ai-report-tools__tabs {
  display: inline-flex;
  gap: 4px;
  padding: 3px;
  border-radius: 10px;
  background: color-mix(in srgb, var(--platform-bg) 70%, transparent);
  border: 1px solid var(--platform-accent-border-soft);
}

.ai-report-tools__tab {
  border: none;
  background: transparent;
  color: var(--platform-text-secondary);
  font-size: 12px;
  font-weight: 600;
  padding: 6px 12px;
  border-radius: 8px;
  cursor: pointer;
}

.ai-report-tools__tab--active {
  color: var(--platform-accent-pressed);
  background: var(--platform-accent-muted);
}

.ai-report-presets {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
  margin-top: 10px;
  padding: 10px 12px;
  border-radius: 14px;
  background: color-mix(in srgb, var(--platform-bg) 62%, transparent);
  border: 1px solid color-mix(in srgb, var(--platform-glass-outline, var(--platform-accent-border-soft)) 75%, transparent);
  box-shadow: inset 0 1px 0 color-mix(in srgb, #fff 55%, transparent);
}

.ai-report-presets__head {
  display: flex;
  align-items: center;
  gap: 6px;
}

.ai-report-presets__label {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--platform-text-secondary);
}

.ai-report-presets__list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.ai-report-presets__chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 30px;
  padding: 5px 12px;
  border: 1px solid color-mix(in srgb, var(--platform-accent-border-soft) 85%, transparent);
  background: color-mix(in srgb, var(--platform-surface, #fff) 88%, transparent);
  color: var(--platform-text);
  font-size: 12px;
  font-weight: 500;
  line-height: 1.35;
  border-radius: 999px;
  cursor: pointer;
  transition:
    background 0.18s ease,
    border-color 0.18s ease,
    color 0.18s ease,
    transform 0.18s ease,
    box-shadow 0.18s ease;
}

.ai-report-presets__chip:hover:not(:disabled) {
  border-color: var(--platform-accent-border);
  color: var(--platform-accent-pressed);
  background: var(--platform-accent-muted);
  box-shadow: 0 2px 8px color-mix(in srgb, var(--platform-accent) 12%, transparent);
  transform: translateY(-1px);
}

.ai-report-presets__chip:active:not(:disabled) {
  transform: translateY(0);
}

.ai-report-presets__chip:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.ai-report-export {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--platform-accent-border-soft);
}

.ai-report-export__btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 34px;
  padding: 0 14px;
  border: 1px solid var(--platform-accent-border);
  border-radius: 10px;
  background: var(--platform-accent-muted);
  color: var(--platform-accent-pressed);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition:
    background 0.18s ease,
    border-color 0.18s ease,
    box-shadow 0.18s ease,
    transform 0.18s ease;
}

.ai-report-export__btn:hover:not(:disabled) {
  background: var(--platform-accent-soft);
  border-color: var(--platform-accent);
  box-shadow: 0 3px 12px color-mix(in srgb, var(--platform-accent) 16%, transparent);
  transform: translateY(-1px);
}

.ai-report-export__btn:active:not(:disabled) {
  transform: translateY(0);
}

.ai-report-export__btn:disabled {
  opacity: 0.65;
  cursor: wait;
}

.ai-report-citations {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--platform-accent-border-soft);
}

.ai-report-citations__head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--platform-text-secondary);
  margin-bottom: 10px;
}

.ai-report-citations__list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.ai-report-web-cites {
  margin-top: 12px;
}

.ai-report-web-cites__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ai-report-web-cites__num {
  color: var(--platform-accent);
  font-weight: 600;
  margin-right: 6px;
}

.ai-report-web-cites__link {
  color: var(--platform-accent);
  text-decoration: none;
}

.ai-report-web-cites__link:hover {
  text-decoration: underline;
}
</style>
