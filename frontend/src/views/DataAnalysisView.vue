<script setup>
defineOptions({ name: "DataAnalysisView" });
import { useI18n } from "../composables/useI18n.js";
import { usePlatformUi } from "../composables/usePlatformUi";
import { computed, nextTick, onMounted, ref, watch } from "vue";
import {
  NAlert,
  NButton,
  NIcon,
  NInput,
  NSpin,
  NTag,
  NUpload,
  NUploadDragger } from "naive-ui";
import { CloudUploadOutline, SendOutline } from "@vicons/ionicons5";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import AnalysisNotebookPanel from "../components/AnalysisNotebookPanel.vue";
import ChatBubbleActions from "../components/ChatBubbleActions.vue";
import { copyChatMessageText, shareChatMessageText } from "../utils/chatBubbleActions.js";
import {
  createDataAnalysisSession,
  dataAnalysisChat,
  fetchDataAnalysisMeta,
  fetchDataAnalysisSession,
  uploadDataAnalysisDataset } from "../api/dataAnalysis";
import { FEATURE_UNAVAILABLE } from "../utils/uiMessage";

const STORAGE_KEY = "data-analysis-session";
const ui = usePlatformUi();
const { t } = useI18n();

const meta = ref(null);
const loadingMeta = ref(true);
const sessionId = ref("");
const datasetId = ref("");
const profile = ref(null);
const messages = ref([]);
const cells = ref([]);
const chatInput = ref("");
const chatting = ref(false);
const uploading = ref(false);
const chatListRef = ref(null);

const acceptedFormats = computed(() => {
  const exts = meta.value?.accepted_extensions || [".xlsx", ".xls", ".csv"];
  return exts.join(",");
});

const canChat = computed(
  () => Boolean(datasetId.value) && Boolean(sessionId.value) && meta.value?.configured
);

function persistSession() {
  if (!sessionId.value) return;
  sessionStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      sessionId: sessionId.value,
      datasetId: datasetId.value})
  );
}

function applySession(data) {
  sessionId.value = data.session_id;
  datasetId.value = data.dataset_id || datasetId.value;
  profile.value = data.profile || profile.value;
  messages.value = data.messages || [];
  cells.value = data.cells || [];
  persistSession();
}

async function loadMeta() {
  loadingMeta.value = true;
  try {
    meta.value = await fetchDataAnalysisMeta();
  } catch (e) {
    meta.value = { configured: false, service_hint: e.message };
  } finally {
    loadingMeta.value = false;
  }
}

async function restoreSession() {
  const raw = sessionStorage.getItem(STORAGE_KEY);
  if (!raw) return;
  try {
    const saved = JSON.parse(raw);
    if (!saved?.sessionId) return;
    const data = await fetchDataAnalysisSession(saved.sessionId);
    applySession(data);
  } catch {
    sessionStorage.removeItem(STORAGE_KEY);
  }
}

async function startSessionWithDataset(uploaded) {
  const sess = await createDataAnalysisSession({ datasetId: uploaded.dataset_id });
  applySession(sess);
  appendMessage("system", profileSummaryText(uploaded.profile));
}

function appendMessage(role, content) {
  messages.value.push({ role, content });
  nextTick(() => {
    if (chatListRef.value) {
      chatListRef.value.scrollTop = chatListRef.value.scrollHeight;
    }
  });
}

function profileSummaryText(p) {
  if (!p) return "";
  const sheet = (p.sheets || [])[0];
  if (!sheet) return `${p.filename}`;
  const cols = (sheet.column_profiles || []).map((c) => c.name).join("、");
  const fields = cols || t("dataAnalysis.fieldsFallback");
  if (p.file_type === "csv") {
    return t("dataAnalysis.profileCsv", {
      filename: p.filename,
      rows: sheet.rows,
      columns: sheet.columns,
      fields,
    });
  }
  return t("dataAnalysis.profileSheet", {
    filename: p.filename,
    sheet: sheet.name,
    rows: sheet.rows,
    columns: sheet.columns,
    fields,
  });
}

async function onUploadChange({ file }) {
  const raw = file?.file;
  if (!raw) return;
  uploading.value = true;
  try {
    const data = await uploadDataAnalysisDataset(raw);
    datasetId.value = data.dataset_id;
    profile.value = data.profile;
    await startSessionWithDataset(data);
    ui.success(t("dataAnalysis.uploadSuccess"));
  } catch (e) {
    ui.error(e.message || t("dataAnalysis.uploadFailed"));
  } finally {
    uploading.value = false;
  }
}

async function sendChat() {
  const text = chatInput.value.trim();
  if (!text) return;
  await sendChatText(text);
}

async function sendChatText(text) {
  if (!text) return;
  if (!datasetId.value || !sessionId.value) {
    ui.warning(t("dataAnalysis.uploadFirst"));
    return;
  }
  if (!meta.value?.configured) {
    ui.warning(FEATURE_UNAVAILABLE);
    return;
  }
  chatting.value = true;
  chatInput.value = "";
  appendMessage("user", text);
  try {
    const data = await dataAnalysisChat(sessionId.value, {
      message: text,
      datasetId: datasetId.value});
    if (data.session) {
      applySession(data.session);
    } else {
      appendMessage("assistant", data.reply || t("dataAnalysis.analysisGenerated"));
      if (data.cells_added?.length) {
        cells.value = [...cells.value, ...data.cells_added];
      }
    }
  } catch (e) {
    appendMessage("assistant", e.message || t("dataAnalysis.analysisFailed"));
    ui.error(e.message || t("dataAnalysis.analysisFailed"));
  } finally {
    chatting.value = false;
  }
}

function findUserIndexBefore(index) {
  for (let i = index - 1; i >= 0; i -= 1) {
    if (messages.value[i]?.role === "user") return i;
  }
  return -1;
}

function canRetryMessage(index, message) {
  if (chatting.value || message?.role !== "assistant") return false;
  return findUserIndexBefore(index) >= 0;
}

function canShowMessageActions(index, message) {
  if (chatting.value || message?.role !== "assistant") return false;
  if (!String(message?.content || "").trim()) return false;
  return findUserIndexBefore(index) >= 0;
}

async function copyAssistantMessage(message) {
  await copyChatMessageText(message?.content, { ui, t });
}

async function shareAssistantMessage(message) {
  await shareChatMessageText(message?.content, {
    ui,
    t,
    title: t("dataAnalysis.chatTitle"),
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

  messages.value = messages.value.slice(0, userIndex);
  await sendChatText(content);
}

function onChatKeydown(e) {
  if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
    e.preventDefault();
    sendChat();
  }
}

const userMessageCount = computed(
  () => Math.floor(messages.value.filter((m) => m.role === "user").length)
);

watch([sessionId, datasetId], persistSession);

onMounted(async () => {
  await loadMeta();
  await restoreSession();
});
</script>

<template>
  <FeatureSubsystemShell fill :show-intro="false">
    <n-spin :show="loadingMeta" class="da-spin" local>
      <div class="data-analysis-layout">
        <aside class="chat-pane">
          <div class="pane-head">
            <h3>{{ t("dataAnalysis.chatTitle") }}</h3>
            <p>{{ t("dataAnalysis.chatDesc") }}</p>
          </div>

          <n-alert
            v-if="meta && !meta.configured"
            type="warning"
            :title="t('dataAnalysis.unavailableTitle')"
            class="meta-alert"
          >
            {{ FEATURE_UNAVAILABLE }}
          </n-alert>

          <n-upload
            :show-file-list="false"
            :default-upload="false"
            :accept="acceptedFormats"
            :disabled="uploading"
            @change="onUploadChange"
          >
            <n-upload-dragger class="upload-box">
              <div class="upload-inner">
                <n-icon size="28" :depth="3"><CloudUploadOutline /></n-icon>
                <p>{{ t("dataAnalysis.uploadPrompt") }}</p>
                <p class="upload-limit">{{ t("dataAnalysis.uploadFormats") }}</p>
                <p v-if="meta" class="upload-limit">{{ t("dataAnalysis.uploadMaxSize", { size: meta.max_file_mb }) }}</p>
              </div>
            </n-upload-dragger>
          </n-upload>

          <div v-if="profile" class="dataset-chip">
            <n-tag type="success" size="small" :bordered="false">{{ t("dataAnalysis.datasetBound") }}</n-tag>
            <span>{{ profile.filename }}</span>
            <n-tag v-if="messages.length > 1" size="small" :bordered="false">
              {{ t("dataAnalysis.chatRounds", { count: userMessageCount }) }}
            </n-tag>
          </div>

          <div ref="chatListRef" class="chat-list">
            <div
              v-for="(msg, idx) in messages"
              :key="idx"
              class="chat-item"
              :class="msg.role"
            >
              <div
                class="chat-item-stack"
                :class="msg.role === 'user' ? 'chat-item-stack--user' : 'chat-item-stack--bot'"
              >
                <div class="bubble">{{ msg.content }}</div>
                <ChatBubbleActions
                  v-if="canShowMessageActions(idx, msg)"
                  align="start"
                  :show-retry="canRetryMessage(idx, msg)"
                  :retry-disabled="chatting"
                  :feedback="msg.feedback || null"
                  @copy="copyAssistantMessage(msg)"
                  @share="shareAssistantMessage(msg)"
                  @retry="retryMessage(idx)"
                  @feedback="setMessageFeedback(idx, $event)"
                />
              </div>
            </div>
            <div v-if="!messages.length" class="chat-placeholder">
              {{ t("dataAnalysis.chatPlaceholder") }}
            </div>
          </div>

          <div class="chat-input-row">
            <n-input
              v-model:value="chatInput"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 5 }"
              :placeholder="t('dataAnalysis.inputPlaceholder')"
              :disabled="chatting || !canChat"
              @keydown="onChatKeydown"
            />
            <n-button
              type="primary"
              :loading="chatting"
              :disabled="!canChat"
              @click="sendChat"
            >
              <template #icon><n-icon><SendOutline /></n-icon></template>
              {{ t("dataAnalysis.send") }}
            </n-button>
          </div>
        </aside>

        <section class="notebook-pane">
          <div class="pane-head notebook-head">
            <h3>{{ t("dataAnalysis.notebookTitle") }}</h3>
            <p>{{ t("dataAnalysis.notebookDesc") }}</p>
          </div>
          <AnalysisNotebookPanel
            v-if="sessionId"
            :session-id="sessionId"
            :cells="cells"
            :libraries="meta?.builtin_libraries"
            @update:cells="cells = $event"
          />
          <div v-else class="notebook-wait">
            {{ t("dataAnalysis.notebookWait") }}
          </div>
        </section>
      </div>
    </n-spin>
  </FeatureSubsystemShell>
</template>

<style scoped>
.da-spin {
  height: 100%;
}

.da-spin :deep(.n-spin-content) {
  height: 100%;
}

.data-analysis-layout {
  display: grid;
  grid-template-columns: minmax(0, 38%) minmax(0, 1fr);
  height: 100%;
  min-height: 0;
  min-width: 0;
  max-width: 100%;
  background: var(--platform-bg-elevated);
  box-sizing: border-box;
  overflow: hidden;
}

.chat-pane,
.notebook-pane {
  min-height: 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.chat-pane {
  border-right: 1px solid var(--platform-border);
  padding: 17px 17px 14px;
}

.notebook-pane {
  min-width: 0;
}

.pane-head h3 {
  margin: 0;
  font-size: 18px;
}

.pane-head p {
  margin: 5px 0 0;
  font-size: 14px;
  color: var(--n-text-color-3);
}

.notebook-head {
  padding: 17px 17px 0;
}

.meta-alert {
  margin: 12px 0;
}

.upload-box {
  margin-top: 14px;
}

.upload-inner {
  padding: 10px 0;
  text-align: center;
  color: var(--n-text-color-2);
}

.upload-limit {
  margin-top: 5px;
  font-size: 14px;
  color: var(--n-text-color-3);
}

.dataset-chip {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
  font-size: 16px;
  flex-wrap: wrap;
}

.chat-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
  margin: 14px 0;
  padding-right: 5px;
}

.chat-item {
  display: flex;
  margin-bottom: 12px;
}

.chat-item-stack {
  display: flex;
  flex-direction: column;
  max-width: 92%;
}

.chat-item-stack--user {
  align-items: flex-end;
  margin-left: auto;
}

.chat-item-stack--bot {
  align-items: flex-start;
}

.chat-item.user {
  justify-content: flex-end;
}

.chat-item.system {
  justify-content: center;
}

.chat-item .bubble {
  width: 100%;
  max-width: 100%;
  padding: 10px 13px;
  border-radius: 12px;
  font-size: 16px;
  line-height: 1.5;
  white-space: pre-wrap;
}

.chat-item.user .bubble {
  width: fit-content;
  max-width: 100%;
  background: var(--platform-bg-tertiary);
  color: var(--platform-text);
  border: 1px solid var(--platform-border);
}

.chat-item.assistant .bubble {
  padding: 5px 0;
  border-radius: 0;
  background: transparent;
  color: var(--platform-text);
}

.chat-item.system .bubble {
  background: var(--platform-accent-soft);
  color: var(--platform-accent-pressed);
  font-size: 14px;
}

.chat-placeholder {
  margin-top: 20%;
  text-align: center;
  color: var(--n-text-color-3);
  font-size: 16px;
  padding: 0 14px;
  line-height: 1.6;
  white-space: pre-line;
}

.chat-input-row {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 10px;
  align-items: end;
}

.notebook-wait {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--n-text-color-3);
  font-size: 16px;
}

@media (max-width: 960px) {
  .data-analysis-layout {
    grid-template-columns: 1fr;
    grid-template-rows: 45% 55%;
  }

  .chat-pane {
    border-right: none;
    border-bottom: 1px solid var(--platform-border);
  }
}
</style>
