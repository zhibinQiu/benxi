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
import { TimeOutline } from "@vicons/ionicons5";
import { fetchChatConversationMessages } from "../api/client";
import { NButton, NIcon, NSpin } from "naive-ui";
import { marked } from "marked";
import ChatComposer from "./ChatComposer.vue";
import IconAction from "./IconAction.vue";
import MarkdownRichContent from "./MarkdownRichContent.vue";
import KnowledgeChatContent from "./KnowledgeChatContent.vue";
import KnowledgeCitationPreviewModal from "./KnowledgeCitationPreviewModal.vue";
import ChatMessageCitations from "./ChatMessageCitations.vue";
import { PLATFORM_APP_NAME } from "../constants/platform";
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
  replyPlaceholder: { type: String, default: "继续提问" },
  /** 对话历史 scope：ai-home | carbon-qa | smart-data-query */
  chatScope: { type: String, default: "" },
  /** 是否展示历史对话 / 新对话（知识检索等单次会话场景设为 false） */
  showSessionActions: { type: Boolean, default: true },
});

const conversationId = defineModel("conversationId", { type: String, default: null });

const emit = defineEmits(["new-chat"]);

const ui = usePlatformUi();
const route = useRoute();
const router = useRouter();

marked.setOptions({ gfm: true, breaks: true });

const started = ref(false);
const loadingHistory = ref(false);
const input = ref("");
const sending = ref(false);
const messages = ref([]);
const messagesRef = ref(null);
const citationPreviewShow = ref(false);
const citationPreviewTarget = ref(null);
let streamAbort = null;

function openCitationPreview(citationOrIndex, citations = []) {
  let citation = citationOrIndex;
  if (typeof citationOrIndex === "number") {
    citation = (citations || []).find((c) => Number(c.index) === citationOrIndex);
  }
  if (!citation) return;
  citationPreviewTarget.value = citation;
  citationPreviewShow.value = true;
}

const displaySubtitle = computed(
  () => props.subtitle || `${PLATFORM_APP_NAME} · 智能对话`
);

const headerSub = computed(
  () =>
    props.chatHeaderSub ||
    (props.streaming ? "多轮对话 · 流式回复" : "多轮对话 · Markdown / 图表")
);

const composerPlaceholder = computed(() =>
  started.value ? props.replyPlaceholder : "输入您的问题"
);

const landingComposerRows = computed(() => ({ minRows: 3, maxRows: 8 }));
/** 对话中输入框固定 1 行 */
const chatComposerRows = computed(() => ({ minRows: 1, maxRows: 1 }));

function emptyWorkflow() {
  return { currentTitle: "", running: false, failed: false };
}

function applyWorkflowEvent(workflow, ev) {
  if (!workflow) return emptyWorkflow();
  const phase = ev?.phase;
  if (phase === "workflow_started") {
    workflow.running = true;
    workflow.failed = false;
    workflow.currentTitle = "工作流启动";
    return workflow;
  }
  if (phase === "node_started") {
    workflow.running = true;
    workflow.failed = false;
    workflow.currentTitle = ev.title || "处理中";
    return workflow;
  }
  if (phase === "node_finished") {
    const failed = ev.status === "failed" || ev.status === "exception";
    if (failed) {
      workflow.failed = true;
      workflow.currentTitle = `${ev.title || "节点"}（失败）`;
    }
    return workflow;
  }
  if (phase === "workflow_finished") {
    workflow.running = false;
    workflow.currentTitle = "";
    workflow.failed = false;
    return workflow;
  }
  return workflow;
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

async function sendMessageStreaming(content, assistantIdx) {
  const history = messages.value
    .slice(0, assistantIdx)
    .filter((m) => m.role === "user" || m.role === "assistant")
    .map((m) => ({ role: m.role, content: m.content }));

  streamAbort?.abort();
  streamAbort = new AbortController();

  let scrollTick = 0;
  try {
    await props.streamChat(
      {
        message: content,
        history,
        conversationId: conversationId.value},
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
        onCitations: (citations) => {
          if (!props.showCitations || !Array.isArray(citations)) return;
          const row = messages.value[assistantIdx];
          if (row) row.citations = citations;
        },
        onReplace: (text) => {
          const row = messages.value[assistantIdx];
          if (!row) return;
          row.content = text;
          scrollToBottom();
        },
        onDelta: (delta) => {
          const row = messages.value[assistantIdx];
          if (!row) return;
          row.content += delta;
          scrollTick += 1;
          if (scrollTick % 4 === 0) scrollToBottom();
        },
        onError: (err) => {
          throw err;
        },
        onDone: (payload) => {
          const row = messages.value[assistantIdx];
          if (row) {
            const full = (payload?.reply || "").trim();
            if (full && full.length >= (row.content || "").length) {
              row.content = full;
            }
            row.streaming = false;
            if (row.workflow) row.workflow.running = false;
            if (props.showCitations && Array.isArray(payload?.citations)) {
              row.citations = payload.citations;
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
    row.content = "（已停止生成）";
  }
}

function stopGeneration() {
  if (!sending.value) return;
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

async function sendMessageBlocking(content, assistantIdx) {
  const history = messages.value
    .slice(0, assistantIdx)
    .filter((m) => m.role === "user" || m.role === "assistant")
    .map((m) => ({ role: m.role, content: m.content }));

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
  if (!content || sending.value) return;

  if (props.streaming && !props.streamChat) {
    ui.error("未配置流式对话");
    return;
  }
  if (!props.streaming && !props.chatSend) {
    ui.error("未配置对话接口");
    return;
  }

  const firstTurn = !started.value;
  if (firstTurn) started.value = true;

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
      await sendMessageStreaming(content, assistantIdx);
    } else {
      await sendMessageBlocking(content, assistantIdx);
    }
  } catch (e) {
    if (e?.name === "AbortError") {
      finalizeStoppedAssistant(assistantIdx);
      return;
    }
    ui.error(e.message || "发送失败");
    const row = messages.value[assistantIdx];
    if (row) {
      row.streaming = false;
      row.error = true;
      if (!row.content.trim()) {
        row.content = "抱歉，暂时无法回复，请稍后重试。";
      }
    } else {
      messages.value.push({
        role: "assistant",
        content: "抱歉，暂时无法回复，请稍后重试。",
        error: true});
    }
  } finally {
    sending.value = false;
    streamAbort = null;
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

function useSuggestion(text) {
  input.value = text;
  sendMessage(text);
}

function persistSessionState() {
  if (!props.chatScope) return;
  const serialized = serializeChatMessages(messages.value);
  if (!serialized.length && !conversationId.value && !input.value.trim()) {
    clearChatSession(props.chatScope);
    return;
  }
  saveChatSession(props.chatScope, {
    conversationId: conversationId.value,
    messages: serialized,
    started: started.value,
    input: input.value,
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
    ui.error(e.message || "加载对话失败");
  } finally {
    loadingHistory.value = false;
  }
}

async function restorePersistedSession() {
  if (!props.chatScope) return;
  const saved = loadChatSession(props.chatScope);
  if (!saved) return;

  if (saved.input) input.value = saved.input;

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
  persistSessionState();
  streamAbort?.abort();
});

onActivated(() => {
  if (started.value) scrollToBottom();
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
        label="查看历史对话"
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
            label="历史对话"
            :icon="TimeOutline"
            :disabled="loadingHistory"
            @click="goToHistory"
          />
          <n-button size="small" quaternary @click="newChat">新对话</n-button>
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

      <div v-if="loadingHistory" class="ai-home-history-loading">
        <n-spin size="small" />
        <span>正在加载对话…</span>
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
              v-if="m.role === 'assistant'"
              class="ai-home-bubble ai-home-bubble--bot"
              :class="{
                'ai-home-bubble--error': m.error,
                'ai-home-bubble--streaming': m.streaming}"
            >
              <div
                v-if="
                  showWorkflowProgress &&
                  m.streaming &&
                  !m.content &&
                  m.workflow?.running &&
                  m.workflow.currentTitle
                "
                class="ai-workflow-current"
                :class="{ 'ai-workflow-current--failed': m.workflow.failed }"
              >
                <span v-if="!m.workflow.failed" class="ai-workflow-spinner" aria-hidden="true" />
                {{ m.workflow.currentTitle }}
              </div>
              <div v-else-if="m.streaming && !m.content" class="ai-thinking">
                <span class="ai-workflow-spinner" aria-hidden="true" />
                正在思考…
              </div>
              <div v-else-if="m.streaming" class="ai-home-stream-text">
                {{ m.content }}<span class="ai-home-cursor">▍</span>
              </div>
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
              <div v-else class="ai-workflow-wait ai-workflow-wait--empty">未能生成回答</div>
              <ChatMessageCitations
                v-if="showCitations && !m.streaming && m.citations?.length"
                :citations="m.citations"
                :preview-on-click="linkifyCitations"
                @open-citation="openCitationPreview($event, m.citations)"
              />
            </div>
            <div v-else class="ai-home-bubble ai-home-bubble--user">
              {{ m.content }}
            </div>
          </div>
        </TransitionGroup>
      </div>

      <div class="ai-home-dock" :class="{ 'ai-home-dock--chat': started }">
        <div class="ai-home-dock-inner">
          <div v-if="!started && toolLinks.length" class="ai-home-tools">
            <RouterLink
              v-for="tool in toolLinks"
              :key="tool.title"
              :to="tool.route"
              class="ai-home-tool-link"
            >
              <n-icon v-if="tool.icon" :size="13" :component="tool.icon" />
              <span>{{ tool.title }}</span>
            </RouterLink>
          </div>
          <div class="ai-home-composer">
            <ChatComposer
              v-model="input"
              :placeholder="composerPlaceholder"
              :disabled="sending"
              :loading="sending"
              :min-rows="started ? chatComposerRows.minRows : landingComposerRows.minRows"
              :max-rows="started ? chatComposerRows.maxRows : landingComposerRows.maxRows"
              @keydown="onComposerKeydown"
              @send="sendMessage()"
              @stop="stopGeneration"
            />
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
  color: #64748b;
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

.ai-home-bubble {
  max-width: min(720px, 88%);
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

.ai-workflow-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid var(--platform-accent-border-soft);
  border-top-color: var(--platform-accent);
  border-radius: 50%;
  animation: ai-workflow-spin 0.8s linear infinite;
  flex-shrink: 0;
}

@keyframes ai-workflow-spin {
  to {
    transform: rotate(360deg);
  }
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
</style>
