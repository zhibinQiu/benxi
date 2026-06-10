<script setup>
import { computed, nextTick, onMounted, ref, watch } from "vue";
import {
  NAlert,
  NButton,
  NIcon,
  NInput,
  NSpin,
  NTag,
  NUpload,
  NUploadDragger,
  useMessage,
} from "naive-ui";
import { CloudUploadOutline, SendOutline } from "@vicons/ionicons5";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import AnalysisNotebookPanel from "../components/AnalysisNotebookPanel.vue";
import {
  createDataAnalysisSession,
  dataAnalysisChat,
  fetchDataAnalysisMeta,
  fetchDataAnalysisSession,
  uploadDataAnalysisDataset,
} from "../api/dataAnalysis";

const STORAGE_KEY = "data-analysis-session";
const message = useMessage();

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
      datasetId: datasetId.value,
    })
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
  if (p.file_type === "csv") {
    return `已加载 CSV「${p.filename}」约 ${sheet.rows} 行 × ${sheet.columns} 列\n字段：${cols || "—"}`;
  }
  return `已加载「${p.filename}」· 工作表「${sheet.name}」约 ${sheet.rows} 行 × ${sheet.columns} 列\n字段：${cols || "—"}`;
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
    message.success("数据文件已上传，可开始连续对话分析");
  } catch (e) {
    message.error(e.message || "上传失败");
  } finally {
    uploading.value = false;
  }
}

async function sendChat() {
  const text = chatInput.value.trim();
  if (!text) return;
  if (!datasetId.value || !sessionId.value) {
    message.warning("请先上传 Excel 或 CSV 文件");
    return;
  }
  if (!meta.value?.configured) {
    message.warning(meta.value?.service_hint || "AI 未配置");
    return;
  }
  chatting.value = true;
  chatInput.value = "";
  appendMessage("user", text);
  try {
    const data = await dataAnalysisChat(sessionId.value, {
      message: text,
      datasetId: datasetId.value,
    });
    if (data.session) {
      applySession(data.session);
    } else {
      appendMessage("assistant", data.reply || "已生成分析代码");
      if (data.cells_added?.length) {
        cells.value = [...cells.value, ...data.cells_added];
      }
    }
  } catch (e) {
    appendMessage("assistant", e.message || "分析失败");
    message.error(e.message || "分析失败");
  } finally {
    chatting.value = false;
  }
}

function onChatKeydown(e) {
  if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
    e.preventDefault();
    sendChat();
  }
}

watch([sessionId, datasetId], persistSession);

onMounted(async () => {
  await loadMeta();
  await restoreSession();
});
</script>

<template>
  <FeatureSubsystemShell fill :show-intro="false">
    <n-spin :show="loadingMeta" class="da-spin">
      <div class="data-analysis-layout">
        <aside class="chat-pane">
          <div class="pane-head">
            <h3>对话分析</h3>
            <p>上传 Excel / CSV，多轮追问，AI 将结合历史与 Notebook 结果继续分析</p>
          </div>

          <n-alert
            v-if="meta && !meta.configured"
            type="warning"
            :title="meta.service_hint || 'AI 未配置'"
            class="meta-alert"
          />

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
                <p>点击或拖拽上传 Excel / CSV</p>
                <p class="upload-limit">支持 .xlsx · .xls · .csv</p>
                <p v-if="meta" class="upload-limit">最大 {{ meta.max_file_mb }}MB</p>
              </div>
            </n-upload-dragger>
          </n-upload>

          <div v-if="profile" class="dataset-chip">
            <n-tag type="success" size="small" :bordered="false">已绑定数据</n-tag>
            <span>{{ profile.filename }}</span>
            <n-tag v-if="messages.length > 1" size="small" :bordered="false">
              {{ Math.floor(messages.filter((m) => m.role === "user").length) }} 轮对话
            </n-tag>
          </div>

          <div ref="chatListRef" class="chat-list">
            <div
              v-for="(msg, idx) in messages"
              :key="idx"
              class="chat-item"
              :class="msg.role"
            >
              <div class="bubble">{{ msg.content }}</div>
            </div>
            <div v-if="!messages.length" class="chat-placeholder">
              上传文件后连续提问，例如：<br />
              「按月份汇总销售额」→「再画折线图」→「找出异常月份」
            </div>
          </div>

          <div class="chat-input-row">
            <n-input
              v-model:value="chatInput"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 5 }"
              placeholder="继续追问或提出新的分析任务…（Ctrl/Cmd + Enter 发送）"
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
              发送
            </n-button>
          </div>
        </aside>

        <section class="notebook-pane">
          <div class="pane-head notebook-head">
            <h3>Notebook</h3>
            <p>每轮对话可追加单元格 · 点击 ▶ 运行 · pandas / numpy / matplotlib / seaborn</p>
          </div>
          <AnalysisNotebookPanel
            v-if="sessionId"
            :session-id="sessionId"
            :cells="cells"
            @update:cells="cells = $event"
          />
          <div v-else class="notebook-wait">
            上传数据文件后将自动创建 Notebook 会话
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
  grid-template-columns: minmax(320px, 38%) 1fr;
  height: 100%;
  min-height: 0;
  background: #fff;
}

.chat-pane,
.notebook-pane {
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.chat-pane {
  border-right: 1px solid #ececef;
  padding: 14px 14px 12px;
}

.notebook-pane {
  min-width: 0;
}

.pane-head h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.pane-head p {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--n-text-color-3);
}

.notebook-head {
  padding: 14px 14px 0;
}

.meta-alert {
  margin: 10px 0;
}

.upload-box {
  margin-top: 12px;
}

.upload-inner {
  padding: 8px 0;
  text-align: center;
  color: var(--n-text-color-2);
}

.upload-limit {
  margin-top: 4px;
  font-size: 12px;
  color: var(--n-text-color-3);
}

.dataset-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
  font-size: 13px;
  flex-wrap: wrap;
}

.chat-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
  margin: 12px 0;
  padding-right: 4px;
}

.chat-item {
  display: flex;
  margin-bottom: 10px;
}

.chat-item.user {
  justify-content: flex-end;
}

.chat-item.system {
  justify-content: center;
}

.chat-item .bubble {
  max-width: 92%;
  padding: 8px 11px;
  border-radius: 10px;
  font-size: 13px;
  line-height: 1.5;
  white-space: pre-wrap;
}

.chat-item.user .bubble {
  background: var(--n-primary-color);
  color: #fff;
}

.chat-item.assistant .bubble {
  background: #f4f5f7;
}

.chat-item.system .bubble {
  background: var(--platform-accent-soft);
  color: var(--platform-accent-pressed);
  font-size: 12px;
}

.chat-placeholder {
  margin-top: 20%;
  text-align: center;
  color: var(--n-text-color-3);
  font-size: 13px;
  padding: 0 12px;
  line-height: 1.6;
}

.chat-input-row {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
  align-items: end;
}

.notebook-wait {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--n-text-color-3);
  font-size: 13px;
}

@media (max-width: 960px) {
  .data-analysis-layout {
    grid-template-columns: 1fr;
    grid-template-rows: 45% 55%;
  }

  .chat-pane {
    border-right: none;
    border-bottom: 1px solid #ececef;
  }
}
</style>
