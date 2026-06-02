<script setup>
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { NButton, NIcon, NSpin } from "naive-ui";
import {
  CloseOutline,
  SparklesOutline,
  TimeOutline,
} from "@vicons/ionicons5";
import ChatComposer from "./ChatComposer.vue";
import { marked } from "marked";
import { assistantChat, fetchChatConversationMessages } from "../api/client";
import { PLATFORM_APP_NAME } from "../constants/platform";
import { navigateWithReturn } from "../utils/navigationReturn";

const open = defineModel("open", { type: Boolean, default: false });

const route = useRoute();
const router = useRouter();

marked.setOptions({ gfm: true, breaks: true });

const WELCOME_MESSAGE = {
  role: "assistant",
  content: `你好，我是${PLATFORM_APP_NAME}智能助手。可以问我菜单在哪、如何上传文档、PDF 翻译、权限与后台任务等问题。`,
};

const sending = ref(false);
const loadingHistory = ref(false);
const conversationId = ref(null);
const input = ref("");
const messages = ref([{ ...WELCOME_MESSAGE }]);

const quickPrompts = [
  "如何上传和管理文档？",
  "PDF 翻译怎么用？",
  "文档分享权限有哪些级别？",
  "后台任务如何终止？",
];

const pageHint = computed(() => {
  const title = route.meta?.title;
  const name = route.name;
  if (title && name) return `${title}（${name}）`;
  return title ? String(title) : name ? String(name) : "";
});

const messagesRef = ref(null);

function scrollToBottom() {
  nextTick(() => {
    const el = messagesRef.value;
    if (el) el.scrollTop = el.scrollHeight;
  });
}

watch(open, (v) => {
  if (v) scrollToBottom();
});

function renderMarkdown(text) {
  try {
    return marked.parse(text || "");
  } catch {
    return text || "";
  }
}

function historyForApi() {
  return messages.value
    .filter((m) => m.role === "user" || m.role === "assistant")
    .slice(-10)
    .map((m) => ({ role: m.role, content: m.content }));
}

async function sendMessage(text) {
  const msg = (text || input.value).trim();
  if (!msg || sending.value) return;
  input.value = "";
  messages.value.push({ role: "user", content: msg });
  scrollToBottom();
  sending.value = true;
  try {
    const history = historyForApi().slice(0, -1);
    const data = await assistantChat({
      message: msg,
      history,
      page_hint: pageHint.value || null,
      conversationId: conversationId.value,
    });
    if (data?.conversation_id) {
      conversationId.value = data.conversation_id;
    }
    messages.value.push({ role: "assistant", content: data.reply });
  } catch (e) {
    messages.value.push({
      role: "assistant",
      content: `抱歉，暂时无法回答：${e.message || "服务异常"}。请稍后重试或联系管理员。`,
    });
  } finally {
    sending.value = false;
    scrollToBottom();
  }
}

function onKeydown(e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

function goToHistory() {
  navigateWithReturn(
    router,
    { name: "chat-history", params: { scope: "assistant" } },
    route
  );
}

function startNewChat() {
  conversationId.value = null;
  messages.value = [{ ...WELCOME_MESSAGE }];
  input.value = "";
  if (route.query.assistantConversation) {
    const { assistantConversation: _id, ...rest } = route.query;
    router.replace({ ...route, query: rest });
  }
}

async function loadConversationFromId(id) {
  if (!id) return;
  loadingHistory.value = true;
  open.value = true;
  try {
    const rows = (await fetchChatConversationMessages("assistant", id)) || [];
    conversationId.value = id;
    messages.value =
      rows.length > 0
        ? rows.map((m) => ({ role: m.role, content: m.content }))
        : [{ ...WELCOME_MESSAGE }];
    await scrollToBottom();
  } catch (e) {
    messages.value.push({
      role: "assistant",
      content: `加载历史对话失败：${e.message || "请稍后重试"}`,
    });
  } finally {
    loadingHistory.value = false;
  }
}

watch(
  () => route.query.assistantConversation,
  (id) => {
    const cid = typeof id === "string" ? id : "";
    if (cid) loadConversationFromId(cid);
  }
);

onMounted(() => {
  const cid =
    typeof route.query.assistantConversation === "string"
      ? route.query.assistantConversation
      : "";
  if (cid) loadConversationFromId(cid);
});
</script>

<template>
  <Teleport to="body">
  <div class="assistant-root" :class="{ 'assistant-root--open': open }">
    <Transition name="assistant-panel">
      <div v-if="open" class="assistant-panel" role="dialog" aria-label="智能客服">
        <header class="assistant-header">
          <div class="assistant-header-brand">
            <div class="assistant-avatar">
              <n-icon :size="20" :component="SparklesOutline" />
            </div>
            <div>
              <div class="assistant-title">智能助手</div>
              <div class="assistant-sub">{{ PLATFORM_APP_NAME }}</div>
            </div>
          </div>
          <div class="assistant-header-actions">
            <n-button quaternary size="small" @click="goToHistory">
              <template #icon>
                <n-icon :component="TimeOutline" />
              </template>
              历史
            </n-button>
            <n-button quaternary size="small" @click="startNewChat">新对话</n-button>
            <n-button quaternary circle size="small" aria-label="关闭" @click="open = false">
              <template #icon>
                <n-icon :component="CloseOutline" />
              </template>
            </n-button>
          </div>
        </header>

        <div v-if="loadingHistory" class="assistant-history-loading">
          <n-spin size="small" />
          <span>正在加载对话…</span>
        </div>

        <div v-else ref="messagesRef" class="assistant-messages">
          <div
            v-for="(m, i) in messages"
            :key="i"
            class="assistant-msg"
            :class="m.role === 'user' ? 'assistant-msg--user' : 'assistant-msg--bot'"
          >
            <div
              v-if="m.role === 'assistant'"
              class="assistant-bubble assistant-bubble--bot"
              v-html="renderMarkdown(m.content)"
            />
            <div v-else class="assistant-bubble assistant-bubble--user">
              {{ m.content }}
            </div>
          </div>
          <div v-if="sending" class="assistant-msg assistant-msg--bot">
            <div class="assistant-bubble assistant-bubble--bot assistant-bubble--typing">
              <n-spin size="small" />
              <span>正在思考…</span>
            </div>
          </div>
        </div>

        <div v-if="!sending" class="assistant-quick">
          <button
            v-for="q in quickPrompts"
            :key="q"
            type="button"
            class="assistant-chip"
            @click="sendMessage(q)"
          >
            {{ q }}
          </button>
        </div>

        <footer class="assistant-footer">
          <ChatComposer
            v-model="input"
            placeholder="描述你的问题，Enter 发送"
            :disabled="sending"
            :loading="sending"
            :min-rows="1"
            :max-rows="3"
            @keydown="onKeydown"
            @send="sendMessage()"
          />
        </footer>
      </div>
    </Transition>
  </div>
  </Teleport>
</template>

<style scoped>
.assistant-root {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 1200;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 12px;
  pointer-events: none;
}

.assistant-root > * {
  pointer-events: auto;
}

.assistant-fab {
  width: 42px;
  height: 42px;
  border: 1px solid rgba(13, 148, 136, 0.22);
  border-radius: 50%;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #0d9488;
  background: linear-gradient(160deg, #f0fdfa 0%, #ccfbf1 100%);
  box-shadow:
    0 2px 8px rgba(13, 148, 136, 0.12),
    0 1px 3px rgba(15, 23, 42, 0.06);
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease,
    background 0.2s ease;
}

.assistant-fab:hover {
  transform: translateY(-1px);
  background: linear-gradient(160deg, #ecfdf5 0%, #99f6e4 100%);
  box-shadow:
    0 4px 12px rgba(13, 148, 136, 0.16),
    0 2px 6px rgba(15, 23, 42, 0.06);
}

.assistant-fab--active {
  color: #64748b;
  border-color: rgba(100, 116, 139, 0.25);
  background: linear-gradient(160deg, #f8fafc 0%, #e2e8f0 100%);
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.1);
}

.assistant-panel {
  width: min(400px, calc(100vw - 32px));
  height: min(520px, calc(100vh - 120px));
  display: flex;
  flex-direction: column;
  background: var(--platform-surface, #fff);
  border-radius: 14px;
  border: 1px solid var(--platform-border, rgba(15, 23, 42, 0.08));
  box-shadow:
    0 12px 40px rgba(15, 23, 42, 0.14),
    0 4px 12px rgba(15, 23, 42, 0.06);
  overflow: hidden;
}

.assistant-header-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}

.assistant-history-loading {
  flex: 1;
  min-height: 80px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #64748b;
  font-size: 13px;
  background: #f8fafc;
}

.assistant-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  background: linear-gradient(135deg, rgba(13, 148, 136, 0.12) 0%, rgba(241, 245, 249, 0.9) 100%);
  border-bottom: 1px solid var(--platform-border, rgba(15, 23, 42, 0.08));
}

.assistant-header-brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.assistant-avatar {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #0d9488;
  background: #fff;
  box-shadow: 0 1px 4px rgba(13, 148, 136, 0.2);
}

.assistant-title {
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
  line-height: 1.3;
}

.assistant-sub {
  font-size: 11px;
  color: #64748b;
}

.assistant-messages {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 14px 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  background: #f8fafc;
}

.assistant-msg {
  display: flex;
}

.assistant-msg--user {
  justify-content: flex-end;
}

.assistant-msg--bot {
  justify-content: flex-start;
}

.assistant-bubble {
  max-width: 92%;
  padding: 10px 12px;
  font-size: 13px;
  line-height: 1.55;
  border-radius: 12px;
  word-break: break-word;
}

.assistant-bubble--user {
  background: linear-gradient(135deg, #14b8a6, #0d9488);
  color: #fff;
  border-bottom-right-radius: 4px;
}

.assistant-bubble--bot {
  background: #fff;
  color: #334155;
  border: 1px solid var(--platform-border, rgba(15, 23, 42, 0.08));
  border-bottom-left-radius: 4px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}

.assistant-bubble--typing {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #64748b;
}

.assistant-bubble--bot :deep(p) {
  margin: 0.35em 0;
}

.assistant-bubble--bot :deep(p:first-child) {
  margin-top: 0;
}

.assistant-bubble--bot :deep(p:last-child) {
  margin-bottom: 0;
}

.assistant-bubble--bot :deep(ul),
.assistant-bubble--bot :deep(ol) {
  margin: 0.35em 0;
  padding-left: 1.2em;
}

.assistant-bubble--bot :deep(code) {
  font-size: 0.9em;
  padding: 0.1em 0.35em;
  border-radius: 4px;
  background: #f1f5f9;
}

.assistant-quick {
  flex-shrink: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px 12px 0;
  background: #fff;
}

.assistant-chip {
  font-size: 11px;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid rgba(13, 148, 136, 0.35);
  background: rgba(13, 148, 136, 0.06);
  color: #0f766e;
  cursor: pointer;
  transition: background 0.15s;
}

.assistant-chip:hover {
  background: rgba(13, 148, 136, 0.14);
}

.assistant-footer {
  flex-shrink: 0;
  padding: 10px 12px 12px;
  background: #fff;
  border-top: 1px solid var(--platform-border, rgba(15, 23, 42, 0.08));
}

.assistant-panel-enter-active,
.assistant-panel-leave-active {
  transition:
    opacity 0.22s ease,
    transform 0.22s ease;
}

.assistant-panel-enter-from,
.assistant-panel-leave-to {
  opacity: 0;
  transform: translateY(12px) scale(0.96);
}
</style>
