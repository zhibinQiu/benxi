<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { useI18n } from "../composables/useI18n.js";
import { messages as localeMessages } from "../locales";
import { useAppPreferences } from "../composables/useAppPreferences";
import { NButton, NIcon, NSpin } from "naive-ui";
import { CloseOutline, SparklesOutline } from "@vicons/ionicons5";
import ChatComposer from "./ChatComposer.vue";
import ChatBubbleRetry from "./ChatBubbleRetry.vue";
import { renderMarkdown } from "../utils/markdown.js";
import { assistantChat, fetchChatConversationMessages } from "../api/client";
import { PLATFORM_APP_NAME } from "../constants/platform";
import {
  clearChatSession,
  loadChatSession,
  saveChatSession,
  serializeChatMessages,
} from "../utils/chatSessionPersist";

const ASSISTANT_SCOPE = "assistant";

const { t, chatScopeTitle } = useI18n();
const { locale } = useAppPreferences();

const open = defineModel("open", { type: Boolean, default: false });

const props = defineProps({
  anchorEl: { type: Object, default: null }});

const route = useRoute();

const WELCOME_MESSAGE = computed(() => ({
  role: "assistant",
  content: t("assistantFab.welcome", { appName: PLATFORM_APP_NAME }),
}));

const quickPrompts = computed(
  () => localeMessages[locale.value]?.assistantFab?.quickPrompts || []
);

const sending = ref(false);
const loadingHistory = ref(false);
const conversationId = ref(null);
const input = ref("");
const messages = ref([]);

function resetWelcomeMessage() {
  messages.value = [{ ...WELCOME_MESSAGE.value }];
}

resetWelcomeMessage();

watch(locale, () => {
  if (messages.value.length === 1 && messages.value[0]?.role === "assistant" && !conversationId.value) {
    resetWelcomeMessage();
  }
});
const pageHint = computed(() => {
  const title = route.meta?.title;
  const name = route.name;
  if (title && name) return `${title}（${name}）`;
  return title ? String(title) : name ? String(name) : "";
});

const messagesRef = ref(null);
const panelRef = ref(null);
const teleportReady = ref(false);

function resolveAnchorNode() {
  const raw = props.anchorEl;
  if (!raw) return null;
  if (raw instanceof HTMLElement) return raw;
  if (raw.$el instanceof HTMLElement) return raw.$el;
  if (raw.value instanceof HTMLElement) return raw.value;
  if (raw.value?.$el instanceof HTMLElement) return raw.value.$el;
  return null;
}

const OUTSIDE_CLOSE_IGNORE_SELECTOR =
  ".n-dialog, .n-modal, .n-popover, .n-dropdown, .n-tooltip, .platform-confirm-dialog";

function onDocumentKeydown(event) {
  if (open.value && event.key === "Escape") {
    open.value = false;
  }
}

function onOutsidePointerDown(event) {
  if (!open.value) return;
  const target = event.target;
  if (!(target instanceof Node)) return;
  if (panelRef.value?.contains(target)) return;
  if (resolveAnchorNode()?.contains(target)) return;
  if (target instanceof Element && target.closest(OUTSIDE_CLOSE_IGNORE_SELECTOR)) return;
  open.value = false;
}

function scrollToBottom() {
  nextTick(() => {
    const el = messagesRef.value;
    if (el) el.scrollTop = el.scrollHeight;
  });
}

watch(open, async (v) => {
  if (v) {
    scrollToBottom();
    document.addEventListener("keydown", onDocumentKeydown);
    document.addEventListener("pointerdown", onOutsidePointerDown, true);
  } else {
    document.removeEventListener("keydown", onDocumentKeydown);
    document.removeEventListener("pointerdown", onOutsidePointerDown, true);
  }
});

function renderMarkdownHtml(text) {
  return renderMarkdown(text || "");
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
      conversationId: conversationId.value});
    if (data?.conversation_id) {
      conversationId.value = data.conversation_id;
    }
    messages.value.push({ role: "assistant", content: data.reply });
  } catch (e) {
    messages.value.push({
      role: "assistant",
      content: t("assistantFab.errorReply", {
        error: e.message || t("assistantFab.serviceError"),
      }),
    });
  } finally {
    sending.value = false;
    scrollToBottom();
    persistAssistantSession();
  }
}

function onKeydown(e) {
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
  if (sending.value || loadingHistory.value) return false;
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

  messages.value = messages.value.slice(0, userIndex);
  await sendMessage(content);
}

function persistAssistantSession() {
  const serialized = serializeChatMessages(messages.value);
  if (!conversationId.value && serialized.length <= 1 && !input.value.trim()) {
    clearChatSession(ASSISTANT_SCOPE);
    return;
  }
  saveChatSession(ASSISTANT_SCOPE, {
    conversationId: conversationId.value,
    messages: serialized,
    input: input.value,
  });
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
        : [{ ...WELCOME_MESSAGE.value }];
    await scrollToBottom();
    persistAssistantSession();
  } catch (e) {
    messages.value.push({
      role: "assistant",
      content: t("assistantFab.loadHistoryFailed", {
        error: e.message || t("assistantFab.retryLater"),
      }),
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
  requestAnimationFrame(() => {
    teleportReady.value = true;
  });

  const cid =
    typeof route.query.assistantConversation === "string"
      ? route.query.assistantConversation
      : "";
  if (cid) {
    loadConversationFromId(cid);
    return;
  }
  const saved = loadChatSession(ASSISTANT_SCOPE);
  if (!saved) return;
  if (saved.input) input.value = saved.input;
  if (saved.conversationId) {
    loadConversationFromId(saved.conversationId);
    return;
  }
  if (Array.isArray(saved.messages) && saved.messages.length) {
    messages.value = saved.messages.map((m) => ({
      role: m.role,
      content: m.content || "",
    }));
  }
});

onBeforeUnmount(() => {
  document.removeEventListener("keydown", onDocumentKeydown);
  document.removeEventListener("pointerdown", onOutsidePointerDown, true);
});
</script>

<template>
  <Teleport v-if="teleportReady" to="body">
    <div class="assistant-root">
      <Transition name="assistant-panel">
        <div
          v-if="open"
          ref="panelRef"
          class="assistant-panel"
          role="dialog"
          :aria-label="t('assistantFab.ariaDialog')"
        >
        <header class="assistant-header">
          <div class="assistant-header-brand">
            <div class="assistant-avatar">
              <n-icon :size="20" :component="SparklesOutline" />
            </div>
            <div>
              <div class="assistant-title">{{ chatScopeTitle("assistant", "本析平台客服") }}</div>
              <div class="assistant-sub">{{ PLATFORM_APP_NAME }}</div>
            </div>
          </div>
          <div class="assistant-header-actions">
            <n-button quaternary circle size="small" :aria-label="t('assistantFab.ariaClose')" @click="open = false">
              <template #icon>
                <n-icon :component="CloseOutline" />
              </template>
            </n-button>
          </div>
        </header>

        <div v-if="loadingHistory" class="assistant-history-loading">
          <n-spin size="small" />
          <span>{{ t("chat.loadingConversation") }}</span>
        </div>

        <div v-else ref="messagesRef" class="assistant-messages">
          <div
            v-for="(m, i) in messages"
            :key="i"
            class="assistant-msg"
            :class="m.role === 'user' ? 'assistant-msg--user' : 'assistant-msg--bot'"
          >
            <div
              class="assistant-msg-stack"
              :class="m.role === 'user' ? 'assistant-msg-stack--user' : 'assistant-msg-stack--bot'"
            >
              <div
                v-if="m.role === 'assistant'"
                class="assistant-bubble assistant-bubble--bot"
                v-html="renderMarkdownHtml(m.content)"
              />
              <div v-else class="assistant-bubble assistant-bubble--user">
                {{ m.content }}
              </div>
              <ChatBubbleRetry
                v-if="m.role === 'assistant' && canRetryMessage(i, m)"
                align="start"
                @retry="retryMessage(i)"
              />
            </div>
          </div>
          <div v-if="sending" class="assistant-msg assistant-msg--bot">
            <div class="assistant-bubble assistant-bubble--bot assistant-bubble--typing">
              <n-spin size="small" />
              <span>{{ t("chat.thinking") }}</span>
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
            :placeholder="t('assistantFab.inputPlaceholder')"
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
  z-index: var(--platform-z-flyout);
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 12px;
  pointer-events: none;
}

.assistant-root > * {
  pointer-events: auto;
}

.assistant-panel {
  width: min(400px, calc(100vw - 32px));
  height: min(520px, calc(100vh - 120px));
  min-height: 320px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--platform-bg-elevated-solid, #fff);
  border-radius: var(--platform-radius, 14px);
  border: 1px solid var(--platform-glass-border, rgba(15, 23, 42, 0.08));
  box-shadow: var(--platform-shadow-lg);
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
  background: linear-gradient(135deg, var(--platform-accent-soft) 0%, rgba(241, 245, 249, 0.9) 100%);
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
  color: var(--platform-accent);
  background: #fff;
  box-shadow: 0 1px 4px color-mix(in srgb, var(--platform-accent) 20%, transparent);
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

.assistant-msg-stack {
  display: flex;
  flex-direction: column;
  max-width: 92%;
}

.assistant-msg-stack--user {
  align-items: flex-end;
}

.assistant-msg-stack--bot {
  align-items: flex-start;
}

.assistant-bubble {
  width: 100%;
  max-width: 100%;
  padding: 10px 12px;
  font-size: 13px;
  line-height: 1.55;
  border-radius: 12px;
  word-break: break-word;
}

.assistant-bubble--user {
  width: fit-content;
  max-width: 100%;
  background: var(--platform-accent-gradient);
  color: #fff;
  border-bottom-right-radius: 4px;
  white-space: pre-wrap;
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
  border: 1px solid var(--platform-accent-border);
  background: var(--platform-accent-muted);
  color: var(--platform-accent-pressed);
  cursor: pointer;
  transition: background 0.15s;
}

.assistant-chip:hover {
  background: var(--platform-accent-soft);
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
