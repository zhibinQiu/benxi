<script setup>
defineOptions({ inheritAttrs: false });

import { usePlatformUi } from "../composables/usePlatformUi";
import {
  computed,
  defineAsyncComponent,
  nextTick,
  onActivated,
  onBeforeUnmount,
  onDeactivated,
  onMounted,
  ref,
  watch,
} from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { TimeOutline, DocumentTextOutline, DocumentOutline, GitNetworkOutline, FolderOpenOutline, SparklesOutline, LayersOutline, CloudOutline } from "@vicons/ionicons5";
import { fetchChatConversationMessages } from "../api/client";
import {
  collectScreenshotAttachmentCandidates,
  markdownHasAuthScreenshot,
  mergeAuthScreenshotMarkdownBlocks,
  normalizeChatAttachmentUrl,
} from "../utils/authenticatedImage.js";
import AssistantConclusionContent from "./AssistantConclusionContent.vue";
import {
  AI_CHAT_ATTACHMENT_ACCEPT,
  clearAiChatAttachments,
  fetchAiChatAgentCatalog,
  fetchAiChatSkillCatalog,
  fetchAiChatAttachments,
  removeAiChatAttachmentFile,
  uploadAiChatAttachments,
} from "../api/chat.js";
import { formatAgentDisplayName } from "../utils/agentDisplay.js";
import RoseLoader from "./RoseLoader.vue";
import { NButton, NIcon, NPopover } from "naive-ui";
import ChatComposer from "./ChatComposer.vue";
import ChatDisclaimer from "./ChatDisclaimer.vue";
import ChatBubbleActions from "./ChatBubbleActions.vue";
import IconAction from "./IconAction.vue";
import MarkdownRichContent from "./MarkdownRichContent.vue";
import ChatMarkdownBody from "./ChatMarkdownBody.vue";
import KnowledgeChatContent from "./KnowledgeChatContent.vue";
import KnowledgeCitationPreviewModal from "./KnowledgeCitationPreviewModal.vue";
const KnowledgeMindMap = defineAsyncComponent(() => import("./KnowledgeMindMap.vue"));
import ChatMessageCitations from "./ChatMessageCitations.vue";
import { useI18n } from "../composables/useI18n.js";
import AgentWorkflowProgress from "./AgentWorkflowProgress.vue";
import AgentWorkflowCompactProgress from "./AgentWorkflowCompactProgress.vue";
import { handleAgentWorkflowForNotifications } from "../composables/useNotificationAlerts.js";
import {
  emptyAgentWorkflow,
  applyAgentWorkflowEvent,
  sanitizeWorkflowDisplayText,
  formatWorkflowRunningLine,
  getWorkflowRunningSegment,
  getWorkflowLastError,
} from "../utils/agentWorkflow.js";
import { alignCitationsWithContent, splitCitedCitations } from "../utils/reportCitations.js";
import { exportMindmapMarkdown, exportMindmapOpml } from "../utils/mindmapExport.js";
import { navigateWithReturn } from "../utils/navigationReturn";
import { openExternal } from "../utils/openExternal.js";
import {
  clearChatSession,
  loadChatSession,
  readChatSessionBootstrap,
  saveChatSession,
  serializeChatMessages,
  SERVER_HISTORY_SCOPES,
} from "../utils/chatSessionPersist";
import {
  MAX_CHAT_MESSAGES,
  MAX_REPORT_HISTORY_CHARS,
  MAX_REPORT_HISTORY_FOR_API,
  MAX_VISIBLE_CHAT_MESSAGES,
  trimChatMessages,
} from "../utils/chatMessageLimits.js";
import { trimHistoryForApi } from "../utils/chatHistoryBudget.js";
import {
  isPlainPreviewTruncated,
  plainMessagePreview,
  shouldRenderMessageRich,
} from "../utils/chatMessageRender.js";
import {
  buildChatShareUrl,
  copyChatMessageText,
  shareChatMessageText,
} from "../utils/chatBubbleActions.js";
import { disposeRichContentInElement } from "../utils/richContentLifecycle.js";

const props = defineProps({
  title: { type: String, required: true },
  description: { type: String, default: "" },
  architecture: { type: [String, Object], default: "" },
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
  /** sessionStorage 持久化 key：多标签场景覆盖 chatScope，各标签独立存储 */
  sessionKey: { type: String, default: null },
  /** 对话状态变更回调({ streaming, hasContent }) */
  onChatStateChange: { type: Function, default: null },
  /** 是否展示历史对话 / 新对话（知识检索等单次会话场景设为 false） */
  showSessionActions: { type: Boolean, default: true },
  /** 历史 / 新对话由页面 Teleport 至顶栏 extension（仿知识检索布局） */
  sessionActionsInToolbar: { type: Boolean, default: false },
  /** 报告生成：最新报告支持思维导图与 Word 导出 */
  showReportTools: { type: Boolean, default: false },
  reportMindmapFetch: { type: Function, default: null },
  reportWordExport: { type: Function, default: null },
  reportLibraryImport: { type: Function, default: null },
  /** { id, label, description?, prompt } */
  reportOptimizePresets: { type: Array, default: () => [] },
  /** 报告撰写智能体挂载的报告类型 Skill */
  reportAgentSkills: { type: Array, default: () => [] },
  reportAgentSkillsLoading: { type: Boolean, default: false },
  /** 流式回复期间仍允许编辑输入框（发送需先停止当前生成） */
  composerInputWhileLoading: { type: Boolean, default: true },
  /** AI 智能体：支持上传临时附件（不入库） */
  enableAttachments: { type: Boolean, default: false },
  /** AI 智能体：展示 Agent Skills 目录 */
  enableAgentSkills: { type: Boolean, default: false },
  /** 输入框下方免责声明（知识检索/报告生成等全屏页默认关闭） */
  showDisclaimer: { type: Boolean, default: true },
});

const conversationId = defineModel("conversationId", { type: String, default: null });

const emit = defineEmits(["new-chat"]);

const ui = usePlatformUi();
const { t } = useI18n();

const showPanelSessionActions = computed(
  () => props.showSessionActions && !props.sessionActionsInToolbar
);
const route = useRoute();
const router = useRouter();

function goAgentkitDocs() {
  router.push({ name: "agentkit-docs" });
}

const architectureData = computed(() => {
  const raw = props.architecture;
  if (typeof raw === "string") return { summary: raw, features: [], linkText: "" };
  return raw;
});

/** sessionStorage 持久化作用域：多标签页场景各标签独立 */
const storageScope = computed(() => props.sessionKey || props.chatScope);

const sessionBootstrap = readChatSessionBootstrap(storageScope.value, {
  conversationId:
    typeof route.query.conversationId === "string" ? route.query.conversationId : "",
});

const started = ref(sessionBootstrap.started);
const loadingHistory = ref(sessionBootstrap.loadingHistory);
const input = ref(sessionBootstrap.input);
const sending = ref(false);
const resumingCheckpoint = ref(null);
const messages = ref(sessionBootstrap.messages);
const messagesRef = ref(null);
const composerRef = ref(null);
const citationPreviewShow = ref(false);
const citationPreviewTarget = ref(null);
const citationPreviewQuestion = ref("");
const reportViewMode = ref("answer");
const reportMindmapRef = ref(null);
const exportingWord = ref(false);
const savingToLibrary = ref(false);
const savedLibraryDocumentId = ref(null);
const exportingMindmap = ref("");
let streamAbort = null;
let streamGeneration = 0;
let persistTimer = null;
/** 本析智能思考计时 */
let thinkingTimer = null;
const thinkingStartTime = ref(0);
const elapsedMs = ref(0);
/** 长对话只渲染最近 N 条，更早消息按需加载 */
const messageWindowStart = ref(sessionBootstrap.messageWindowStart);
/** KeepAlive 失活时不渲染 Markdown DOM，仅保留纯文本占位 */
const chatDomActive = ref(true);
const loadingConversationId = ref("");
const expandedMessageIndexes = ref(new Set());
const historyHasOlder = ref(false);
const historyOldestId = ref(null);
const loadingOlderHistory = ref(false);

if (sessionBootstrap.conversationId) {
  conversationId.value = sessionBootstrap.conversationId;
}

/* 向父组件报告流式 / 内容状态（多标签页状态灯） */
function hasConversationContent() {
  for (const m of messages.value) {
    if (m.role === "user" && (m.content || "").trim()) return true;
  }
  return false;
}

/** 用最后一条 AI 回复内容或用户问题作为对话标题 */
function getConversationTitle() {
  // 优先用最后一条 assistant 内容
  for (let i = messages.value.length - 1; i >= 0; i -= 1) {
    const m = messages.value[i];
    if (m.role === "assistant" && (m.content || "").trim()) {
      return m.content.trim().slice(0, 15);
    }
  }
  // 没有 assistant 回复则用最后一条用户消息摘要
  for (let i = messages.value.length - 1; i >= 0; i -= 1) {
    const m = messages.value[i];
    if (m.role === "user" && (m.content || "").trim()) {
      return m.content.trim().slice(0, 15);
    }
  }
  return "";
}

function reportChatState() {
  props.onChatStateChange?.({
    streaming: sending.value,
    hasContent: hasConversationContent(),
    title: getConversationTitle(),
  });
}

if (props.onChatStateChange) {
  watch(sending, reportChatState);
  watch(messages, reportChatState, { deep: true });
  /* 首次报告状态 */
  nextTick(reportChatState);
  /* KeepAlive 切回时重新报告（watcher 在 deactivate 期间被暂停） */
  onActivated(reportChatState);
}

/** 本析智能：开始/停止思考计时 */
watch(sending, (val) => {
  if (val && props.chatScope === "ai-home") {
    thinkingStartTime.value = Date.now();
    elapsedMs.value = 0;
    thinkingTimer = setInterval(() => {
      elapsedMs.value = Date.now() - thinkingStartTime.value;
    }, 200);
  } else {
    if (thinkingTimer) {
      clearInterval(thinkingTimer);
      thinkingTimer = null;
    }
  }
});

const hiddenOlderCount = computed(() => messageWindowStart.value);
const canLoadOlder = computed(() => hiddenOlderCount.value > 0 || historyHasOlder.value);

const displayEntries = computed(() =>
  messages.value
    .slice(messageWindowStart.value)
    .map((message, offset) => ({
      message,
      index: messageWindowStart.value + offset,
    }))
);

async function showOlderMessages() {
  if (hiddenOlderCount.value > 0) {
    messageWindowStart.value = Math.max(0, messageWindowStart.value - 20);
    return;
  }
  if (!historyHasOlder.value || !historyOldestId.value || loadingOlderHistory.value) return;
  if (!props.chatScope || !conversationId.value) return;
  loadingOlderHistory.value = true;
  try {
    const data = await fetchChatConversationMessages(props.chatScope, conversationId.value, {
      limit: 24,
      beforeId: historyOldestId.value,
    });
    const older = Array.isArray(data?.messages) ? data.messages : [];
    historyHasOlder.value = Boolean(data?.has_older);
    historyOldestId.value = data?.oldest_id || historyOldestId.value;
    if (!older.length) {
      historyHasOlder.value = false;
      return;
    }
    const mapped = older.map((m) => ({
      role: m.role,
      content: m.content,
      streaming: false,
    }));
    messages.value = trimChatMessages([...mapped, ...messages.value]);
    messageWindowStart.value += mapped.length;
  } catch (e) {
    ui.error(e.message || t("chat.loadFailed"));
  } finally {
    loadingOlderHistory.value = false;
  }
}

function shouldRenderRich(entry) {
  if (hasAssistantAnswer(entry.message)) return true;
  if (markdownHasAuthScreenshot(entry.message.content)) return true;
  if (
    props.showReportTools &&
    entry.message.role === "assistant" &&
    (entry.message.content || "").trim()
  ) {
    return true;
  }
  return shouldRenderMessageRich({
    messageIndex: entry.index,
    totalMessages: messages.value.length,
    message: entry.message,
    chatDomActive: chatDomActive.value,
    expandedIndexes: expandedMessageIndexes.value,
  });
}

function messageScreenshots(message) {
  if (!message) return [];
  if (Array.isArray(message.browserScreenshots) && message.browserScreenshots.length) {
    return message.browserScreenshots;
  }
  return collectScreenshotAttachmentCandidates(message.content || "");
}

function hasAssistantAnswerText(message) {
  return Boolean(String(message?.content || "").trim());
}

function hasAssistantAnswer(message) {
  return hasAssistantAnswerText(message) || messageScreenshots(message).length > 0;
}

function syncMessageScreenshots(row) {
  if (!row) return;
  const fromAttachments = (row.browserScreenshots || []).map((shot) => ({
    type: "image",
    url: shot.url,
    title: shot.title,
  }));
  const shots = collectScreenshotAttachmentCandidates(row.content || "", fromAttachments);
  if (shots.length) row.browserScreenshots = shots;
}

function expandMessage(index) {
  const next = new Set(expandedMessageIndexes.value);
  next.add(index);
  expandedMessageIndexes.value = next;
}

watch(
  () => messages.value.length,
  (len, prevLen) => {
    if (loadingOlderHistory.value) return;
    if (len <= MAX_VISIBLE_CHAT_MESSAGES) {
      messageWindowStart.value = 0;
      return;
    }
    if (len > prevLen) {
      messageWindowStart.value = Math.max(messageWindowStart.value, len - MAX_VISIBLE_CHAT_MESSAGES);
    }
  }
);

const attachmentSessionId = ref(sessionBootstrap.attachmentSessionId);
const attachmentFiles = ref(sessionBootstrap.attachmentFiles);
const uploadingAttachments = ref(false);
const attachmentInputRef = ref(null);

const agentCatalog = ref([]);
const agentCatalogLoading = ref(false);
const agentPopoverShow = ref(false);
const agentCatalogLoaded = ref(false);

const skillCatalog = ref([]);
const skillCatalogLoading = ref(false);
const skillPopoverShow = ref(false);
const skillCatalogLoaded = ref(false);
const thirdPartyAiPopoverShow = ref(false);

const thirdPartyAiOptions = [
  { key: "doubao", label: "豆包", desc: "字节跳动自研 AI，通用对话能力强、支持文字生图、反应快、免费额度充足" },
  { key: "qwen", label: "通义千问", desc: "阿里云通义系列，擅长中文创作与知识问答、支持通义万相生图、输出质量高" },
  { key: "deepseek", label: "DeepSeek", desc: "DeepSeek 推理模型，代码编程与逻辑推理能力突出、深度思考模式、适合技术问题" },
];
const reportSkillPopoverShow = ref(false);
const reportOptimizePopoverShow = ref(false);

async function loadAgentCatalog() {
  if (agentCatalogLoading.value) return;
  agentCatalogLoading.value = true;
  try {
    agentCatalog.value = (await fetchAiChatAgentCatalog()) || [];
    agentCatalogLoaded.value = true;
  } catch (e) {
    ui.error(e.message || t("chat.agentSkills.loadFailed"));
  } finally {
    agentCatalogLoading.value = false;
  }
}

async function onAgentPopoverShowChange(show) {
  agentPopoverShow.value = show;
  if (show && !agentCatalogLoaded.value) {
    await loadAgentCatalog();
  }
}

function useAgent(agent) {
  const label = formatAgentDisplayName(agent.title);
  input.value = `请让 ${label}：`;
  agentPopoverShow.value = false;
  nextTick(() => composerRef.value?.focus?.());
}

async function loadSkillCatalog() {
  if (skillCatalogLoading.value) return;
  skillCatalogLoading.value = true;
  try {
    skillCatalog.value = (await fetchAiChatSkillCatalog()) || [];
    skillCatalogLoaded.value = true;
  } catch (e) {
    ui.error(e.message || t("chat.agentSkills.skillLoadFailed"));
  } finally {
    skillCatalogLoading.value = false;
  }
}

async function onSkillPopoverShowChange(show) {
  skillPopoverShow.value = show;
  if (show && !skillCatalogLoaded.value) {
    await loadSkillCatalog();
  }
}

function useSkill(skill) {
  const label = (skill.title || skill.name || "").trim();
  if (!label) return;
  input.value = `请使用 ${label} 技能：`;
  skillPopoverShow.value = false;
  nextTick(() => composerRef.value?.focus?.());
}

const THIRD_PARTY_AI_PREFIXES = {
  doubao: "#豆包",
  qwen: "#千问",
  deepseek: "#DeepSeek",
};

function onThirdPartyAiPopoverShowChange(show) {
  thirdPartyAiPopoverShow.value = show;
}

function useThirdPartyAi(opt) {
  const prefixUsed = THIRD_PARTY_AI_PREFIXES[opt.key] || `#${opt.label}`;
  input.value = `${prefixUsed} `;
  thirdPartyAiPopoverShow.value = false;
  nextTick(() => composerRef.value?.focus?.());
}

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
  savedLibraryDocumentId.value = null;
});

function isReportMessage(index, message) {
  return (
    props.showReportTools &&
    index === lastAssistantIndex.value &&
    message.role === "assistant" &&
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

async function saveReportToLibrary(content) {
  if (!props.reportLibraryImport || savingToLibrary.value) return;
  savingToLibrary.value = true;
  try {
    const res = await props.reportLibraryImport({
      title: lastReportTitle.value,
      markdown: content,
    });
    savedLibraryDocumentId.value = res?.document_id || null;
    ui.success(res?.message || t("reportGeneration.saveToLibrarySuccess"));
  } catch (e) {
    ui.error(e.message || t("reportGeneration.saveToLibraryFailed"));
  } finally {
    savingToLibrary.value = false;
  }
}

function openSavedLibraryDocument() {
  if (!savedLibraryDocumentId.value) return;
  router.push({ name: "document-detail", params: { id: savedLibraryDocumentId.value } });
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
  const aligned = alignCitationsWithContent(message?.content, message?.citations || []);
  return splitCitedCitations(aligned.content, aligned.citations);
}

function messageCitationView(message) {
  return alignCitationsWithContent(message?.content, message?.citations || []);
}

function reportQuestionForMessage(index) {
  for (let i = index - 1; i >= 0; i -= 1) {
    if (messages.value[i]?.role === "user") {
      return messages.value[i].content || "";
    }
  }
  return "";
}

function onReportCitationClick(index, message, messageIndex) {
  const groups = reportCitationGroups(message);
  const all = [...groups.local, ...groups.web];
  openCitationPreview(index, all, reportQuestionForMessage(messageIndex));
}

function useReportOptimizePreset(preset) {
  const prompt = (preset?.prompt || preset?.description || preset?.label || "").trim();
  if (!prompt) return;
  input.value = prompt;
  reportOptimizePopoverShow.value = false;
  nextTick(() => composerRef.value?.focus?.());
}

function useReportAgentSkill(skill) {
  const prompt = String(skill?.sample_prompt || skill?.samplePrompt || "").trim();
  if (!prompt) return;
  input.value = prompt;
  reportSkillPopoverShow.value = false;
  nextTick(() => composerRef.value?.focus?.());
}

function openCitationPreview(citationOrIndex, citations = [], question = "") {
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
    openExternal(citation.url);
    return;
  }
  citationPreviewQuestion.value = question || "";
  citationPreviewTarget.value = citation;
  citationPreviewShow.value = true;
}

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
/** 对话中从 1 行起随内容增高，不出现滚动条 */
const chatComposerRows = computed(() => ({ minRows: 1, maxRows: 6 }));

function emptyWorkflow() {
  return emptyAgentWorkflow();
}

const useCompactWorkflowProgress = computed(() => props.chatScope === "ai-home");

function applyWorkflowEvent(workflow, ev) {
  return applyAgentWorkflowEvent(workflow, ev, t, {
    currentStepOnly: useCompactWorkflowProgress.value,
  });
}

function workflowHasStepList(workflow) {
  if (!workflow) return false;
  if ((workflow.steps?.length ?? 0) > 0) return true;
  if ((workflow.taskPlan?.length ?? 0) > 0) return true;
  if (workflow.pendingConfirmation?.status === "awaiting") return true;
  if (workflow.pendingChoice?.status === "awaiting") return true;
  return false;
}
function workflowHasVisibleProgress(workflow) {
  if (!workflow) return false;
  if (workflow.running) return true;
  if ((workflow.steps?.length ?? 0) > 0) return true;
  if ((workflow.taskPlan?.length ?? 0) > 0) return true;
  return Boolean(sanitizeWorkflowDisplayText(workflow.currentTitle));
}

function workflowAwaitingAnswer(message) {
  if ((message?.content || "").trim()) return false;
  if (messageScreenshots(message).length) return false;
  const workflow = message?.workflow;
  if (!workflow || !workflowHasVisibleProgress(workflow)) return false;
  return Boolean(message?.streaming || workflow.running);
}

function assistantConclusionContent(message) {
  if (!message) return "";
  if (props.linkifyCitations && hasAssistantAnswerText(message)) {
    return messageCitationView(message).content;
  }
  return message.content || "";
}

function workflowCurrentStepText(workflow) {
  if (!workflow) return "";
  const running = getWorkflowRunningSegment(workflow);
  if (running) return formatWorkflowRunningLine(workflow, running, t("agentWorkflow.executingAgent"));
  const current = sanitizeWorkflowDisplayText(workflow.currentTitle);
  if (current) return current;
  for (const task of workflow.taskPlan || []) {
    if (task.status === "running" && task.title) return task.title;
  }
  return "";
}

function formatElapsed(ms) {
  const totalSec = Math.floor(ms / 1000);
  if (totalSec < 60) return `已处理 ${totalSec} 秒`;
  const min = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  return `已处理 ${min} 分 ${sec} 秒`;
}

function workflowAnswerStatusText(workflow) {
  if (!workflow) return "";
  const running = workflowCurrentStepText(workflow);
  if (running) return running;
  return sanitizeWorkflowDisplayText(workflow.planResult) || "";
}

function clearFollowUpQuestions() {
  for (const msg of messages.value) {
    if (msg.followUpQuestions) delete msg.followUpQuestions;
  }
}

function applyFollowUpQuestions(row, questions) {
  if (props.chatScope !== "ai-home" || !row) return;
  if (!Array.isArray(questions) || !questions.length) return;
  row.followUpQuestions = questions.filter((q) => String(q || "").trim());
}

function showFollowUpForMessage(index, message) {
  if (props.chatScope !== "ai-home") return false;
  if (message?.role !== "assistant" || message.streaming || message.error) return false;
  if (!Array.isArray(message.followUpQuestions) || !message.followUpQuestions.length) {
    return false;
  }
  for (let i = messages.value.length - 1; i >= 0; i -= 1) {
    if (messages.value[i]?.role === "assistant") {
      return i === index;
    }
  }
  return false;
}

function useFollowUpQuestion(text) {
  const q = String(text || "").trim();
  if (!q || sending.value) return;
  sendMessage(q);
}

async function scrollToBottom() {
  await nextTick();
  const el = messagesRef.value;
  if (el) el.scrollTop = el.scrollHeight;
}

function buildChatHistory() {
  if (props.chatScope === "report-generation") {
    return trimHistoryForApi(messages.value, {
      maxMessages: MAX_REPORT_HISTORY_FOR_API,
      maxChars: MAX_REPORT_HISTORY_CHARS,
    });
  }
  return trimHistoryForApi(messages.value);
}

async function sendMessageStreaming(content, assistantIdx, history) {
  streamAbort?.abort();
  streamAbort = new AbortController();

  let scrollTick = 0;
  let typewriterActive = false;
  const streamedScreenshotBlocks = [];

  function applyScreenshotAttachments(row, attachments) {
    if (!row || !Array.isArray(attachments)) return;
    if (!row.browserScreenshots) row.browserScreenshots = [];
    for (const att of attachments) {
      if (att?.type !== "image" || !att.url) continue;
      const src = normalizeChatAttachmentUrl(att.url);
      if (!src) continue;
      const title = att.title || "浏览器截图";
      const block = `![${title}](${src})`;
      if (!streamedScreenshotBlocks.includes(block)) {
        streamedScreenshotBlocks.push(block);
      }
      if (!row.browserScreenshots.some((shot) => shot.url === src)) {
        row.browserScreenshots.push({ url: src, title });
      }
    }
    row.content = mergeAuthScreenshotMarkdownBlocks(
      row.content || "",
      streamedScreenshotBlocks
    );
  }

  function mergeScreenshotBlocksIntoContent(text) {
    return mergeAuthScreenshotMarkdownBlocks(text, streamedScreenshotBlocks);
  }

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
          handleAgentWorkflowForNotifications(ev);
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
          const formatted = mergeScreenshotBlocksIntoContent(text);
          if (row.content) {
            // 已有部分流式内容，直接替换（做后续格式修正）
            row.content = formatted;
            syncMessageScreenshots(row);
            scrollToBottom();
          } else {
            // 无流式内容，用打字机动画逐步展示（避免探针路径等场景全文蹦出）
            typewriterActive = true;
            revealContentTypewriter(row, formatted);
          }
        },
        onCitations: (citations) => {
          if ((!props.showCitations && !props.showReportTools) || !Array.isArray(citations)) return;
          const row = messages.value[assistantIdx];
          if (row) row.citations = citations;
        },
        onAttachments: (attachments) => {
          const row = messages.value[assistantIdx];
          applyScreenshotAttachments(row, attachments);
          scrollToBottom();
        },
        onDelta: (delta) => {
          const row = messages.value[assistantIdx];
          if (!row) return;
          row.content += delta;
          syncMessageScreenshots(row);
          scrollTick += 1;
          if (scrollTick % 4 === 0) scrollToBottom();
        },
        onError: (err) => {
          const row = messages.value[assistantIdx];
          if (row?.content?.trim()) {
            row.streaming = false;
            if (row.workflow) {
              row.workflow.running = false;
            }
            return;
          }
          if (row) {
            row.streaming = false;
            const wfErr = row.workflow ? getWorkflowLastError(row.workflow) : "";
            if (!wfErr) {
              row.error = true;
            }
            row.content = err?.message?.trim() || wfErr || t("chat.sorryRetry");
            if (row.workflow) {
              row.workflow.running = false;
            }
          }
          ui.error(err?.message || t("chat.sendFailed"));
        },
        onDone: (payload) => {
          if (
            !payload?.done &&
            !String(payload?.reply || "").trim() &&
            !(Array.isArray(payload?.attachments) && payload.attachments.length) &&
            !payload?.conversation_id
          ) {
            return;
          }
          const row = messages.value[assistantIdx];
          if (row) {
            applyScreenshotAttachments(row, payload?.attachments);
            if (payload?.suspended) {
              // Checkpoint 暂停：保留 workflow 状态（含 checkpointId），前端展示暂停标记
              row.streaming = false;
              row.suspended = true;
              row.checkpointId = payload.checkpoint_id || null;
            } else if (!typewriterActive) {
              // 打字机动画进行中时，不覆盖逐字展示的内容，由动画最终设置完整文本
              const merged = mergeScreenshotBlocksIntoContent(
                payload?.reply || row.content || ""
              );
              if (merged) {
                row.content = merged;
              }
              row.streaming = false;
            }
            syncMessageScreenshots(row);
            if (row.workflow) {
              row.workflow.running = false;
            }
            if (props.showCitations || props.showReportTools) {
              if (Array.isArray(payload?.citations)) {
                row.citations = payload.citations;
              }
            }
            applyFollowUpQuestions(row, payload?.follow_up_questions);
          }
          if (payload?.conversation_id) {
            conversationId.value = payload.conversation_id;
          }
          /* 每次智能体回复完毕后更新标签标题 */
          reportChatState();
        },
        onFollowUpQuestions: (questions) => {
          const row = messages.value[assistantIdx];
          applyFollowUpQuestions(row, questions);
        },
        onConversationId: (id) => {
          if (id) conversationId.value = id;
        },
      }
    );
    const row = messages.value[assistantIdx];
    if (row && !typewriterActive) {
      row.streaming = false;
      if (row.workflow) {
        row.workflow.running = false;
      }
      if (!row.content.trim()) {
        row.content = "";
      }
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

/** 从 checkpoint 恢复 Agent 执行。 */
async function resumeCheckpoint(checkpointId, assistantIdx, accepted) {
  const { resumeCheckpointStream } = await import("../api/rag.js");
  resumingCheckpoint.value = checkpointId;
  const row = messages.value[assistantIdx];
  if (row) {
    row.streaming = true;
    row.suspended = false;
  }

  try {
    await resumeCheckpointStream(checkpointId, { accepted })(
      {
        onDelta: (delta) => {
          if (row) row.content += delta;
        },
        onReplace: (text) => {
          if (row) row.content = text;
        },
        onWorkflow: (ev) => {
          if (!row) return;
          if (!row.workflow) row.workflow = emptyWorkflow();
          applyWorkflowEvent(row.workflow, ev);
        },
        onCitations: (citations) => {
          if (row && (props.showCitations || props.showReportTools)) {
            row.citations = citations;
          }
        },
        onAttachments: (attachments) => {
          if (row) applyScreenshotAttachments(row, attachments);
        },
        onFollowUpQuestions: (questions) => {
          if (row) applyFollowUpQuestions(row, questions);
        },
        onConversationId: (id) => {
          if (id) conversationId.value = id;
        },
        onError: (err) => {
          if (row) {
            row.streaming = false;
            if (!row.content.trim()) row.error = true;
          }
          ui.error(err?.message || "恢复执行失败");
        },
        onDone: (payload) => {
          if (row) {
            if (payload?.reply) {
              row.content = payload.reply;
            }
            row.streaming = false;
            if (row.workflow) row.workflow.running = false;
            row.suspended = false;
            row.checkpointId = null;
          }
          if (payload?.conversation_id) conversationId.value = payload.conversation_id;
          reportChatState();
        },
      }
    );
  } catch (err) {
    if (row) {
      row.streaming = false;
      row.suspended = false;
    }
    ui.error(err?.message || "恢复执行失败");
  } finally {
    resumingCheckpoint.value = null;
  }
}

/** 从 checkpoint 恢复，带方案选择。 */
async function resumeCheckpointWithChoice(checkpointId, assistantIdx, choice) {
  resumingCheckpoint.value = checkpointId;
  const row = messages.value[assistantIdx];
  if (row) {
    row.streaming = true;
    row.suspended = false;
  }

  try {
    const { resumeCheckpointStream } = await import("../api/rag.js");
    await resumeCheckpointStream(checkpointId, { choice })(
      {
        onDelta: (delta) => { if (row) row.content += delta; },
        onReplace: (text) => { if (row) row.content = text; },
        onWorkflow: (ev) => {
          if (!row) return;
          if (!row.workflow) row.workflow = emptyWorkflow();
          applyWorkflowEvent(row.workflow, ev);
        },
        onCitations: (citations) => { if (row && props.showCitations) row.citations = citations; },
        onAttachments: (attachments) => { if (row) applyScreenshotAttachments(row, attachments); },
        onFollowUpQuestions: (questions) => { if (row) applyFollowUpQuestions(row, questions); },
        onConversationId: (id) => { if (id) conversationId.value = id; },
        onError: (err) => {
          if (row) { row.streaming = false; if (!row.content.trim()) row.error = true; }
          ui.error(err?.message || "恢复执行失败");
        },
        onDone: (payload) => {
          if (row) {
            if (payload?.reply) row.content = payload.reply;
            row.streaming = false;
            if (row.workflow) row.workflow.running = false;
            row.suspended = false;
            row.checkpointId = null;
          }
          if (payload?.conversation_id) conversationId.value = payload.conversation_id;
          reportChatState();
        },
      }
    );
  } catch (err) {
    if (row) { row.streaming = false; row.suspended = false; }
    ui.error(err?.message || "恢复执行失败");
  } finally {
    resumingCheckpoint.value = null;
  }
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
    applyFollowUpQuestions(row, data?.follow_up_questions);
  }
}

async function sendMessage(text) {
  const content = (text ?? input.value).trim();
  if (!content) return;

  if (sending.value) return;

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

  clearFollowUpQuestions();

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
        workflow: props.showWorkflowProgress
          ? {
              ...emptyWorkflow(),
              running: true,
              currentTitle: t("chat.thinking"),
            }
          : null,
      });
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
        row.content = e.message?.trim() || t("chat.sorryRetry");
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
    persistSessionState({ immediate: true });
  }
}

function onComposerKeydown(e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    if (sending.value) return;
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

function canShowMessageActions(index, message) {
  if (loadingHistory.value || message?.streaming) return false;
  if (message?.role !== "assistant") return false;
  if (!hasAssistantAnswer(message)) return false;
  return findUserIndexBefore(index) >= 0;
}

async function copyAssistantMessage(message) {
  await copyChatMessageText(message?.content, { ui, t });
}

async function shareAssistantMessage(message) {
  await shareChatMessageText(message?.content, {
    ui,
    t,
    title: props.title,
    shareUrl: buildChatShareUrl(conversationId.value, props.chatScope),
  });
}

function setMessageFeedback(index, value) {
  const message = messages.value[index];
  if (!message) return;
  message.feedback = value;
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

function persistSessionState({ immediate = false } = {}) {
  if (!storageScope.value) return;
  const run = () => {
    const serialized = serializeChatMessages(messages.value);
    if (!serialized.length && !conversationId.value && !input.value.trim() && !attachmentSessionId.value) {
      clearChatSession(storageScope.value);
      return;
    }
    saveChatSession(storageScope.value, {
      conversationId: conversationId.value,
      messages: serialized,
      started: started.value,
      input: input.value,
      attachmentSessionId: attachmentSessionId.value,
      attachmentFiles: attachmentFiles.value,
    });
  };
  if (immediate) {
    if (persistTimer) {
      clearTimeout(persistTimer);
      persistTimer = null;
    }
    run();
    return;
  }
  if (persistTimer) clearTimeout(persistTimer);
  persistTimer = setTimeout(() => {
    persistTimer = null;
    run();
  }, sending.value ? 1200 : 200);
}

function newChat() {
  streamAbort?.abort();
  streamAbort = null;
  sending.value = false;
  started.value = false;
  messages.value = [];
  messageWindowStart.value = 0;
  expandedMessageIndexes.value = new Set();
  historyHasOlder.value = false;
  historyOldestId.value = null;
  input.value = "";
  conversationId.value = null;
  clearAttachmentState();
  if (storageScope.value) clearChatSession(storageScope.value);
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

function routeConversationId() {
  const id = route.query.conversationId;
  return typeof id === "string" ? id.trim() : "";
}

function syncConversationFromRoute() {
  const cid = routeConversationId();
  if (!cid || !props.chatScope || !SERVER_HISTORY_SCOPES.has(props.chatScope)) return;
  if (loadingConversationId.value === cid && loadingHistory.value) return;
  if (cid === conversationId.value && messages.value.length && !loadingHistory.value) {
    started.value = true;
    chatDomActive.value = true;
    return;
  }
  void loadConversationFromId(cid);
}

async function loadConversationFromId(id) {
  if (!props.chatScope || !id) return;
  if (!SERVER_HISTORY_SCOPES.has(props.chatScope)) {
    loadingHistory.value = false;
    return;
  }
  if (loadingConversationId.value === id && loadingHistory.value) return;
  loadingConversationId.value = id;
  loadingHistory.value = true;
  try {
    const data = await fetchChatConversationMessages(props.chatScope, id, {
      limit: MAX_CHAT_MESSAGES,
    });
    if (loadingConversationId.value !== id) return;
    const rows = Array.isArray(data?.messages) ? data.messages : [];
    historyHasOlder.value = Boolean(data?.has_older);
    historyOldestId.value = data?.oldest_id || null;
    expandedMessageIndexes.value = new Set();
    streamAbort?.abort();
    streamAbort = null;
    sending.value = false;
    messages.value = trimChatMessages(
      rows.map((m) => {
        const row = {
          role: m.role,
          content: m.content ?? "",
          streaming: false,
        };
        syncMessageScreenshots(row);
        return row;
      })
    );
    conversationId.value = id;
    started.value = messages.value.length > 0;
    messageWindowStart.value = Math.max(0, messages.value.length - MAX_VISIBLE_CHAT_MESSAGES);
    input.value = "";
    await scrollToBottom();
    persistSessionState({ immediate: true });
  } catch (e) {
    ui.error(e.message || t("chat.loadFailed"));
  } finally {
    loadingHistory.value = false;
    if (loadingConversationId.value === id) loadingConversationId.value = "";
  }
}

async function restorePersistedSession() {
  if (!storageScope.value) return;
  const saved = loadChatSession(storageScope.value);
  if (!saved) return;

  const sid = saved.attachmentSessionId || attachmentSessionId.value;
  if (sid) {
    attachmentSessionId.value = sid;
    if (!attachmentFiles.value.length && Array.isArray(saved.attachmentFiles)) {
      attachmentFiles.value = saved.attachmentFiles;
    }
    await refreshAttachmentList(sid);
  }

  if (SERVER_HISTORY_SCOPES.has(storageScope.value) && saved.conversationId) {
    if (!messages.value.length) {
      await loadConversationFromId(saved.conversationId);
    }
    return;
  }

  if (messages.value.length) {
    await scrollToBottom();
  }
}

watch(() => route.query.conversationId, syncConversationFromRoute);

onMounted(async () => {
  const cid = routeConversationId();
  if (cid) {
    syncConversationFromRoute();
    return;
  }
  await restorePersistedSession();
});

onDeactivated(() => {
  chatDomActive.value = false;
  expandedMessageIndexes.value = new Set();
  citationPreviewShow.value = false;
  agentPopoverShow.value = false;
  skillPopoverShow.value = false;
  reportSkillPopoverShow.value = false;
  reportOptimizePopoverShow.value = false;
  // 面板失活时仅释放富文本 DOM / 图表实例；流式请求继续在后台更新 messages
  if (messagesRef.value) disposeRichContentInElement(messagesRef.value);
  reportViewMode.value = "answer";
  if (messages.value.length > MAX_VISIBLE_CHAT_MESSAGES) {
    messages.value = trimChatMessages(messages.value);
    messageWindowStart.value = Math.max(0, messages.value.length - MAX_VISIBLE_CHAT_MESSAGES);
  }
  /* 停止思考计时，切回时重新开始 */
  if (thinkingTimer) {
    clearInterval(thinkingTimer);
    thinkingTimer = null;
  }
  persistSessionState({ immediate: true });
});

onActivated(async () => {
  chatDomActive.value = true;
  syncConversationFromRoute();
  if (!messages.value.length && storageScope.value) {
    await restorePersistedSession();
  }
  /* 从后台切回时重启思考计时 */
  if (sending.value && props.chatScope === "ai-home" && !thinkingTimer) {
    thinkingStartTime.value = Date.now() - elapsedMs.value;
    thinkingTimer = setInterval(() => {
      elapsedMs.value = Date.now() - thinkingStartTime.value;
    }, 200);
  }
  /* 重新报告状态：watcher 在 deactivate 期间被暂停，
     若后台流已完成，tabStreaming 尚未更新会显示为仍在加载 */
  reportChatState();
  if ((started.value || sending.value) && !loadingHistory.value) scrollToBottom();
});

onBeforeUnmount(() => {
  if (persistTimer) {
    clearTimeout(persistTimer);
    persistTimer = null;
  }
  if (thinkingTimer) {
    clearInterval(thinkingTimer);
    thinkingTimer = null;
  }
  /* KeepAlive 驱逐缓存时：不中止流式请求，让其在后台自然完成。
     onDone 会更新内容，finally 块会持久化正确状态到 sessionStorage，
     避免 catch(AbortError) 中的 finalizeStoppedAssistant 写入「已停止生成」。 */
  if (sending.value) {
    streamGeneration += 1;
    /* 注意：不调 streamAbort?.abort() */
  }
  persistSessionState({ immediate: true });
});

defineExpose({
  newChat,
  goToHistory,
  loadingHistory,
  applyReportAgentSkill: useReportAgentSkill,
  /** 获取对话标题（首条用户消息或末条用户消息 */
  getConversationTitle: () => {
    for (const m of messages.value) {
      if (m.role === "user" && (m.content || "").trim()) {
        return (m.content || "").trim().slice(0, 60);
      }
    }
    return "";
  },
  messages,
});
</script>

<template>
  <div
    class="ai-home"
    :class="{ 'ai-home--active': started }"
    v-bind="$attrs"
  >
    <div v-if="!started && chatScope && showPanelSessionActions" class="ai-home-landing-topbar">
      <IconAction
        :label="t('chat.viewHistory')"
        :icon="TimeOutline"
        :disabled="loadingHistory"
        @click="goToHistory"
      />
    </div>

    <Transition name="ai-chat-header">
      <header
        v-if="started && (showChatHeaderBrand || showPanelSessionActions)"
        class="ai-home-chat-header"
        :class="{ 'ai-home-chat-header--minimal': !showChatHeaderBrand }"
      >
        <div v-if="showChatHeaderBrand" class="ai-home-chat-brand">
          <div class="ai-home-icon ai-home-icon--sm">
            <n-icon :size="24" :component="icon" />
          </div>
          <div>
            <div class="ai-home-chat-title">{{ title }}</div>
            <div class="ai-home-chat-sub">{{ headerSub }}</div>
          </div>
        </div>
        <div v-if="showPanelSessionActions" class="ai-home-chat-actions">
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
              <n-icon :size="43" :component="icon" />
            </div>
            <h1 class="ai-home-title" :class="{ 'platform-text-gradient': titleGradient }">
              {{ title }}
            </h1>
            <p v-if="description" class="ai-home-desc">{{ description }}</p>
            <p v-if="subtitle" class="ai-home-sub">{{ subtitle }}</p>
            <div v-if="architectureData.summary" class="ai-home-arch">
              <p class="ai-home-arch-summary">{{ architectureData.summary }}</p>
            </div>
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
            v-if="canLoadOlder"
            key="load-older"
            class="ai-home-load-older"
          >
            <button
              type="button"
              class="ai-home-load-older__btn"
              :disabled="loadingOlderHistory"
              @click="showOlderMessages"
            >
              <n-spin v-if="loadingOlderHistory" :size="17" />
              <span v-else-if="hiddenOlderCount > 0">
                {{ t("chat.loadOlderMessages", { count: hiddenOlderCount }) }}
              </span>
              <span v-else>{{ t("chat.loadOlderFromServer") }}</span>
            </button>
          </div>
          <div
            v-for="entry in displayEntries"
            :key="`msg-${entry.index}`"
            class="ai-home-msg"
            :class="entry.message.role === 'user' ? 'ai-home-msg--user' : 'ai-home-msg--bot'"
          >
            <div
              class="ai-home-msg-stack"
              :class="entry.message.role === 'user' ? 'ai-home-msg-stack--user' : 'ai-home-msg-stack--bot'"
            >
            <div
              v-if="entry.message.role === 'assistant'"
              class="ai-home-bubble ai-home-bubble--bot"
              :class="{
                'ai-home-bubble--error': entry.message.error,
                'ai-home-bubble--streaming': entry.message.streaming}"
            >
              <AgentWorkflowProgress
                v-if="
                  showWorkflowProgress &&
                  !useCompactWorkflowProgress &&
                  workflowHasStepList(entry.message.workflow)
                "
                :workflow="entry.message.workflow"
                :keep-visible-after-done="true"
                :awaiting-reply="entry.message.streaming && !entry.message.content"
                :show-live-status="false"
                compact
              />
              <div
                v-else-if="
                  entry.message.streaming &&
                  !entry.message.content &&
                  !(showWorkflowProgress && workflowAwaitingAnswer(entry.message)) &&
                  !useCompactWorkflowProgress
                "
                class="ai-answer-status platform-inline-loading ai-thinking"
              >
                <RoseLoader class="ai-answer-status__rose" :size="24" />
                <span class="ai-answer-status-text">{{ t("chat.thinking") }}</span>
              </div>
              <!-- 本析智能：已处理时长 + 分割线（ai-home 作用域，流式且无内容时显示） -->
              <div
                v-if="
                  useCompactWorkflowProgress &&
                  entry.message.streaming &&
                  !entry.message.content
                "
                class="ai-thinking-elapsed"
              >
                <div class="ai-thinking-elapsed__header">
                  <span class="ai-thinking-elapsed__time">{{ formatElapsed(elapsedMs) }}</span>
                </div>
                <div class="ai-thinking-elapsed__divider"></div>
              </div>
              <AgentWorkflowCompactProgress
                v-if="showWorkflowProgress && workflowAwaitingAnswer(entry.message) && useCompactWorkflowProgress"
                :workflow="entry.message.workflow"
              />
              <div
                v-else-if="showWorkflowProgress && workflowAwaitingAnswer(entry.message)"
                class="ai-answer-status platform-inline-loading ai-workflow-current"
              >
                <RoseLoader class="ai-answer-status__rose" :size="24" />
                <span
                  v-if="entry.message.workflow?.currentAgentTitle"
                  class="ai-workflow-current__agent"
                >
                  {{ entry.message.workflow.currentAgentTitle }}
                </span>
                <span class="ai-answer-status-text">{{
                  workflowAnswerStatusText(entry.message.workflow) || t("agentWorkflow.executing")
                }}</span>
              </div>
              <div
                v-if="
                  entry.message.streaming &&
                  (entry.message.content || messageScreenshots(entry.message).length) &&
                  !(showReportTools && isReportMessage(entry.index, entry.message))
                "
                class="ai-home-stream-md"
              >
                <AssistantConclusionContent
                  :content="assistantConclusionContent(entry.message)"
                  :rich-markdown="richMarkdown"
                  :browser-screenshots="entry.message.browserScreenshots"
                />
                <span v-if="entry.message.streaming" class="ai-home-cursor">▍</span>
              </div>
              <!-- Checkpoint 暂停恢复按钮 -->
              <div
                v-else-if="entry.message.suspended && entry.message.checkpointId"
                class="ai-home-suspended"
              >
                <div class="ai-suspended-info">
                  <NIcon size="20" class="ai-suspended-icon"><TimeOutline /></NIcon>
                  <span>{{ t("agentWorkflow.suspended") || "等待您的确认，点击下方按钮继续" }}</span>
                </div>
                <div class="ai-suspended-actions">
                  <NButton
                    size="small"
                    type="primary"
                    :loading="resumingCheckpoint === entry.message.checkpointId"
                    @click="resumeCheckpoint(entry.message.checkpointId, entry.index, true)"
                  >
                    {{ t("agentWorkflow.confirm") || "确认执行" }}
                  </NButton>
                  <NButton
                    size="small"
                    :loading="resumingCheckpoint === entry.message.checkpointId"
                    @click="resumeCheckpoint(entry.message.checkpointId, entry.index, false)"
                  >
                    {{ t("agentWorkflow.reject") || "取消" }}
                  </NButton>
                </div>
                <div
                  v-if="entry.message.workflow?.pendingConfirmation?.status === 'awaiting'"
                  class="ai-suspended-detail"
                >
                  {{ entry.message.workflow.pendingConfirmation.detail }}
                </div>
                <div
                  v-else-if="entry.message.workflow?.pendingChoice?.status === 'awaiting'"
                  class="ai-suspended-detail"
                >
                  <p>{{ entry.message.workflow.pendingChoice.question }}</p>
                  <div class="ai-suspended-choices">
                    <NButton
                      v-for="opt in (entry.message.workflow.pendingChoice.options || [])"
                      :key="opt"
                      size="tiny"
                      @click="resumeCheckpointWithChoice(entry.message.checkpointId, entry.index, opt)"
                    >
                      {{ opt }}
                    </NButton>
                  </div>
                </div>
              </div>
              <template v-else-if="shouldRenderRich(entry)">
              <template v-if="isReportMessage(entry.index, entry.message)">
                <div v-if="!entry.message.streaming" class="ai-report-tools">
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
                  v-if="!entry.message.streaming"
                  v-show="reportViewMode === 'mindmap'"
                  ref="reportMindmapRef"
                  :question="reportQuestionForMessage(entry.index)"
                  :answer="entry.message.content"
                  :fetch-mindmap="reportMindmapFetch"
                  :auto-load="true"
                  :active="reportViewMode === 'mindmap'"
                />
                <template v-if="reportViewMode !== 'mindmap'">
                  <div
                    class="ai-home-stream-md"
                    :class="{ 'ai-home-stream-md--report': entry.message.streaming }"
                  >
                    <KnowledgeChatContent
                      v-if="linkifyCitations && entry.message.content"
                      :key="`kc-report-${entry.index}`"
                      :content="reportCitationGroups(entry.message).content"
                      :citations="reportCitationGroups(entry.message).cited"
                      :defer-rich-media="entry.message.streaming"
                      @open-citation="(idx) => onReportCitationClick(idx, entry.message, entry.index)"
                    />
                    <MarkdownRichContent
                      v-else-if="richMarkdown && entry.message.content"
                      :key="`md-report-${entry.index}`"
                      :content="reportCitationGroups(entry.message).content || entry.message.content"
                      :defer-rich-media="entry.message.streaming"
                    />
                    <ChatMarkdownBody
                      v-else-if="entry.message.content"
                      :key="`md-plain-report-${entry.index}`"
                      :content="reportCitationGroups(entry.message).content || entry.message.content"
                    />
                    <span v-if="entry.message.streaming" class="ai-home-cursor">▍</span>
                  </div>
                  <AssistantConclusionContent
                    v-if="messageScreenshots(entry.message).length"
                    text-mode="gallery-only"
                    :content="entry.message.content"
                    :browser-screenshots="entry.message.browserScreenshots"
                  />
                  <ChatMessageCitations
                    v-if="!entry.message.streaming && reportCitationGroups(entry.message).cited.length"
                    class="ai-report-citations"
                    :citations="reportCitationGroups(entry.message).cited"
                    :question="reportQuestionForMessage(entry.index)"
                    :hint="t('reportGeneration.citationsClickHint')"
                    :preview-on-click="true"
                    @open-citation="
                      (c) => openCitationPreview(c, [], reportQuestionForMessage(entry.index))
                    "
                  />
                </template>
                <div v-if="reportWordExport || reportLibraryImport || reportViewMode === 'mindmap'" class="ai-report-export">
                  <template
                    v-if="
                      reportViewMode === 'answer' &&
                      !entry.message.streaming &&
                      (reportWordExport || reportLibraryImport)
                    "
                  >
                    <button
                      v-if="reportWordExport"
                      type="button"
                      class="ai-report-export__btn"
                      :disabled="exportingWord"
                      @click="exportReportWord(entry.message.content)"
                    >
                      <n-spin v-if="exportingWord" :size="17" />
                      <n-icon v-else :size="18" :component="DocumentTextOutline" />
                      <span>{{ t("reportGeneration.exportWord") }}</span>
                    </button>
                    <button
                      v-if="savedLibraryDocumentId"
                      type="button"
                      class="ai-report-export__btn ai-report-export__btn--primary"
                      @click="openSavedLibraryDocument"
                    >
                      <n-icon :size="18" :component="FolderOpenOutline" />
                      <span>{{ t("reportGeneration.viewDocument") }}</span>
                    </button>
                    <button
                      v-else-if="reportLibraryImport"
                      type="button"
                      class="ai-report-export__btn"
                      :disabled="savingToLibrary"
                      @click="saveReportToLibrary(entry.message.content)"
                    >
                      <n-spin v-if="savingToLibrary" :size="17" />
                      <n-icon v-else :size="18" :component="FolderOpenOutline" />
                      <span>{{ t("reportGeneration.saveToLibrary") }}</span>
                    </button>
                  </template>
                  <template v-else-if="reportViewMode === 'mindmap'">
                    <button
                      type="button"
                      class="ai-report-export__btn"
                      :disabled="Boolean(exportingMindmap)"
                      @click="exportReportMindmap('md', entry.index)"
                    >
                      <n-spin v-if="exportingMindmap === 'md'" :size="17" />
                      <n-icon v-else :size="18" :component="DocumentOutline" />
                      <span>{{ t("reportGeneration.exportMindmapMd") }}</span>
                    </button>
                    <button
                      type="button"
                      class="ai-report-export__btn"
                      :disabled="Boolean(exportingMindmap)"
                      @click="exportReportMindmap('opml', entry.index)"
                    >
                      <n-spin v-if="exportingMindmap === 'opml'" :size="17" />
                      <n-icon v-else :size="18" :component="GitNetworkOutline" />
                      <span>{{ t("reportGeneration.exportMindmapOpml") }}</span>
                    </button>
                  </template>
                </div>
              </template>
              <KnowledgeChatContent
                v-else-if="
                  linkifyCitations &&
                  hasAssistantAnswerText(entry.message) &&
                  !messageScreenshots(entry.message).length
                "
                :key="`kc-${entry.index}`"
                :content="messageCitationView(entry.message).content"
                :citations="messageCitationView(entry.message).citations"
                @open-citation="openCitationPreview($event, messageCitationView(entry.message).citations)"
              />
              <template v-else-if="linkifyCitations && hasAssistantAnswer(entry.message)">
                <KnowledgeChatContent
                  :key="`kc-shot-${entry.index}`"
                  :content="messageCitationView(entry.message).content"
                  :citations="messageCitationView(entry.message).citations"
                  @open-citation="openCitationPreview($event, messageCitationView(entry.message).citations)"
                />
                <AssistantConclusionContent
                  text-mode="gallery-only"
                  :content="entry.message.content"
                  :browser-screenshots="entry.message.browserScreenshots"
                />
              </template>
              <AssistantConclusionContent
                v-else-if="hasAssistantAnswer(entry.message)"
                :content="assistantConclusionContent(entry.message)"
                :rich-markdown="richMarkdown"
                :browser-screenshots="entry.message.browserScreenshots"
              />
              <div
                v-else-if="
                  !hasAssistantAnswerText(entry.message) &&
                  !workflowAwaitingAnswer(entry.message)
                "
                class="ai-workflow-wait ai-workflow-wait--empty"
                :class="{ 'ai-workflow-wait--failed': getWorkflowLastError(entry.message.workflow) }"
              >
                {{ getWorkflowLastError(entry.message.workflow) || t("chat.noAnswer") }}
              </div>
              <ChatMessageCitations
                v-if="
                  showCitations &&
                  !showReportTools &&
                  !entry.message.streaming &&
                  messageCitationView(entry.message).citations.length
                "
                :citations="messageCitationView(entry.message).citations"
                :preview-on-click="linkifyCitations"
                @open-citation="openCitationPreview($event, messageCitationView(entry.message).citations)"
              />
              </template>
              <div v-else-if="hasAssistantAnswer(entry.message)" class="ai-home-msg-collapsed">
                <div class="ai-home-msg-preview">
                  {{ plainMessagePreview(entry.message.content) }}
                </div>
                <button
                  v-if="isPlainPreviewTruncated(entry.message.content)"
                  type="button"
                  class="ai-home-msg-expand"
                  @click="expandMessage(entry.index)"
                >
                  {{ t("chat.expandMessage") }}
                </button>
              </div>
            </div>
            <div v-else class="ai-home-bubble ai-home-bubble--user">
              {{ entry.message.content }}
            </div>
            <ChatBubbleActions
              v-if="canShowMessageActions(entry.index, entry.message)"
              align="start"
              :show-retry="canRetryMessage(entry.index, entry.message)"
              :retry-disabled="sending || loadingHistory"
              :feedback="entry.message.feedback || null"
              @copy="copyAssistantMessage(entry.message)"
              @share="shareAssistantMessage(entry.message)"
              @retry="retryMessage(entry.index)"
              @feedback="setMessageFeedback(entry.index, $event)"
            />
            <div
              v-if="showFollowUpForMessage(entry.index, entry.message)"
              class="ai-home-follow-ups"
            >
              <span class="ai-home-follow-ups__label">{{ t("chat.continueAsk") }}</span>
              <div class="ai-home-follow-ups__list">
                <button
                  v-for="q in entry.message.followUpQuestions"
                  :key="q"
                  type="button"
                  class="ai-home-chip"
                  :disabled="sending"
                  @click="useFollowUpQuestion(q)"
                >
                  {{ q }}
                </button>
              </div>
            </div>
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
          <div class="ai-home-composer-stack">
            <div
              v-if="
                showReportTools
                  && (
                    reportAgentSkillsLoading
                    || reportAgentSkills.length
                    || (started && reportOptimizePresets.length)
                  )
              "
              class="ai-home-tools ai-home-tools--stack"
            >
              <n-popover
                v-if="reportAgentSkillsLoading || reportAgentSkills.length"
                trigger="click"
                placement="top-start"
                :width="312"
                :show="reportSkillPopoverShow"
                @update:show="(v) => (reportSkillPopoverShow = v)"
              >
                <template #trigger>
                  <button
                    type="button"
                    class="ai-home-tool-link ai-home-tool-action"
                    :disabled="(!composerInputWhileLoading && sending) || reportAgentSkillsLoading"
                  >
                    <n-icon :size="16" :component="LayersOutline" />
                    <span>{{ t("reportGeneration.selectReportType") }}</span>
                  </button>
                </template>
                <div class="ai-home-skills-popover">
                  <div class="ai-home-skills-popover__title">{{ t("reportGeneration.reportSkills") }}</div>
                  <div v-if="reportAgentSkillsLoading" class="ai-home-skills-popover__loading">
                    <n-spin :size="19" />
                  </div>
                  <div v-else-if="!reportAgentSkills.length" class="ai-home-skills-popover__empty">
                    {{ t("chat.agentSkills.skillEmpty") }}
                  </div>
                  <button
                    v-for="skill in reportAgentSkills"
                    :key="skill.name"
                    type="button"
                    class="ai-home-skills-popover__item"
                    @click="useReportAgentSkill(skill)"
                  >
                    <span class="ai-home-skills-popover__item-name">
                      {{ skill.title || skill.name }}
                    </span>
                    <span v-if="skill.description" class="ai-home-skills-popover__item-desc">
                      {{ skill.description }}
                    </span>
                  </button>
                </div>
              </n-popover>
              <n-popover
                v-if="started && reportOptimizePresets.length"
                trigger="click"
                placement="top-start"
                :width="312"
                :show="reportOptimizePopoverShow"
                @update:show="(v) => (reportOptimizePopoverShow = v)"
              >
                <template #trigger>
                  <button
                    type="button"
                    class="ai-home-tool-link ai-home-tool-action"
                    :disabled="!composerInputWhileLoading && sending"
                  >
                    <n-icon :size="16" :component="SparklesOutline" />
                    <span>{{ t("reportGeneration.selectReportOptimize") }}</span>
                  </button>
                </template>
                <div class="ai-home-skills-popover">
                  <div class="ai-home-skills-popover__title">{{ t("reportGeneration.optimizePresets") }}</div>
                  <button
                    v-for="p in reportOptimizePresets"
                    :key="p.id"
                    type="button"
                    class="ai-home-skills-popover__item"
                    @click="useReportOptimizePreset(p)"
                  >
                    <span class="ai-home-skills-popover__item-name">{{ p.label }}</span>
                    <span v-if="p.description" class="ai-home-skills-popover__item-desc">
                      {{ p.description }}
                    </span>
                  </button>
                </div>
              </n-popover>
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
                :show-attachment="enableAttachments"
                :attachment-loading="uploadingAttachments"
                :attachment-disabled="uploadingAttachments || sending"
                :attachments="enableAttachments ? attachmentFiles : []"
                @keydown="onComposerKeydown"
                @send="sendMessage()"
                @stop="stopGeneration"
                @attach="openAttachmentPicker"
                @remove-attachment="removeAttachment"
              >
                <template v-if="toolLinks.length || enableAgentSkills" #toolbar>
                  <RouterLink
                    v-for="tool in toolLinks"
                    :key="tool.title"
                    :to="tool.route"
                    class="ai-home-tool-link ai-home-composer-tool"
                  >
                    <n-icon v-if="tool.icon" :size="14" :component="tool.icon" />
                    <span>{{ tool.title }}</span>
                  </RouterLink>
                  <n-popover
                    v-if="enableAgentSkills"
                    trigger="click"
                    placement="top-start"
                    :width="312"
                    :show="agentPopoverShow"
                    @update:show="onAgentPopoverShowChange"
                  >
                    <template #trigger>
                      <button
                        type="button"
                        class="ai-home-tool-link ai-home-tool-action ai-home-composer-tool"
                        :disabled="sending"
                      >
                        <n-icon :size="14" :component="SparklesOutline" />
                        <span>{{ t("chat.agentSkills.selectAgent") }}</span>
                      </button>
                    </template>
                    <div class="ai-home-skills-popover">
                      <div class="ai-home-skills-popover__title">{{ t("chat.agentSkills.title") }}</div>
                      <div v-if="agentCatalogLoading" class="ai-home-skills-popover__loading">
                        <n-spin :size="16" />
                      </div>
                      <div v-else-if="!agentCatalog.length" class="ai-home-skills-popover__empty">
                        {{ t("chat.agentSkills.empty") }}
                      </div>
                      <button
                        v-for="agent in agentCatalog"
                        :key="agent.id"
                        type="button"
                        class="ai-home-skills-popover__item"
                        @click="useAgent(agent)"
                      >
                        <span class="ai-home-skills-popover__item-name">
                          {{ formatAgentDisplayName(agent.title) }}
                        </span>
                        <span v-if="agent.description" class="ai-home-skills-popover__item-desc">
                          {{ agent.description }}
                        </span>
                      </button>
                    </div>
                  </n-popover>
                  <n-popover
                    v-if="enableAgentSkills"
                    trigger="click"
                    placement="top-start"
                    :width="312"
                    :show="skillPopoverShow"
                    @update:show="onSkillPopoverShowChange"
                  >
                    <template #trigger>
                      <button
                        type="button"
                        class="ai-home-tool-link ai-home-tool-action ai-home-composer-tool"
                        :disabled="sending"
                      >
                        <n-icon :size="14" :component="LayersOutline" />
                        <span>{{ t("chat.agentSkills.selectSkill") }}</span>
                      </button>
                    </template>
                    <div class="ai-home-skills-popover">
                      <div class="ai-home-skills-popover__title">{{ t("chat.agentSkills.skillTitle") }}</div>
                      <div v-if="skillCatalogLoading" class="ai-home-skills-popover__loading">
                        <n-spin :size="16" />
                      </div>
                      <div v-else-if="!skillCatalog.length" class="ai-home-skills-popover__empty">
                        {{ t("chat.agentSkills.skillEmpty") }}
                      </div>
                      <button
                        v-for="skill in skillCatalog"
                        :key="skill.name"
                        type="button"
                        class="ai-home-skills-popover__item"
                        @click="useSkill(skill)"
                      >
                        <span class="ai-home-skills-popover__item-name">
                          {{ skill.title || skill.name }}
                        </span>
                        <span v-if="skill.description" class="ai-home-skills-popover__item-desc">
                          {{ skill.description }}
                        </span>
                      </button>
                    </div>
                  </n-popover>
                  <n-popover
                    v-if="enableAgentSkills"
                    trigger="click"
                    placement="top-start"
                    :width="312"
                    :show="thirdPartyAiPopoverShow"
                    @update:show="onThirdPartyAiPopoverShowChange"
                  >
                    <template #trigger>
                      <button
                        type="button"
                        class="ai-home-tool-link ai-home-tool-action ai-home-composer-tool"
                        :disabled="sending"
                      >
                        <n-icon :size="14" :component="CloudOutline" />
                        <span>{{ t("chat.agentSkills.thirdPartyAi") }}</span>
                      </button>
                    </template>
                    <div class="ai-home-skills-popover">
                      <div class="ai-home-skills-popover__title">{{ t("chat.agentSkills.thirdPartyAiSelect") }}</div>
                      <button
                        v-for="opt in thirdPartyAiOptions"
                        :key="opt.key"
                        type="button"
                        class="ai-home-skills-popover__item ai-home-skills-popover__item--with-badge"
                        @click="useThirdPartyAi(opt)"
                      >
                        <span class="ai-home-skills-popover__item-row">
                          <span class="ai-home-skills-popover__item-badge" :class="`ai-home-skills-popover__item-badge--${opt.key}`">
                            {{ opt.label.charAt(0) }}
                          </span>
                          <span class="ai-home-skills-popover__item-name">{{ opt.label }}</span>
                        </span>
                        <span class="ai-home-skills-popover__item-desc">{{ opt.desc }}</span>
                      </button>
                    </div>
                  </n-popover>
                </template>
              </ChatComposer>
            </div>
            <ChatDisclaimer v-if="showDisclaimer" :started="started" />
          </div>
          <div v-if="!started && suggestions.length && !showReportTools" class="ai-home-suggestions">
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
      :question="citationPreviewQuestion"
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
  top: 14px;
  right: 19px;
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
  padding-bottom: min(9vh, 77px);
  overflow: auto;
}

.ai-home-welcome {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 29px 29px 10px;
  overflow: auto;
}

.ai-home-main--landing .ai-home-welcome {
  flex: 0 0 auto;
  justify-content: center;
  padding: 0 29px;
  overflow: visible;
}

.ai-home-hero {
  text-align: center;
  max-width: 672px;
  margin-bottom: 14px;
}

.ai-home-icon {
  width: 86px;
  height: 86px;
  margin: 0 auto 19px;
  border-radius: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--platform-accent);
  background: var(--platform-accent-gradient-soft);
  border: 1px solid var(--platform-accent-border-soft);
  box-shadow: 0 5px 19px color-mix(in srgb, var(--platform-accent) 10%, transparent);
}

.ai-home-icon--sm {
  width: 48px;
  height: 48px;
  margin: 0;
  border-radius: 14px;
}

.ai-home-title {
  margin: 0 0 12px;
  font-size: 30px;
  font-weight: 700;
  color: var(--platform-text);
  letter-spacing: var(--platform-tracking-tight);
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
  margin: 0 0 12px;
  font-size: 18px;
  line-height: 1.65;
  color: var(--platform-muted);
}

.ai-home-sub {
  margin: 0;
  font-size: 15px;
  color: var(--platform-text-tertiary);
}

.ai-home-arch {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--platform-text-tertiary);
}

/* ── AgentKit 介绍卡片 ── */
.ai-home-agentkit {
  margin-top: 20px;
  max-width: 520px;
  margin-left: auto;
  margin-right: auto;
  padding: 12px 16px;
  border: 1px solid var(--platform-border);
  border-radius: 8px;
  background: var(--platform-bg-secondary);
}

.agentkit-intro-title {
  margin: 0 0 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--platform-text-primary);
}

.agentkit-intro-list {
  margin: 0;
  padding: 0 0 0 14px;
  list-style: none;
}

.agentkit-intro-item {
  position: relative;
  margin-bottom: 4px;
  padding-left: 10px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--platform-text-secondary);
}

.agentkit-intro-item::before {
  content: "·";
  position: absolute;
  left: 0;
  color: var(--platform-primary);
  font-weight: bold;
}

.agentkit-intro-link {
  display: inline-block;
  margin-top: 6px;
  font-size: 12px;
  color: var(--platform-primary);
  cursor: pointer;
  text-decoration: none;
}

.agentkit-intro-link:hover {
  text-decoration: underline;
}

.ai-home-dock {
  flex-shrink: 0;
  width: 100%;
  padding: 0 24px 20px;
  box-sizing: border-box;
  transition: transform 0.42s cubic-bezier(0.22, 1, 0.36, 1);
  will-change: transform;
}

.ai-home-dock-inner {
  width: min(720px, calc(100% - 10px));
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
}

.ai-home-main--landing .ai-home-dock {
  flex-shrink: 0;
  margin-top: 24px;
  padding: 0 24px;
  transform: none;
}

/* 对话中：输入区与消息区 flex 分区 */
.ai-home-dock--chat {
  flex-shrink: 0;
  margin-top: 8px;
  padding: 0 24px 14px;
  transform: none;
  background: transparent;
}

.ai-home-tools {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-start;
  gap: 7px;
  width: 100%;
  padding-left: 2px;
  margin-bottom: 2px;
}

.ai-home-tools--stack {
  margin-bottom: 0;
}

.ai-home-tool-link {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  font-size: 13px;
  line-height: 1.4;
  color: var(--platform-text-secondary);
  text-decoration: none;
  border-radius: var(--platform-radius-pill);
  border: 1px solid var(--platform-border);
  background: transparent;
  transition:
    background var(--platform-duration-smooth) ease,
    border-color var(--platform-duration-smooth) ease,
    color var(--platform-duration-smooth) ease;
}

.ai-home-tool-link:hover {
  color: var(--platform-text);
  background: var(--platform-bg-secondary);
  border-color: var(--platform-border-strong);
}

.ai-home-tool-action {
  cursor: pointer;
  font-family: inherit;
}

.ai-home-tool-action:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* 输入框内工具栏按钮 —— 更紧凑，与附件按钮水平对齐 */
.ai-home-composer-tool {
  padding: 3px 8px;
  font-size: 12px;
  line-height: 1.3;
  border: none;
  background: transparent;
  color: var(--platform-text-tertiary);
  border-radius: 4px;
  white-space: nowrap;
  transition: color var(--platform-duration-smooth) ease, background var(--platform-duration-smooth) ease;
}

.ai-home-composer-tool:hover {
  color: var(--platform-text-secondary);
  background: var(--platform-bg-secondary);
}

.ai-home-suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  justify-content: flex-start;
  width: 100%;
  padding-left: 2px;
  margin-top: 2px;
}

.ai-home-chip {
  padding: 7px 16px;
  font-size: 13px;
  font-weight: 500;
  color: var(--platform-text-secondary);
  background: var(--platform-accent-muted);
  border: 1px solid var(--platform-accent-border-soft);
  border-radius: var(--platform-radius-pill);
  cursor: pointer;
  white-space: nowrap;
  transition:
    all var(--platform-duration-smooth, 0.2s) var(--platform-ease-smooth, ease);
}

.ai-home-chip:hover:not(:disabled) {
  color: var(--platform-accent-pressed);
  background: var(--platform-accent-soft);
  border-color: var(--platform-accent-border);
  box-shadow: 0 2px 8px color-mix(in srgb, var(--platform-accent) 10%, transparent);
  transform: translateY(-1px);
}

.ai-home-chip:active:not(:disabled) {
  transform: translateY(0);
  box-shadow: none;
}

.ai-home-chip:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.ai-home-follow-ups {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  width: 100%;
  max-width: min(100%, 864px);
  padding: 4px 4px 0;
  margin-top: 2px;
}

.ai-home-follow-ups__label {
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.3px;
  text-transform: uppercase;
  color: var(--platform-text-quaternary);
  user-select: none;
}

.ai-home-follow-ups__list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.ai-home-follow-ups .ai-home-chip {
  padding: 6px 14px;
  font-size: 13px;
}

.ai-home-attachment-input {
  display: none;
}

.ai-home-skills-popover {
  display: flex;
  flex-direction: column;
  gap: 1px;
  max-height: 360px;
  overflow-y: auto;
  padding: 0;
}

.ai-home-skills-popover__title {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--platform-text-tertiary);
  padding: 8px 10px 6px;
}

.ai-home-skills-popover__loading,
.ai-home-skills-popover__empty {
  padding: 14px 10px;
  font-size: 13px;
  color: var(--platform-text-tertiary);
  text-align: center;
}

.ai-home-skills-popover__item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 3px;
  width: 100%;
  padding: 8px 10px;
  border: none;
  border-radius: 6px;
  background: transparent;
  text-align: left;
  cursor: pointer;
  font-family: inherit;
  transition: background 0.15s ease;
}

.ai-home-skills-popover__item:hover:not(:disabled) {
  background: var(--platform-bg-secondary);
}

.ai-home-skills-popover__item:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.ai-home-skills-popover__item-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--platform-text);
}

.ai-home-skills-popover__item-desc {
  font-size: 12px;
  line-height: 1.4;
  color: var(--platform-text-tertiary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* ── Third-party AI badge row ── */
.ai-home-skills-popover__item--with-badge {
  gap: 4px;
}

.ai-home-skills-popover__item-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.ai-home-skills-popover__item-badge {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 5px;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
}

.ai-home-skills-popover__item-badge--doubao {
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
}

.ai-home-skills-popover__item-badge--qwen {
  background: linear-gradient(135deg, #0ea5e9, #06b6d4);
}

.ai-home-skills-popover__item-badge--deepseek {
  background: linear-gradient(135deg, #f59e0b, #d97706);
}

.ai-home-composer-stack {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
}

.ai-home-composer {
  width: 100%;
}

.ai-home-dock--chat .ai-home-composer :deep(.chat-composer) {
  border-radius: var(--platform-radius);
}

.ai-home :deep(.ai-chat-textarea.n-input) {
  --n-padding-left: 18px;
  --n-padding-right: 18px;
  --n-line-height-textarea: 1.5;
  font-size: 16px;
}

.ai-home :deep(.ai-chat-textarea .n-input__textarea-el),
.ai-home :deep(.ai-chat-textarea .n-input__placeholder),
.ai-home :deep(.ai-chat-textarea .n-input__textarea-mirror) {
  font-size: 16px;
  line-height: 1.5;
  padding-top: 14px;
  padding-left: 0;
  padding-right: 0;
}

.ai-home-chat-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 19px;
  border-bottom: 1px solid var(--platform-border);
  background: var(--platform-surface);
  position: relative;
  z-index: 2;
}

.ai-home-chat-header--minimal {
  justify-content: flex-end;
  padding: 10px 19px 4px;
  background: transparent;
  border-bottom: none;
}

.ai-home-chat-actions {
  display: flex;
  align-items: center;
  gap: 5px;
  flex-shrink: 0;
}

.ai-home-history-loading {
  flex: 1;
  min-height: 144px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--platform-text-secondary);
  font-size: 17px;
}

.ai-home-chat-brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.ai-home-chat-title {
  font-size: 17px;
  font-weight: 600;
  color: var(--platform-text);
}

.ai-home-chat-sub {
  font-size: 14px;
  color: var(--platform-muted);
}

.ai-home-messages {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px 24px 10px;
  -webkit-overflow-scrolling: touch;
  box-sizing: border-box;
  background:
    radial-gradient(ellipse at 20% 50%, color-mix(in srgb, var(--platform-accent) 2%, transparent) 0%, transparent 55%),
    radial-gradient(ellipse at 80% 20%, color-mix(in srgb, var(--platform-accent) 1.5%, transparent) 0%, transparent 55%);
}

.ai-home-messages-inner {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.ai-home-load-older {
  display: flex;
  justify-content: center;
  padding: 5px 0 10px;
}

.ai-home-load-older__btn {
  border: 1px solid var(--platform-border);
  background: var(--platform-surface-soft, rgba(255, 255, 255, 0.6));
  color: var(--platform-text-secondary);
  border-radius: 1199px;
  padding: 7px 17px;
  font-size: 14px;
  cursor: pointer;
}

.ai-home-load-older__btn:hover {
  color: var(--platform-accent);
  border-color: var(--platform-accent-soft);
}

.ai-home-msg {
  display: flex;
  margin: 2px 0;
  animation: ai-home-msg-in 0.25s ease-out;
}

@keyframes ai-home-msg-in {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
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
  max-width: min(864px, 88%);
  gap: 6px;
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
  padding: 14px 19px;
  border-radius: 17px;
  font-size: 16px;
  line-height: 1.65;
  word-break: break-word;
}

.ai-home-bubble--user {
  width: fit-content;
  max-width: 100%;
  background: var(--platform-bg-tertiary);
  color: var(--platform-text);
  border: 1px solid var(--platform-border);
  border-bottom-right-radius: 5px;
  white-space: pre-wrap;
  font-size: 15px;
  padding: 10px 16px;
  backdrop-filter: blur(4px);
  transition: box-shadow 0.2s ease;
}

/* 用户消息气泡：渐变蓝色 + 精致圆角 + 深度感阴影 */
.ai-home-bubble--user {
  background: linear-gradient(135deg, var(--platform-accent-secondary) 0%, var(--platform-accent) 100%);
  color: #fff;
  border: none;
  border-bottom-right-radius: 4px;
  box-shadow: 0 1px 3px rgba(10, 107, 255, 0.2), 0 2px 8px rgba(10, 107, 255, 0.12);
  font-kerning: normal;
  -webkit-font-smoothing: antialiased;
  letter-spacing: var(--platform-tracking-tight, -0.01em);
}

.ai-home-bubble--bot {
  padding: 0;
  border-radius: 0;
  background: transparent;
  color: var(--platform-text);
  border: none;
  box-shadow: none;
}

/* 高级感助手气泡：多层阴影 + 微渐变 + 精致排版 — 对标 ChatGPT/Claude 风格 */
.ai-home-bubble--bot {
  position: relative;
  width: 100%;
  padding: 18px 22px;
  border-radius: var(--platform-radius, 12px);
  background: var(--platform-bg-elevated);
  background-image:
    linear-gradient(
      180deg,
      color-mix(in srgb, var(--platform-accent) 0.8%, transparent) 0%,
      transparent 48px
    );
  box-shadow: var(--platform-shadow);
  border: 1px solid var(--platform-border);
  font-kerning: normal;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  transition:
    box-shadow var(--platform-duration-smooth, 0.2s) var(--platform-ease-smooth),
    border-color var(--platform-duration-smooth, 0.2s) var(--platform-ease-smooth);
}

/* Hover 时略微增强边框对比 */
.ai-home-msg-stack--bot:hover .ai-home-bubble--bot {
  border-color: var(--platform-border-strong);
}

.ai-home-bubble--error {
  color: var(--platform-danger);
  background: color-mix(in srgb, var(--platform-danger-soft, #fef2f2) 60%, transparent);
  border: 1px solid color-mix(in srgb, var(--platform-danger) 20%, transparent);
  border-radius: var(--platform-radius);
  padding: 12px 16px;
}

.ai-home-stream-text {
  white-space: pre-wrap;
  word-break: break-word;
}

.ai-home-stream-md {
  word-break: break-word;
}

.ai-home-stream-md .ai-home-cursor {
  display: inline-block;
  margin-left: 2px;
}

/* Checkpoint 暂停恢复区域 */
.ai-home-suspended {
  padding: 12px 16px;
  margin: 8px 0;
  background: var(--platform-bg-2, #f5f7fa);
  border: 1px solid var(--platform-border-color, #e0e0e0);
  border-radius: 8px;
}
.ai-suspended-info {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  font-size: 14px;
  color: var(--platform-text-secondary, #666);
}
.ai-suspended-icon {
  flex-shrink: 0;
}
.ai-suspended-actions {
  display: flex;
  gap: 8px;
}
.ai-suspended-detail {
  margin-top: 12px;
  font-size: 13px;
  color: var(--platform-text-tertiary, #999);
}
.ai-suspended-choices {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.ai-home-msg-preview {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 16px;
  line-height: 1.55;
  color: var(--platform-text-secondary);
  max-height: 8.5em;
  overflow: hidden;
}

.ai-home-msg-collapsed {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 7px;
}

.ai-home-msg-expand {
  border: none;
  background: transparent;
  color: var(--platform-accent);
  font-size: 14px;
  padding: 0;
  cursor: pointer;
}

.ai-home-msg-expand:hover {
  text-decoration: underline;
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
  margin: 0 0 0.6em;
  font-size: 15px;
  line-height: 1.7;
  color: var(--platform-text);
  font-kerning: normal;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

.ai-home-bubble--bot :deep(p:last-child) {
  margin-bottom: 0;
}

.ai-home-bubble--bot :deep(ul),
.ai-home-bubble--bot :deep(ol) {
  margin: 0.5em 0;
  padding-left: 1.4em;
  font-size: 15px;
  line-height: 1.7;
}

.ai-home-bubble--bot :deep(li) {
  margin-bottom: 0.2em;
}

.ai-home-bubble--bot :deep(code) {
  font-size: 0.85em;
  padding: 2px 8px;
  border-radius: 6px;
  background: color-mix(in srgb, var(--platform-accent) 6%, transparent);
  border: 1px solid color-mix(in srgb, var(--platform-accent) 12%, transparent);
  font-family: "SF Mono", "Fira Code", "Cascadia Code", Consolas, monospace;
  font-weight: 500;
  color: color-mix(in srgb, var(--platform-accent-pressed) 80%, var(--platform-text));
}

/* 代码块（pre > code） — 更具高级感的深色背景 */
.ai-home-bubble--bot :deep(pre) {
  margin: 0.6em 0;
  padding: 16px 18px;
  border-radius: 10px;
  background: #1a1a2e;
  border: 1px solid rgba(255, 255, 255, 0.06);
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

.ai-home-bubble--bot :deep(pre code) {
  padding: 0;
  background: transparent;
  border: none;
  font-weight: 400;
  color: #e4e4e7;
  font-size: 0.82em;
  line-height: 1.55;
}

.ai-home-bubble--bot :deep(h1),
.ai-home-bubble--bot :deep(h2),
.ai-home-bubble--bot :deep(h3),
.ai-home-bubble--bot :deep(h4) {
  margin: 0.8em 0 0.4em;
  font-weight: 600;
  line-height: 1.4;
  color: var(--platform-text);
}

.ai-home-bubble--bot :deep(h1) { font-size: 1.25em; }
.ai-home-bubble--bot :deep(h2) { font-size: 1.15em; }
.ai-home-bubble--bot :deep(h3) { font-size: 1.05em; }

.ai-home-bubble--bot :deep(blockquote) {
  margin: 0.5em 0;
  padding: 4px 12px;
  border-left: 3px solid var(--platform-accent);
  color: var(--platform-text-secondary);
  background: color-mix(in srgb, var(--platform-bg-tertiary) 30%, transparent);
  border-radius: 0 6px 6px 0;
}

.ai-home-bubble--bot :deep(hr) {
  margin: 1em 0;
  border: none;
  border-top: 1px solid var(--platform-border);
}

.ai-home-bubble--bot :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 0.6em 0;
  font-size: 14px;
}

.ai-home-bubble--bot :deep(th),
.ai-home-bubble--bot :deep(td) {
  padding: 8px 12px;
  border: 1px solid var(--platform-border);
  text-align: left;
}

.ai-home-bubble--bot :deep(th) {
  background: color-mix(in srgb, var(--platform-bg-tertiary) 50%, transparent);
  font-weight: 600;
}

.ai-workflow-current {
  margin-top: 5px;
}

.ai-answer-status {
  gap: 10px;
  font-size: 16px;
  padding: 5px 0;
}

.ai-answer-status__rose {
  flex-shrink: 0;
  line-height: 0;
}

.ai-answer-status__rose :deep(.rose-loader) {
  display: block;
}

.ai-answer-status-text {
  font-weight: 500;
  color: var(--platform-text-secondary);
  line-height: 1.35;
}

.ai-workflow-current--failed .ai-answer-status-text {
  color: var(--platform-text-secondary, #64748b);
}

.ai-workflow-current__agent {
  flex-shrink: 0;
  padding: 1px 7px;
  border-radius: 5px;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.4;
  color: var(--platform-text);
  background: var(--platform-bg-tertiary);
}

.ai-workflow-wait {
  font-size: 15px;
  color: var(--platform-text-tertiary);
  padding: 5px 0;
}

.ai-thinking {
  font-size: 15px;
  padding: 8px 0;
}

.ai-thinking-elapsed {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 0;
  width: 100%;
}

.ai-thinking-elapsed__header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ai-thinking-elapsed__time {
  font-size: 12px;
  font-weight: 500;
  color: var(--platform-text-quaternary);
  line-height: 1;
  white-space: nowrap;
  letter-spacing: 0.3px;
}

.ai-thinking-elapsed__divider {
  height: 0;
  border: none;
  border-top: 1px solid var(--platform-border);
  width: 100%;
  max-width: 100%;
}

.ai-workflow-wait--empty {
  color: var(--platform-text-tertiary);
}

.ai-workflow-wait--failed {
  color: var(--platform-text-secondary);
}

.ai-report-tools {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  margin-bottom: 14px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--platform-accent-border-soft);
}

.ai-report-tools__tabs {
  display: inline-flex;
  gap: 5px;
  padding: 4px;
  border-radius: 12px;
  background: color-mix(in srgb, var(--platform-bg) 70%, transparent);
  border: 1px solid var(--platform-accent-border-soft);
}

.ai-report-tools__tab {
  border: none;
  background: transparent;
  color: var(--platform-text-secondary);
  font-size: 14px;
  font-weight: 600;
  padding: 7px 14px;
  border-radius: 10px;
  cursor: pointer;
}

.ai-report-tools__tab--active {
  color: var(--platform-accent-pressed);
  background: var(--platform-accent-muted);
}

.ai-report-export {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 19px;
  padding-top: 17px;
  border-top: 1px solid var(--platform-accent-border-soft);
}

.ai-report-export__btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 41px;
  padding: 0 17px;
  border: 1px solid var(--platform-accent-border);
  border-radius: 12px;
  background: var(--platform-accent-muted);
  color: var(--platform-accent-pressed);
  font-size: 16px;
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
  box-shadow: 0 4px 14px color-mix(in srgb, var(--platform-accent) 16%, transparent);
  transform: translateY(-1px);
}

.ai-report-export__btn:active:not(:disabled) {
  transform: translateY(0);
}

.ai-report-export__btn:disabled {
  opacity: 0.65;
  cursor: wait;
}

.ai-report-export__btn--primary {
  background: var(--platform-accent);
  border-color: var(--platform-accent);
  color: #fff;
}

.ai-report-export__btn--primary:hover:not(:disabled) {
  background: var(--platform-accent-pressed);
  border-color: var(--platform-accent-pressed);
  color: #fff;
}

.ai-report-citations {
  margin-top: 17px;
}
</style>
