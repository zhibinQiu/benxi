<script setup>
import { computed, nextTick, onBeforeUnmount, ref } from "vue";
import { NButton, NIcon, NInput, useMessage } from "naive-ui";
import { SendOutline } from "@vicons/ionicons5";
import { marked } from "marked";
import MarkdownRichContent from "./MarkdownRichContent.vue";
import ChatMessageCitations from "./ChatMessageCitations.vue";
import { PLATFORM_APP_NAME } from "../constants/platform";

const props = defineProps({
  title: { type: String, required: true },
  description: { type: String, default: "" },
  subtitle: { type: String, default: "" },
  suggestions: { type: Array, default: () => [] },
  icon: { type: Object, required: true },
  /** 流式对话（AI 首页等） */
  streaming: { type: Boolean, default: true },
  streamChat: { type: Function, default: null },
  /** 非流式对话 */
  chatSend: { type: Function, default: null },
  /** 流式结束后用 Markdown + ECharts 渲染 */
  richMarkdown: { type: Boolean, default: false },
  /** 展示 Dify 工作流节点执行进度 */
  showWorkflowProgress: { type: Boolean, default: false },
  /** 展示回答引用来源（Dify 知识库检索） */
  showCitations: { type: Boolean, default: false },
  chatHeaderSub: { type: String, default: "" },
});

const conversationId = defineModel("conversationId", { type: String, default: null });

const emit = defineEmits(["new-chat"]);

const message = useMessage();

marked.setOptions({ gfm: true, breaks: true });

const started = ref(false);
const input = ref("");
const sending = ref(false);
const messages = ref([]);
const messagesRef = ref(null);
let streamAbort = null;

const displaySubtitle = computed(
  () => props.subtitle || `${PLATFORM_APP_NAME} · 智能对话`
);

const headerSub = computed(
  () =>
    props.chatHeaderSub ||
    (props.streaming ? "多轮对话 · 流式回复" : "多轮对话 · Markdown / 图表")
);

const canSend = computed(() => input.value.trim().length > 0 && !sending.value);

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
        conversationId: conversationId.value,
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
        },
      }
    );
    const row = messages.value[assistantIdx];
    if (row && !row.content.trim()) {
      row.content = "（未收到回复内容）";
      row.streaming = false;
    }
  } catch (e) {
    if (e?.name === "AbortError") return;
    throw e;
  }
}

async function sendMessageBlocking(content, assistantIdx) {
  const history = messages.value
    .slice(0, assistantIdx)
    .filter((m) => m.role === "user" || m.role === "assistant")
    .map((m) => ({ role: m.role, content: m.content }));

  messages.value.push({ role: "assistant", content: "", streaming: false });
  await scrollToBottom();

  const data = await props.chatSend({
    message: content,
    history,
    conversationId: conversationId.value,
  });

  const row = messages.value[assistantIdx];
  if (row) {
    row.content = (data?.reply || "").trim() || "（未收到回复内容）";
    if (props.showCitations && Array.isArray(data?.citations)) {
      row.citations = data.citations;
    }
    if (data?.conversation_id) {
      conversationId.value = data.conversation_id;
    }
  }
}

async function sendMessage(text) {
  const content = (text ?? input.value).trim();
  if (!content || sending.value) return;

  if (props.streaming && !props.streamChat) {
    message.error("未配置流式对话");
    return;
  }
  if (!props.streaming && !props.chatSend) {
    message.error("未配置对话接口");
    return;
  }

  if (!started.value) started.value = true;
  messages.value.push({ role: "user", content });
  input.value = "";
  sending.value = true;
  await scrollToBottom();

  const assistantIdx = messages.value.length;

  try {
    if (props.streaming) {
      messages.value.push({
        role: "assistant",
        content: "",
        streaming: true,
        workflow: props.showWorkflowProgress ? emptyWorkflow() : null,
      });
      await scrollToBottom();
      await sendMessageStreaming(content, assistantIdx);
    } else {
      await sendMessageBlocking(content, assistantIdx);
    }
  } catch (e) {
    if (e?.name === "AbortError") return;
    message.error(e.message || "发送失败");
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
        error: true,
      });
    }
  } finally {
    sending.value = false;
    streamAbort = null;
    await scrollToBottom();
  }
}

function onLandingKeydown(e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

function onChatKeydown(e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

function useSuggestion(text) {
  input.value = text;
  sendMessage(text);
}

function newChat() {
  streamAbort?.abort();
  streamAbort = null;
  sending.value = false;
  started.value = false;
  messages.value = [];
  input.value = "";
  conversationId.value = null;
  emit("new-chat");
}

onBeforeUnmount(() => {
  streamAbort?.abort();
  messages.value = [];
});
</script>

<template>
  <div class="ai-home">
    <div v-if="!started" class="ai-home-welcome">
      <div class="ai-home-hero">
        <div class="ai-home-icon">
          <n-icon :size="36" :component="icon" />
        </div>
        <h1 class="ai-home-title">{{ title }}</h1>
        <p v-if="description" class="ai-home-desc">{{ description }}</p>
        <p class="ai-home-sub">{{ displaySubtitle }}</p>
      </div>

      <div class="ai-home-landing-input">
        <n-input
          v-model:value="input"
          class="ai-chat-textarea"
          type="textarea"
          :autosize="{ minRows: 4, maxRows: 8 }"
          placeholder="输入您的问题…"
          :disabled="sending"
          @keydown="onLandingKeydown"
        />
        <n-button
          type="primary"
          class="ai-home-send-btn"
          :disabled="!canSend"
          :loading="sending"
          @click="sendMessage()"
        >
          <template #icon>
            <n-icon :component="SendOutline" />
          </template>
          开始对话
        </n-button>
      </div>

      <div v-if="suggestions.length" class="ai-home-suggestions">
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

    <div v-else class="ai-home-chat">
      <header class="ai-home-chat-header">
        <div class="ai-home-chat-brand">
          <div class="ai-home-icon ai-home-icon--sm">
            <n-icon :size="20" :component="icon" />
          </div>
          <div>
            <div class="ai-home-chat-title">{{ title }}</div>
            <div class="ai-home-chat-sub">{{ headerSub }}</div>
          </div>
        </div>
        <n-button size="small" quaternary @click="newChat">新对话</n-button>
      </header>

      <div ref="messagesRef" class="ai-home-messages">
        <div
          v-for="(m, i) in messages"
          :key="i"
          class="ai-home-msg"
          :class="m.role === 'user' ? 'ai-home-msg--user' : 'ai-home-msg--bot'"
        >
          <div
            v-if="m.role === 'assistant'"
            class="ai-home-bubble ai-home-bubble--bot"
            :class="{ 'ai-home-bubble--error': m.error, 'ai-home-bubble--streaming': m.streaming }"
          >
            <div
              v-if="
                showWorkflowProgress &&
                m.streaming &&
                m.workflow?.running &&
                m.workflow.currentTitle
              "
              class="ai-workflow-current"
              :class="{ 'ai-workflow-current--failed': m.workflow.failed }"
            >
              <span v-if="!m.workflow.failed" class="ai-workflow-spinner" aria-hidden="true" />
              正在执行：{{ m.workflow.currentTitle }}
            </div>
            <div
              v-else-if="m.streaming && richMarkdown && showWorkflowProgress"
              class="ai-workflow-wait"
            >
              {{ m.content ? "正在整理回答…" : "正在生成回答…" }}
            </div>
            <div v-else-if="m.streaming" class="ai-home-stream-text">
              {{ m.content }}<span class="ai-home-cursor">▍</span>
            </div>
            <MarkdownRichContent
              v-else-if="richMarkdown && m.content"
              :key="`md-${i}`"
              :content="m.content"
            />
            <div v-else-if="m.content" v-html="renderMarkdown(m.content)" />
            <div v-else class="ai-workflow-wait">（未收到回复内容）</div>
            <ChatMessageCitations
              v-if="showCitations && !m.streaming && m.citations?.length"
              :citations="m.citations"
            />
          </div>
          <div v-else class="ai-home-bubble ai-home-bubble--user">
            {{ m.content }}
          </div>
        </div>
      </div>

      <footer class="ai-home-footer">
        <n-input
          v-model:value="input"
          class="ai-chat-textarea"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          placeholder="继续提问…（Enter 发送，Shift+Enter 换行）"
          :disabled="sending"
          @keydown="onChatKeydown"
        />
        <n-button
          type="primary"
          class="ai-home-footer-send"
          :disabled="!canSend"
          :loading="sending"
          @click="sendMessage()"
        >
          <template #icon>
            <n-icon :component="SendOutline" />
          </template>
        </n-button>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.ai-home {
  background: linear-gradient(180deg, #f8fafc 0%, #f0fdfa 40%, #ffffff 100%);
  border-radius: var(--platform-radius);
  overflow: hidden;
}

.ai-home-welcome {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px 24px 48px;
  min-height: 0;
  overflow: auto;
}

.ai-home-hero {
  text-align: center;
  max-width: 560px;
  margin-bottom: 32px;
}

.ai-home-icon {
  width: 72px;
  height: 72px;
  margin: 0 auto 16px;
  border-radius: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #0d9488;
  background: linear-gradient(160deg, #f0fdfa 0%, #ccfbf1 100%);
  border: 1px solid rgba(13, 148, 136, 0.18);
  box-shadow: 0 4px 16px rgba(13, 148, 136, 0.1);
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
  color: #0f172a;
  letter-spacing: 0.02em;
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

.ai-home-landing-input {
  width: min(640px, 100%);
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.ai-home-landing-input :deep(.ai-chat-textarea.n-input) {
  border-radius: var(--platform-radius);
  box-shadow: var(--platform-shadow);
}

/* Naive UI：placeholder 与 textarea 分层定位，须同步字体/行高/内边距 */
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
  padding-bottom: 14px;
  padding-left: 0;
  padding-right: 0;
}

.ai-home :deep(.ai-chat-textarea .n-input__placeholder span) {
  line-height: 1.55;
}

.ai-home-send-btn {
  align-self: flex-end;
  min-width: 120px;
}

.ai-home-suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  max-width: 640px;
  margin-top: 20px;
}

.ai-home-chip {
  padding: 8px 14px;
  font-size: 13px;
  color: #0f766e;
  background: rgba(13, 148, 136, 0.08);
  border: 1px solid rgba(13, 148, 136, 0.16);
  border-radius: 999px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.ai-home-chip:hover:not(:disabled) {
  background: rgba(13, 148, 136, 0.14);
  border-color: rgba(13, 148, 136, 0.28);
}

.ai-home-chip:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.ai-home-chat {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.ai-home-chat-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--platform-border);
  background: var(--platform-surface);
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
  overflow-y: auto;
  padding: 20px 16px;
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
  background: linear-gradient(160deg, #0d9488 0%, #0f766e 100%);
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
  color: #0d9488;
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

.ai-home-footer {
  flex-shrink: 0;
  display: flex;
  gap: 10px;
  align-items: flex-end;
  padding: 12px 16px 16px;
  border-top: 1px solid var(--platform-border);
  background: var(--platform-surface);
}

.ai-home-footer :deep(.n-input) {
  flex: 1;
}

.ai-home-footer-send {
  flex-shrink: 0;
  width: 44px;
  height: 44px;
}

.ai-workflow-current {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 500;
  color: #0f766e;
  margin-bottom: 10px;
  padding-bottom: 10px;
  border-bottom: 1px dashed rgba(13, 148, 136, 0.2);
}

.ai-workflow-current--failed {
  color: #b91c1c;
  border-bottom-color: rgba(239, 68, 68, 0.25);
}

.ai-workflow-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(13, 148, 136, 0.25);
  border-top-color: #0d9488;
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
</style>
