<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import {
  NAlert,
  NButton,
  NCard,
  NCheckbox,
  NDrawer,
  NGi,
  NGrid,
  NIcon,
  NInput,
  NModal,
  NSelect,
  NSpace,
  NSpin,
  NTag,
  NText,
  useDialog,
  useMessage,
} from "naive-ui";
import {
  ArrowBackOutline,
  MicOutline,
  StopCircleOutline,
  CopyOutline,
  CloudUploadOutline,
  SparklesOutline,
  RadioOutline,
  SaveOutline,
  FolderOpenOutline,
  TrashOutline,
} from "@vicons/ionicons5";
import FileDropZone from "../components/FileDropZone.vue";
import FeaturePageToolbar from "../components/FeaturePageToolbar.vue";
import AudioWaveform from "../components/AudioWaveform.vue";
import {
  deleteMeetingRecord,
  fetchMeetingRecord,
  fetchSpeechMeta,
  listMeetingRecords,
  saveMeetingRecord,
  summarizeSpeech,
  transcribeSpeech,
} from "../api/client";

const router = useRouter();
const message = useMessage();
const dialog = useDialog();

const meta = ref(null);
const loadingMeta = ref(true);
const sourceMode = ref("record");
const audioFile = ref(null);
const language = ref("");
const diarize = ref(true);
const autoSummarize = ref(true);
const streamRecognize = ref(true);
const transcript = ref("");
const segments = ref([]);
const liveSegments = ref([]);
const summary = ref("");
const summaryBlocks = ref([]);
const summaryStyle = ref("minutes");
const saving = ref(false);
const saveModalOpen = ref(false);
const saveTitle = ref("");
const recordsDrawerOpen = ref(false);
const recordsLoading = ref(false);
const records = ref([]);
const recordsPage = ref(1);
const recordsTotal = ref(0);
const viewingRecord = ref(null);
const recordDetailLoading = ref(false);
const transcribing = ref(false);
const summarizing = ref(false);
const error = ref("");

const recording = ref(false);
const recordSeconds = ref(0);
let fullRecorder = null;
let segmentRecorder = null;
let fullChunks = [];
let segmentChunks = [];
let recordTimer = null;
let recordStream = null;
let recordMime = "audio/webm";
let streamChunkId = 0;
let segmentStopReason = "final";
let hasSpeechInChunk = false;
let silenceMs = 0;
let speechMs = 0;
let lastLevelTs = 0;

const SILENCE_THRESHOLD = 0.018;
const SILENCE_MS = 1400;
const MIN_SPEECH_MS = 600;

const languageOptions = [
  { label: "自动检测", value: "" },
  { label: "中文 (zh)", value: "zh" },
  { label: "英语 (en)", value: "en" },
  { label: "日语 (ja)", value: "ja" },
  { label: "韩语 (ko)", value: "ko" },
];

const summaryStyleOptions = [
  { label: "会议纪要", value: "minutes" },
  { label: "简要要点", value: "brief" },
  { label: "详细总结", value: "detailed" },
];

const configured = computed(() => meta.value?.configured ?? false);

const pendingStreamCount = computed(
  () => liveSegments.value.filter((s) => s.status === "transcribing").length
);

const canTranscribe = computed(
  () =>
    configured.value &&
    !transcribing.value &&
    !!audioFile.value &&
    !(recording.value && streamRecognize.value)
);

const canSummarize = computed(
  () =>
    configured.value &&
    meta.value?.summarize_available &&
    !summarizing.value &&
    (!!transcript.value.trim() || segments.value.length > 0)
);

const canSave = computed(
  () => !saving.value && (segments.value.length > 0 || !!transcript.value.trim() || !!summary.value.trim())
);

const recordHint = computed(() => {
  if (recording.value) {
    const streamHint = streamRecognize.value ? "，停顿后自动转写" : "";
    return `录音中 ${formatDuration(recordSeconds.value)}${streamHint}`;
  }
  if (audioFile.value && sourceMode.value === "record") {
    return `${audioFile.value.name}（${formatDuration(recordSeconds.value)}）`;
  }
  return "点击开始录音，再次点击停止";
});

function formatDuration(sec) {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

function formatTime(sec) {
  return formatDuration(sec);
}

function speakerColor(speaker) {
  const n = parseInt(String(speaker).replace(/\D/g, ""), 10) || 1;
  const colors = ["#2080f0", "#18a058", "#f0a020", "#d03050", "#7c3aed"];
  return colors[(n - 1) % colors.length];
}

function segmentsToText(segs) {
  return segs.map((s) => `${s.speaker} [${formatTime(s.start)}]: ${s.text}`).join("\n");
}

function rebuildTranscript() {
  transcript.value = segments.value.length ? segmentsToText(segments.value) : "";
}

async function loadMeta() {
  loadingMeta.value = true;
  try {
    meta.value = await fetchSpeechMeta();
    if (meta.value?.default_language) language.value = meta.value.default_language;
    if (!meta.value?.diarization_available) diarize.value = false;
  } catch (e) {
    error.value = e.message;
  } finally {
    loadingMeta.value = false;
  }
}

function clearRecording() {
  if (recordTimer) {
    clearInterval(recordTimer);
    recordTimer = null;
  }
  if (recordStream) {
    recordStream.getTracks().forEach((t) => t.stop());
    recordStream = null;
  }
  fullRecorder = null;
  segmentRecorder = null;
  fullChunks = [];
  segmentChunks = [];
  hasSpeechInChunk = false;
  silenceMs = 0;
  speechMs = 0;
  recording.value = false;
}

function onWaveLevel(rms) {
  if (!recording.value || !streamRecognize.value) return;
  const now = performance.now();
  const dt = lastLevelTs ? now - lastLevelTs : 16;
  lastLevelTs = now;

  if (rms > SILENCE_THRESHOLD) {
    speechMs += dt;
    silenceMs = 0;
    hasSpeechInChunk = true;
  } else if (hasSpeechInChunk) {
    silenceMs += dt;
    if (silenceMs >= SILENCE_MS && speechMs >= MIN_SPEECH_MS) {
      void flushStreamChunk();
      hasSpeechInChunk = false;
      speechMs = 0;
      silenceMs = 0;
    }
  }
}

async function transcribeSegmentBlob(blob, chunkTime) {
  const id = ++streamChunkId;
  liveSegments.value.push({
    id,
    status: "transcribing",
    text: "",
    timeLabel: formatDuration(chunkTime),
  });
  try {
    const file = new File([blob], `chunk-${id}.webm`, { type: blob.type });
    const result = await transcribeSpeech({
      file,
      language: language.value || undefined,
      diarize: diarize.value && meta.value?.diarization_available,
    });
    const idx = liveSegments.value.findIndex((s) => s.id === id);
    const newSegs = (result.segments || []).length
      ? result.segments.map((s) => ({
          ...s,
          start: (s.start ?? 0) + chunkTime,
        }))
      : result.text
        ? [{ speaker: "SPEAKER_00", start: chunkTime, text: result.text }]
        : [];
    if (newSegs.length) {
      segments.value.push(...newSegs);
      rebuildTranscript();
    }
    if (idx >= 0) {
      liveSegments.value[idx] = {
        ...liveSegments.value[idx],
        status: "done",
        text: newSegs.map((s) => s.text).join(" ") || "（无识别内容）",
      };
    }
  } catch (e) {
    const idx = liveSegments.value.findIndex((s) => s.id === id);
    if (idx >= 0) {
      liveSegments.value[idx] = {
        ...liveSegments.value[idx],
        status: "error",
        text: e.message || "转写失败",
      };
    }
    message.error(e.message || "片段转写失败");
  }
}

function startSegmentRecorder() {
  if (!recordStream) return false;
  try {
    segmentChunks = [];
    segmentRecorder = new MediaRecorder(recordStream, { mimeType: recordMime });
    segmentRecorder.ondataavailable = (ev) => {
      if (ev.data.size > 0) segmentChunks.push(ev.data);
    };
    segmentRecorder.onstop = () => {
      const blob = new Blob(segmentChunks, { type: recordMime.split(";")[0] });
      segmentChunks = [];
      if (segmentStopReason === "flush" && blob.size > 0) {
        const chunkTime = Math.max(0, recordSeconds.value - 2);
        void transcribeSegmentBlob(blob, chunkTime);
        if (recording.value && streamRecognize.value) startSegmentRecorder();
      }
    };
    segmentRecorder.start(200);
    return true;
  } catch {
    segmentRecorder = null;
    return false;
  }
}

async function flushStreamChunk() {
  if (!segmentRecorder || segmentRecorder.state !== "recording") return;
  segmentStopReason = "flush";
  segmentRecorder.stop();
}

function onUploadChange(e) {
  audioFile.value = e.target?.files?.[0] || null;
  error.value = "";
}

async function startRecording() {
  if (recording.value) return;
  error.value = "";
  if (streamRecognize.value) {
    segments.value = [];
    liveSegments.value = [];
    transcript.value = "";
    summary.value = "";
    summaryBlocks.value = [];
  }
  try {
    recordStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    message.error("无法访问麦克风，请检查浏览器权限");
    return;
  }

  fullChunks = [];
  streamChunkId = 0;
  hasSpeechInChunk = false;
  silenceMs = 0;
  speechMs = 0;
  lastLevelTs = 0;
  recordSeconds.value = 0;
  recordMime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
    ? "audio/webm;codecs=opus"
    : "audio/webm";

  try {
    fullRecorder = new MediaRecorder(recordStream, { mimeType: recordMime });
  } catch (e) {
    message.error(`无法启动录音：${e.message || "浏览器不支持该音频格式"}`);
    recordStream.getTracks().forEach((t) => t.stop());
    recordStream = null;
    return;
  }

  fullRecorder.ondataavailable = (ev) => {
    if (ev.data.size > 0) fullChunks.push(ev.data);
  };
  fullRecorder.onstop = () => {
    const blob = new Blob(fullChunks, { type: recordMime.split(";")[0] });
    audioFile.value = new File([blob], `recording-${Date.now()}.webm`, { type: blob.type });
    clearRecording();
  };

  recording.value = true;
  recordTimer = setInterval(() => {
    recordSeconds.value += 1;
  }, 1000);

  try {
    fullRecorder.start(200);
  } catch (e) {
    recording.value = false;
    if (recordTimer) {
      clearInterval(recordTimer);
      recordTimer = null;
    }
    clearRecording();
    message.error(`录音启动失败：${e.message || "未知错误"}`);
    return;
  }

  if (streamRecognize.value && !startSegmentRecorder()) {
    message.warning("当前浏览器不支持双路录音，已关闭实时识别，录完后请手动转写");
    streamRecognize.value = false;
  }
}

async function stopRecording() {
  if (!recording.value || !fullRecorder) return;
  if (recordTimer) {
    clearInterval(recordTimer);
    recordTimer = null;
  }
  recording.value = false;
  if (streamRecognize.value && segmentRecorder?.state === "recording") {
    if (hasSpeechInChunk) {
      segmentStopReason = "flush";
      segmentRecorder.stop();
      await new Promise((r) => setTimeout(r, 120));
    } else if (segmentRecorder) {
      segmentRecorder.onstop = null;
      try {
        segmentRecorder.stop();
      } catch {
        /* ignore */
      }
      segmentRecorder = null;
    }
  }
  segmentStopReason = "final";
  fullRecorder.stop();
}

function toggleRecording() {
  if (recording.value) stopRecording();
  else startRecording();
}

function resetAll() {
  stopRecording();
  clearRecording();
  audioFile.value = null;
  recordSeconds.value = 0;
  transcript.value = "";
  segments.value = [];
  liveSegments.value = [];
  summary.value = "";
  summaryBlocks.value = [];
  error.value = "";
}

function openSaveModal() {
  if (!canSave.value) return;
  saveTitle.value = "";
  saveModalOpen.value = true;
}

async function confirmSave() {
  if (!canSave.value) return;
  saving.value = true;
  try {
    const segs = segments.value.map((s) => ({
      speaker: s.speaker,
      start: s.start ?? 0,
      end: s.end ?? s.start ?? 0,
      text: s.text || "",
    }));
    await saveMeetingRecord({
      title: saveTitle.value.trim(),
      segments: segs,
      summary: summary.value || null,
      summary_blocks: summaryBlocks.value.length ? summaryBlocks.value : null,
      meta: { style: summaryStyle.value, language: language.value || null },
    });
    saveModalOpen.value = false;
    message.success("会议记录已保存");
  } catch (e) {
    message.error(e.message);
  } finally {
    saving.value = false;
  }
}

async function loadRecords() {
  recordsLoading.value = true;
  try {
    const res = await listMeetingRecords({ page: recordsPage.value, pageSize: 30 });
    records.value = res.items || [];
    recordsTotal.value = res.total || 0;
  } catch (e) {
    message.error(e.message);
  } finally {
    recordsLoading.value = false;
  }
}

async function openRecordsDrawer() {
  recordsDrawerOpen.value = true;
  viewingRecord.value = null;
  recordsPage.value = 1;
  await loadRecords();
}

async function viewRecord(item) {
  recordDetailLoading.value = true;
  try {
    viewingRecord.value = await fetchMeetingRecord(item.id);
  } catch (e) {
    message.error(e.message);
  } finally {
    recordDetailLoading.value = false;
  }
}

function applyRecordToEditor(rec) {
  segments.value = (rec.segments || []).map((s) => ({ ...s }));
  rebuildTranscript();
  summary.value = rec.summary || "";
  summaryBlocks.value = rec.summary_blocks || [];
  recordsDrawerOpen.value = false;
  message.success("已载入会议记录");
}

function confirmDeleteRecord(rec) {
  dialog.warning({
    title: "删除会议记录",
    content: `确定删除「${rec.title || "未命名"}」？此操作不可恢复。`,
    positiveText: "删除",
    negativeText: "取消",
    onPositiveClick: async () => {
      try {
        await deleteMeetingRecord(rec.id);
        message.success("已删除");
        if (viewingRecord.value?.id === rec.id) viewingRecord.value = null;
        await loadRecords();
      } catch (e) {
        message.error(e.message);
      }
    },
  });
}

function formatRecordTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString("zh-CN", { hour12: false });
}

async function runSummarize() {
  if (!transcript.value.trim() && !segments.value.length) return;
  summarizing.value = true;
  try {
    const segs = segments.value.map((s) => ({
      speaker: s.speaker,
      start: s.start ?? 0,
      end: s.end ?? s.start ?? 0,
      text: s.text || "",
    }));
    const res = await summarizeSpeech({
      text: transcript.value,
      style: summaryStyle.value,
      segments: segs,
    });
    summary.value = res.summary || "";
    summaryBlocks.value = res.blocks || [];
    message.success("总结已生成");
  } catch (e) {
    message.error(e.message);
  } finally {
    summarizing.value = false;
  }
}

async function runTranscribe() {
  if (!audioFile.value) {
    message.warning("请先录音或选择音频文件");
    return;
  }
  transcribing.value = true;
  error.value = "";
  if (!streamRecognize.value || sourceMode.value === "upload") {
    transcript.value = "";
    segments.value = [];
    summary.value = "";
    summaryBlocks.value = [];
  }
  try {
    const result = await transcribeSpeech({
      file: audioFile.value,
      language: language.value || undefined,
      diarize: diarize.value && meta.value?.diarization_available,
    });
    segments.value = result.segments || [];
    transcript.value =
      segments.value.length > 0
        ? segmentsToText(segments.value)
        : result.text || "";
    message.success("转写完成");
    if (autoSummarize.value && meta.value?.summarize_available) {
      await runSummarize();
    }
  } catch (e) {
    error.value = e.message;
    message.error(e.message);
  } finally {
    transcribing.value = false;
  }
}

async function copyText(text) {
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    message.success("已复制到剪贴板");
  } catch {
    message.error("复制失败");
  }
}

onMounted(loadMeta);
onBeforeUnmount(() => {
  stopRecording();
  clearRecording();
});
</script>

<template>
  <div class="speech-page feature-page feature-page--fill">
    <FeaturePageToolbar>
      <n-space :size="8">
        <n-button quaternary @click="openRecordsDrawer">
          <template #icon><n-icon :component="FolderOpenOutline" /></template>
          会议记录
        </n-button>
        <n-button type="primary" secondary :disabled="!canSave" :loading="saving" @click="openSaveModal">
          <template #icon><n-icon :component="SaveOutline" /></template>
          保存
        </n-button>
      </n-space>
    </FeaturePageToolbar>

    <n-modal
      v-model:show="saveModalOpen"
      preset="dialog"
      title="保存会议记录"
      positive-text="保存"
      negative-text="取消"
      :loading="saving"
      @positive-click="confirmSave"
    >
      <n-input
        v-model:value="saveTitle"
        placeholder="标题（可选，留空则自动生成）"
        maxlength="256"
        show-count
      />
    </n-modal>

    <n-drawer v-model:show="recordsDrawerOpen" :width="520" placement="right">
      <n-drawer-content title="会议记录" closable>
        <n-spin :show="recordsLoading || recordDetailLoading">
          <template v-if="viewingRecord">
            <n-space vertical :size="12">
              <n-button size="small" quaternary @click="viewingRecord = null">← 返回列表</n-button>
              <n-text strong>{{ viewingRecord.title }}</n-text>
              <n-text depth="3" style="font-size: 12px">
                {{ formatRecordTime(viewingRecord.created_at) }}
              </n-text>
              <n-button size="small" type="primary" @click="applyRecordToEditor(viewingRecord)">
                载入到当前编辑区
              </n-button>
              <n-text strong style="font-size: 13px">转写</n-text>
              <div class="record-segments">
                <div v-for="(seg, i) in viewingRecord.segments" :key="i" class="segment-row">
                  <n-tag
                    size="small"
                    :bordered="false"
                    :style="{ background: speakerColor(seg.speaker) + '22', color: speakerColor(seg.speaker) }"
                  >
                    {{ seg.speaker }}
                  </n-tag>
                  <n-text depth="3" class="seg-time">{{ formatTime(seg.start) }}</n-text>
                  <n-text class="seg-text">{{ seg.text }}</n-text>
                </div>
              </div>
              <template v-if="viewingRecord.summary_blocks?.length">
                <n-text strong style="font-size: 13px">时间线总结</n-text>
                <div
                  v-for="(blk, i) in viewingRecord.summary_blocks"
                  :key="i"
                  class="summary-block"
                >
                  <n-tag
                    size="small"
                    :bordered="false"
                    :style="{ background: speakerColor(blk.speaker) + '22', color: speakerColor(blk.speaker) }"
                  >
                    {{ blk.speaker }}
                  </n-tag>
                  <n-text depth="3" class="blk-time">{{ blk.time_range }}</n-text>
                  <n-text class="blk-summary">{{ blk.summary }}</n-text>
                </div>
              </template>
              <template v-else-if="viewingRecord.summary">
                <n-text strong style="font-size: 13px">总结</n-text>
                <n-input
                  type="textarea"
                  :value="viewingRecord.summary"
                  readonly
                  :autosize="{ minRows: 4, maxRows: 12 }"
                />
              </template>
            </n-space>
          </template>
          <template v-else>
            <n-space v-if="records.length" vertical :size="8">
              <div v-for="item in records" :key="item.id" class="record-list-item">
                <div class="record-list-main" @click="viewRecord(item)">
                  <n-text strong>{{ item.title || "未命名会议" }}</n-text>
                  <n-text depth="3" style="font-size: 12px">
                    {{ formatRecordTime(item.created_at) }} · {{ item.segment_count }} 段
                    <n-tag v-if="item.has_summary" size="tiny" :bordered="false" style="margin-left: 6px">
                      已总结
                    </n-tag>
                  </n-text>
                </div>
                <n-button size="tiny" quaternary type="error" @click.stop="confirmDeleteRecord(item)">
                  <template #icon><n-icon :component="TrashOutline" /></template>
                </n-button>
              </div>
            </n-space>
            <n-text v-else depth="3">暂无保存的会议记录</n-text>
          </template>
        </n-spin>
      </n-drawer-content>
    </n-drawer>

    <n-spin :show="loadingMeta" class="speech-spin">
      <div class="speech-alerts">
        <n-alert
          v-if="!loadingMeta && !configured"
          type="warning"
          title="语音服务未就绪"
          class="page-alert"
        >
          语音服务尚未配置完成，请联系管理员部署并启用相关能力。
        </n-alert>

        <n-alert
          v-if="error"
          type="error"
          :title="error"
          class="page-alert"
          closable
          @close="error = ''"
        />
      </div>

      <div class="speech-layout">
          <n-card title="音频来源" class="panel panel-source">
            <div class="panel-body">
            <n-space vertical :size="16" class="source-space">
              <n-space :size="8">
                <n-button
                  :type="sourceMode === 'record' ? 'primary' : 'default'"
                  :secondary="sourceMode !== 'record'"
                  @click="sourceMode = 'record'"
                >
                  浏览器录音
                </n-button>
                <n-button
                  :type="sourceMode === 'upload' ? 'primary' : 'default'"
                  :secondary="sourceMode !== 'upload'"
                  @click="sourceMode = 'upload'"
                >
                  上传文件
                </n-button>
              </n-space>

              <div v-if="sourceMode === 'record'" class="record-block source-main">
                <audio-waveform
                  :stream="recordStream"
                  :active="recording"
                  :height="100"
                  @level="onWaveLevel"
                />
                <n-space align="center" :size="12" wrap>
                  <n-button
                    :type="recording ? 'error' : 'primary'"
                    size="large"
                    :disabled="!configured"
                    @click="toggleRecording"
                  >
                    <template #icon>
                      <n-icon :component="recording ? StopCircleOutline : MicOutline" />
                    </template>
                    {{ recording ? "停止录音" : "开始录音" }}
                  </n-button>
                  <n-tag v-if="recording && streamRecognize" type="warning" size="small" :bordered="false">
                    <template #icon>
                      <n-icon :component="RadioOutline" />
                    </template>
                    实时转写中
                  </n-tag>
                  <n-tag v-if="pendingStreamCount" size="small" :bordered="false">
                    {{ pendingStreamCount }} 段识别中
                  </n-tag>
                </n-space>
                <n-text depth="3" class="record-hint">{{ recordHint }}</n-text>
                <n-checkbox v-model:checked="streamRecognize" :disabled="recording">
                  实时识别：检测到停顿（约 1.4 秒）后自动转写当前片段
                </n-checkbox>
                <div v-if="liveSegments.length" class="live-segments">
                  <div
                    v-for="item in liveSegments"
                    :key="item.id"
                    class="live-seg-row"
                    :class="item.status"
                  >
                    <n-tag size="tiny" :type="item.status === 'done' ? 'success' : item.status === 'error' ? 'error' : 'info'">
                      {{ item.timeLabel }}
                    </n-tag>
                    <n-spin v-if="item.status === 'transcribing'" size="small" />
                    <n-text class="live-seg-text">{{ item.text || "识别中…" }}</n-text>
                  </div>
                </div>
              </div>

              <div v-else class="upload-fill source-main">
                <file-drop-zone
                  accept="audio/*,.webm,.wav,.mp3,.m4a,.ogg,.flac"
                  title="拖拽或选择音频"
                  :hint="`最大 ${meta?.max_file_mb || 100} MB`"
                  :file-name="audioFile?.name || ''"
                  icon="upload"
                  :disabled="!configured"
                  @change="onUploadChange"
                />
              </div>

              <div v-if="audioFile" class="audio-actions">
                <n-text depth="3">已就绪：{{ audioFile.name }}</n-text>
                <n-button size="small" quaternary @click="resetAll">清除</n-button>
              </div>

              <div>
                <n-text class="field-label">识别语言</n-text>
                <n-select v-model:value="language" :options="languageOptions" />
              </div>

              <n-checkbox
                v-model:checked="diarize"
                :disabled="!meta?.diarization_available"
              >
                区分不同说话人
              </n-checkbox>

              <n-checkbox
                v-if="meta?.summarize_available"
                v-model:checked="autoSummarize"
              >
                转写完成后自动生成智能总结
              </n-checkbox>

              <n-button
                type="primary"
                block
                :loading="transcribing"
                :disabled="!canTranscribe"
                @click="runTranscribe"
              >
                <template #icon>
                  <n-icon :component="CloudUploadOutline" />
                </template>
                {{
                  streamRecognize && segments.length
                    ? "整段重新转写"
                    : "开始转写"
                }}
              </n-button>
            </n-space>
            </div>
          </n-card>

          <div class="speech-output-column">
          <n-card title="转写结果" class="panel panel-transcript">
            <template #header-extra>
              <n-button size="small" quaternary :disabled="!transcript" @click="copyText(transcript)">
                <template #icon><n-icon :component="CopyOutline" /></template>
                复制
              </n-button>
            </template>

            <div class="panel-body">
              <div v-if="segments.length" class="segment-list">
                <div v-for="(seg, i) in segments" :key="i" class="segment-row">
                  <n-tag
                    size="small"
                    :bordered="false"
                    :style="{ background: speakerColor(seg.speaker) + '22', color: speakerColor(seg.speaker) }"
                  >
                    {{ seg.speaker }}
                  </n-tag>
                  <n-text depth="3" class="seg-time">{{ formatTime(seg.start) }}</n-text>
                  <n-text class="seg-text">{{ seg.text }}</n-text>
                </div>
              </div>

              <div class="textarea-fill">
                <n-input
                  v-model:value="transcript"
                  type="textarea"
                  placeholder="转写文字（含说话人时间轴）"
                />
              </div>
            </div>
          </n-card>

          <n-card title="智能总结" class="panel panel-summary">
            <template #header-extra>
              <n-space :size="8">
                <n-select
                  v-model:value="summaryStyle"
                  :options="summaryStyleOptions"
                  size="small"
                  style="width: 120px"
                />
                <n-button
                  size="small"
                  type="primary"
                  :loading="summarizing"
                  :disabled="!canSummarize"
                  @click="runSummarize"
                >
                  <template #icon><n-icon :component="SparklesOutline" /></template>
                  生成总结
                </n-button>
                <n-button
                  size="small"
                  quaternary
                  :disabled="!summary"
                  @click="copyText(summary)"
                >
                  复制
                </n-button>
              </n-space>
            </template>
            <div class="panel-body">
              <div v-if="summaryBlocks.length" class="summary-blocks">
                <div v-for="(blk, i) in summaryBlocks" :key="i" class="summary-block">
                  <n-tag
                    size="small"
                    :bordered="false"
                    :style="{ background: speakerColor(blk.speaker) + '22', color: speakerColor(blk.speaker) }"
                  >
                    {{ blk.speaker }}
                  </n-tag>
                  <n-text depth="3" class="blk-time">{{ blk.time_range }}</n-text>
                  <n-text class="blk-summary">{{ blk.summary }}</n-text>
                </div>
              </div>
              <div class="textarea-fill">
                <n-input
                  v-model:value="summary"
                  type="textarea"
                  :placeholder="
                    meta?.summarize_available
                      ? '按说话人时间线的总结将显示在这里（含上方分段视图）'
                      : '总结功能未启用，请联系管理员'
                  "
                  :disabled="!meta?.summarize_available"
                />
              </div>
            </div>
          </n-card>
          </div>
      </div>
    </n-spin>
  </div>
</template>

<style scoped>
.speech-page {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  min-height: 0;
  max-width: none;
  margin: 0;
}
.speech-spin {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.speech-spin :deep(.n-spin-container) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.speech-alerts {
  flex-shrink: 0;
}
.speech-layout {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(300px, 1fr) minmax(340px, 1.15fr);
  gap: 16px;
  align-items: stretch;
}
.speech-output-column {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 0;
}
.panel {
  border-radius: 10px;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.panel :deep(.n-card) {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.panel :deep(.n-card__content) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.panel-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.panel-source .source-space {
  width: 100%;
  height: 100%;
}
.source-main {
  flex: 1;
  min-height: 200px;
}
.upload-fill {
  display: flex;
}
.upload-fill :deep(.drop-zone) {
  flex: 1;
  width: 100%;
  min-height: 180px;
}
.panel-transcript,
.panel-summary {
  flex: 1;
  min-height: 0;
}
.textarea-fill {
  flex: 1;
  min-height: 160px;
  display: flex;
}
.textarea-fill :deep(.n-input) {
  height: 100%;
}
.textarea-fill :deep(textarea) {
  height: 100% !important;
  min-height: 160px;
  resize: none;
}
.page-alert {
  margin-bottom: 12px;
}
.record-block {
  flex: 1;
  min-height: 200px;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 12px;
  padding: 16px;
  border-radius: 8px;
  border: 1px dashed rgba(0, 0, 0, 0.12);
  background: rgba(0, 0, 0, 0.02);
}
.record-hint {
  font-size: 13px;
}
.live-segments {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1;
  min-height: 80px;
  max-height: none;
  overflow-y: auto;
  padding: 8px;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.03);
}
.live-seg-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 13px;
}
.live-seg-row.error .live-seg-text {
  color: #d03050;
}
.live-seg-text {
  flex: 1;
  line-height: 1.45;
}
.audio-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.field-label {
  display: block;
  font-size: 12px;
  margin-bottom: 6px;
}
.segment-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  flex: 0 1 auto;
  max-height: 38%;
  min-height: 72px;
  overflow-y: auto;
}
.segment-row {
  display: grid;
  grid-template-columns: auto auto 1fr;
  gap: 8px;
  align-items: start;
  font-size: 13px;
}
.seg-time {
  font-size: 12px;
  white-space: nowrap;
}
.seg-text {
  line-height: 1.5;
}
.summary-blocks,
.record-segments {
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex: 0 1 auto;
  max-height: 42%;
  overflow-y: auto;
}
.summary-block {
  display: grid;
  grid-template-columns: auto auto 1fr;
  gap: 8px;
  align-items: start;
  font-size: 13px;
  padding: 10px;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.03);
}
.blk-time {
  font-size: 12px;
  white-space: nowrap;
}
.blk-summary {
  line-height: 1.5;
}
.record-list-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  cursor: default;
}
.record-list-main {
  flex: 1;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.record-list-main:hover {
  opacity: 0.85;
}
@media (max-width: 900px) {
  .speech-spin {
    overflow-y: auto;
  }
  .speech-layout {
    grid-template-columns: 1fr;
    flex: none;
    min-height: min(85vh, 900px);
  }
  .speech-output-column {
    min-height: 480px;
  }
  .panel-transcript,
  .panel-summary {
    min-height: 280px;
  }
}
</style>
