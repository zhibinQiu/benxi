<script setup>
import { usePlatformUi } from "../composables/usePlatformUi";
import { useAuth } from "../composables/useAuth";
import { useI18n } from "../composables/useI18n.js";
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import {
  NAlert,
  NButton,
  NCard,
  NCheckbox,
  NDrawer,
  NIcon,
  NInput,
  NModal,
  NPagination,
  NSelect,
  NSpace,
  NSpin,
  NTag,
  NText } from "naive-ui";
import {
  MicOutline,
  StopCircleOutline,
  CopyOutline,
  CloudUploadOutline,
  SparklesOutline,
  RadioOutline,
  SaveOutline,
  FolderOpenOutline,
  TrashOutline,
  GitNetworkOutline,
  LibraryOutline,
  LinkOutline,
} from "@vicons/ionicons5";
import FileDropZone from "../components/FileDropZone.vue";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import ListRefreshButton from "../components/ListRefreshButton.vue";
import { LIST_PAGE_SIZE } from "../constants/listPage.js";
import AudioWaveform from "../components/AudioWaveform.vue";
import {
  deleteMeetingRecord,
  fetchMeetingRecord,
  fetchSpeechMeta,
  importMeetingSummaryToLibrary,
  listMeetingRecords,
  saveMeetingRecord,
  summarizeSpeech,
  transcribeSpeech,
  transcribeSpeechFromUrl } from "../api/client";
import { extractKgFromText } from "../api/kg.js";
import { FEATURE_UNAVAILABLE } from "../utils/uiMessage";

const router = useRouter();
const ui = usePlatformUi();
const { hasPerm } = useAuth();
const { t, locale } = useI18n();

const meta = ref(null);
const loadingMeta = ref(true);
const sourceMode = ref("record");
const audioFile = ref(null);
const videoUrl = ref("");
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
const importingKg = ref(false);
const importingLibrary = ref(false);
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
let streamChunkTimer = null;
let streamChunkStartSec = 0;
let pendingChunkTime = 0;

const STREAM_CHUNK_MS = 2500;

const languageOptions = computed(() => [
  { label: t("speechToText.langAuto"), value: "" },
  { label: t("speechToText.langZh"), value: "zh" },
  { label: t("speechToText.langEn"), value: "en" },
  { label: t("speechToText.langJa"), value: "ja" },
  { label: t("speechToText.langKo"), value: "ko" },
]);

const summaryStyleOptions = computed(() => [
  { label: t("speechToText.summaryStyleMinutes"), value: "minutes" },
  { label: t("speechToText.summaryStyleBrief"), value: "brief" },
  { label: t("speechToText.summaryStyleDetailed"), value: "detailed" },
]);

const configured = computed(() => meta.value?.configured ?? false);

const pendingStreamCount = computed(
  () => liveSegments.value.filter((s) => s.status === "transcribing").length
);

const canTranscribe = computed(
  () =>
    configured.value &&
    !transcribing.value &&
    (sourceMode.value === "videoUrl"
      ? !!videoUrl.value.trim()
      : !!audioFile.value && !(recording.value && streamRecognize.value))
);

const canSummarize = computed(
  () =>
    configured.value &&
    meta.value?.summarize_available &&
    !summarizing.value &&
    (!!transcript.value.trim() || segments.value.length > 0)
);

function buildSummaryExportText({ summaryText = summary.value, blocks = summaryBlocks.value } = {}) {
  if (blocks?.length) {
    return blocks
      .map((blk) => `${blk.speaker} [${blk.time_range}]: ${blk.summary || ""}`)
      .join("\n")
      .trim();
  }
  return (summaryText || "").trim();
}

function resolveImportKgTitle({ recordTitle = "" } = {}) {
  const title = (recordTitle || saveTitle.value || "").trim();
  if (title) return title;
  const dateLocale = locale.value === "zh" ? "zh-CN" : "en-US";
  return t("speechToText.meetingSummaryDefault", {
    date: new Date().toLocaleString(dateLocale),
  });
}

const canImportKg = computed(
  () => hasPerm("feature.kg") && !!buildSummaryExportText().length
);

const canImportLibrary = computed(() => !!buildSummaryExportText().length);

const canSave = computed(
  () => !saving.value && (segments.value.length > 0 || !!transcript.value.trim() || !!summary.value.trim())
);

const recordHint = computed(() => {
  if (recording.value) {
    const streamHint = streamRecognize.value ? t("speechToText.streamHintSuffix") : "";
    return t("speechToText.recordHintRecording", {
      duration: formatDuration(recordSeconds.value),
      streamHint,
    });
  }
  if (audioFile.value && sourceMode.value === "record") {
    return t("speechToText.recordHintReady", {
      name: audioFile.value.name,
      duration: formatDuration(recordSeconds.value),
    });
  }
  return t("speechToText.recordHintIdle");
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
  // 仅使用平台既有色：accent / accent-secondary / caution / danger / accent-hover
  const colors = ["#0a6bff", "#3b82ff", "#e25507", "#BE1743", "#0058e0"];
  return colors[(n - 1) % colors.length];
}

const sourceModeOptions = computed(() => [
  { key: "record", label: t("speechToText.browserRecord"), icon: MicOutline },
  { key: "upload", label: t("speechToText.uploadFile"), icon: CloudUploadOutline },
  { key: "videoUrl", label: t("speechToText.videoUrl"), icon: LinkOutline },
]);

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
  clearStreamChunkTimer();
  streamChunkStartSec = 0;
  pendingChunkTime = 0;
  recording.value = false;
}

function clearStreamChunkTimer() {
  if (streamChunkTimer) {
    clearInterval(streamChunkTimer);
    streamChunkTimer = null;
  }
}

function startStreamChunkTimer() {
  clearStreamChunkTimer();
  streamChunkStartSec = 0;
  streamChunkTimer = setInterval(() => {
    if (recording.value && streamRecognize.value) {
      void flushStreamChunk();
    }
  }, STREAM_CHUNK_MS);
}

async function transcribeSegmentBlob(blob, chunkTime) {
  const id = ++streamChunkId;
  liveSegments.value.push({
    id,
    status: "transcribing",
    text: "",
    timeLabel: formatDuration(chunkTime)});
  try {
    const file = new File([blob], `chunk-${id}.webm`, { type: blob.type });
    const result = await transcribeSpeech({
      file,
      language: language.value || undefined,
      diarize: diarize.value && meta.value?.diarization_available});
    const idx = liveSegments.value.findIndex((s) => s.id === id);
    const newSegs = (result.segments || []).length
      ? result.segments.map((s) => ({
          ...s,
          start: (s.start ?? 0) + chunkTime}))
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
        text: newSegs.map((s) => s.text).join(" ") || t("speechToText.noTranscriptContent")};
    }
  } catch (e) {
    const idx = liveSegments.value.findIndex((s) => s.id === id);
    if (idx >= 0) {
      liveSegments.value[idx] = {
        ...liveSegments.value[idx],
        status: "error",
        text: e.message || t("speechToText.transcribeFailed")};
    }
    ui.error(e.message || t("speechToText.segmentTranscribeFailed"));
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
      const chunkTime = pendingChunkTime;
      segmentChunks = [];
      if (segmentStopReason === "flush" && blob.size > 0) {
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
  pendingChunkTime = streamChunkStartSec;
  streamChunkStartSec = recordSeconds.value;
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
    ui.error(t("speechToText.micAccessDenied"));
    return;
  }

  fullChunks = [];
  streamChunkId = 0;
  streamChunkStartSec = 0;
  pendingChunkTime = 0;
  recordSeconds.value = 0;
  recordMime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
    ? "audio/webm;codecs=opus"
    : "audio/webm";

  try {
    fullRecorder = new MediaRecorder(recordStream, { mimeType: recordMime });
  } catch (e) {
    ui.error(
      t("speechToText.cannotStartRecording", {
        message: e.message || t("speechToText.browserUnsupportedFormat"),
      })
    );
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
    ui.error(
      t("speechToText.recordingStartFailed", {
        message: e.message || t("speechToText.unknownError"),
      })
    );
    return;
  }

  if (streamRecognize.value && !startSegmentRecorder()) {
    ui.warning(t("speechToText.dualRecorderUnsupported"));
    streamRecognize.value = false;
  } else if (streamRecognize.value) {
    startStreamChunkTimer();
  }
}

async function stopRecording() {
  if (!recording.value || !fullRecorder) return;
  if (recordTimer) {
    clearInterval(recordTimer);
    recordTimer = null;
  }
  recording.value = false;
  clearStreamChunkTimer();
  if (streamRecognize.value && segmentRecorder?.state === "recording") {
    pendingChunkTime = streamChunkStartSec;
    segmentStopReason = "flush";
    segmentRecorder.stop();
    await new Promise((r) => setTimeout(r, 120));
  } else if (streamRecognize.value && segmentRecorder) {
    segmentRecorder.onstop = null;
    try {
      segmentRecorder.stop();
    } catch {
      /* ignore */
    }
    segmentRecorder = null;
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
  videoUrl.value = "";
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
      text: s.text || ""}));
    await saveMeetingRecord({
      title: saveTitle.value.trim(),
      segments: segs,
      summary: summary.value || null,
      summary_blocks: summaryBlocks.value.length ? summaryBlocks.value : null,
      meta: { style: summaryStyle.value, language: language.value || null }});
    saveModalOpen.value = false;
    ui.success(t("speechToText.recordSaved"));
  } catch (e) {
    ui.error(e.message);
  } finally {
    saving.value = false;
  }
}

async function onRecordsPageChange(p) {
  recordsPage.value = p;
  await loadRecords();
}

async function loadRecords() {
  recordsLoading.value = true;
  try {
    const res = await listMeetingRecords({ page: recordsPage.value, pageSize: LIST_PAGE_SIZE });
    records.value = res.items || [];
    recordsTotal.value = res.total || 0;
  } catch (e) {
    ui.error(e.message);
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
    ui.error(e.message);
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
  ui.success(t("speechToText.recordLoaded"));
}

function confirmDeleteRecord(rec) {
  ui.confirmDelete({
    title: t("speechToText.deleteRecordTitle"),
    content: t("speechToText.deleteRecordContent", {
      title: rec.title || t("speechToText.unnamed"),
    }),
    onPositive: async () => {
      await deleteMeetingRecord(rec.id);
      ui.success(t("speechToText.deleted"));
      if (viewingRecord.value?.id === rec.id) viewingRecord.value = null;
      await loadRecords();
    }});
}

function formatRecordTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const dateLocale = locale.value === "zh" ? "zh-CN" : "en-US";
  return d.toLocaleString(dateLocale, { hour12: false });
}

async function runSummarize() {
  if (!transcript.value.trim() && !segments.value.length) return;
  summarizing.value = true;
  try {
    const segs = segments.value.map((s) => ({
      speaker: s.speaker,
      start: s.start ?? 0,
      end: s.end ?? s.start ?? 0,
      text: s.text || ""}));
    const res = await summarizeSpeech({
      text: transcript.value,
      style: summaryStyle.value,
      segments: segs});
    summary.value = res.summary || "";
    summaryBlocks.value = res.blocks || [];
    ui.success(t("speechToText.summaryGenerated"));
  } catch (e) {
    ui.error(e.message);
  } finally {
    summarizing.value = false;
  }
}

async function runTranscribe() {
  if (sourceMode.value === "videoUrl") {
    if (!videoUrl.value.trim()) {
      ui.warning(t("speechToText.enterVideoUrlFirst"));
      return;
    }
    transcribing.value = true;
    error.value = "";
    transcript.value = "";
    segments.value = [];
    summary.value = "";
    summaryBlocks.value = [];
    try {
      const result = await transcribeSpeechFromUrl({
        url: videoUrl.value.trim(),
        language: language.value || undefined,
        diarize: diarize.value && meta.value?.diarization_available,
      });
      segments.value = result.segments || [];
      transcript.value =
        segments.value.length > 0
          ? segmentsToText(segments.value)
          : result.text || "";
      ui.success(t("speechToText.transcribeComplete"));
      if (autoSummarize.value && meta.value?.summarize_available) {
        await runSummarize();
      }
    } catch (e) {
      error.value = e.message;
      ui.error(e.message);
    } finally {
      transcribing.value = false;
    }
    return;
  }

  if (!audioFile.value) {
    ui.warning(t("speechToText.selectAudioFirst"));
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
      diarize: diarize.value && meta.value?.diarization_available});
    segments.value = result.segments || [];
    transcript.value =
      segments.value.length > 0
        ? segmentsToText(segments.value)
        : result.text || "";
    ui.success(t("speechToText.transcribeComplete"));
    if (autoSummarize.value && meta.value?.summarize_available) {
      await runSummarize();
    }
  } catch (e) {
    error.value = e.message;
    ui.error(e.message);
  } finally {
    transcribing.value = false;
  }
}

async function copyText(text) {
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    ui.success(t("speechToText.copied"));
  } catch {
    ui.error(t("speechToText.copyFailed"));
  }
}

async function runImportKg({ record } = {}) {
  const text = record
    ? buildSummaryExportText({
        summaryText: record.summary,
        blocks: record.summary_blocks,
      })
    : buildSummaryExportText();
  if (!text) {
    ui.warning(t("speechToText.generateSummaryFirst"));
    return;
  }
  importingKg.value = true;
  try {
    const res = await extractKgFromText({
      title: resolveImportKgTitle({ recordTitle: record?.title }),
      text,
      sourceType: "meeting_summary",
      sourceId: record?.id || null,
    });
    const created = res.entities_created || 0;
    const relations = res.relations_created || 0;
    ui.success(
      t("speechToText.kgImportSuccess", { entities: created, relations })
    );
    if (res.root_entity_id) {
      router.push({
        path: "/system/kg",
        query: { focusEntityId: res.root_entity_id },
      });
    }
  } catch (e) {
    ui.error(e.message);
  } finally {
    importingKg.value = false;
  }
}

async function runImportLibrary({ record } = {}) {
  const exportText = record
    ? buildSummaryExportText({
        summaryText: record.summary,
        blocks: record.summary_blocks,
      })
    : buildSummaryExportText();
  if (!exportText) {
    ui.warning(t("speechToText.generateSummaryFirst"));
    return;
  }
  importingLibrary.value = true;
  try {
    const res = await importMeetingSummaryToLibrary({
      title: resolveImportKgTitle({ recordTitle: record?.title }),
      summary: record ? record.summary || exportText : summary.value || exportText,
      summaryBlocks: record ? record.summary_blocks || [] : summaryBlocks.value,
    });
    ui.success(res.message || t("speechToText.libraryImportSuccess"));
    if (res.document_id) {
      router.push({ name: "document-detail", params: { id: res.document_id } });
    }
  } catch (e) {
    ui.error(e.message);
  } finally {
    importingLibrary.value = false;
  }
}

onMounted(loadMeta);
onBeforeUnmount(() => {
  stopRecording();
  clearRecording();
});
</script>

<template>
  <FeatureSubsystemShell fill>
    <template #extra>
      <n-space :size="10">
        <n-button quaternary @click="openRecordsDrawer">
          <template #icon><n-icon :component="FolderOpenOutline" /></template>
          {{ t('speechToText.meetingRecords') }}
        </n-button>
        <n-button quaternary :disabled="!canSave" :loading="saving" @click="openSaveModal">
          <template #icon><n-icon :component="SaveOutline" /></template>
          {{ t('speechToText.save') }}
        </n-button>
      </n-space>
    </template>

    <n-modal
      v-model:show="saveModalOpen"
      preset="dialog"
      :title="t('speechToText.saveRecordTitle')"
      :positive-text="t('speechToText.save')"
      :negative-text="t('speechToText.cancel')"
      :loading="saving"
      @positive-click="confirmSave"
    >
      <n-input
        v-model:value="saveTitle"
        :placeholder="t('speechToText.titlePlaceholder')"
        maxlength="256"
        show-count
      />
    </n-modal>

    <n-drawer v-model:show="recordsDrawerOpen" :width="624" placement="right">
      <n-drawer-content :title="t('speechToText.drawerTitle')" closable>
        <template #header-extra>
          <ListRefreshButton
            v-if="!viewingRecord"
            :loading="recordsLoading"
            size="small"
            @click="loadRecords"
          />
        </template>
        <n-spin :show="recordsLoading || recordDetailLoading" local>
          <template v-if="viewingRecord">
            <n-space vertical :size="14">
              <n-button size="small" quaternary @click="viewingRecord = null">{{ t('speechToText.backToList') }}</n-button>
              <n-text strong>{{ viewingRecord.title }}</n-text>
              <n-text depth="3" style="font-size: 14px">
                {{ formatRecordTime(viewingRecord.created_at) }}
              </n-text>
              <n-button size="small" secondary @click="applyRecordToEditor(viewingRecord)">
                {{ t('speechToText.loadToEditor') }}
              </n-button>
              <n-button
                v-if="hasPerm('feature.kg')"
                size="small"
                quaternary
                :loading="importingKg"
                :disabled="!buildSummaryExportText({
                  summaryText: viewingRecord.summary,
                  blocks: viewingRecord.summary_blocks,
                })"
                @click="runImportKg({ record: viewingRecord })"
              >
                <template #icon><n-icon :component="GitNetworkOutline" /></template>
                {{ t('speechToText.importKg') }}
              </n-button>
              <n-button
                size="small"
                quaternary
                :loading="importingLibrary"
                :disabled="!buildSummaryExportText({
                  summaryText: viewingRecord.summary,
                  blocks: viewingRecord.summary_blocks,
                })"
                @click="runImportLibrary({ record: viewingRecord })"
              >
                <template #icon><n-icon :component="LibraryOutline" /></template>
                {{ t('speechToText.importLibrary') }}
              </n-button>
              <n-text strong style="font-size: 16px">{{ t('speechToText.transcript') }}</n-text>
              <div class="record-segments">
                <div v-for="(seg, i) in viewingRecord.segments" :key="i" class="segment-row">
                  <div class="segment-meta">
                    <n-tag
                      size="small"
                      :bordered="false"
                      round
                      :style="{ background: speakerColor(seg.speaker) + '18', color: speakerColor(seg.speaker) }"
                    >
                      {{ seg.speaker }}
                    </n-tag>
                    <n-text depth="3" class="seg-time">{{ formatTime(seg.start) }}</n-text>
                  </div>
                  <n-text class="seg-text">{{ seg.text }}</n-text>
                </div>
              </div>
              <template v-if="viewingRecord.summary_blocks?.length">
                <n-text strong style="font-size: 16px">{{ t('speechToText.timelineSummary') }}</n-text>
                <div
                  v-for="(blk, i) in viewingRecord.summary_blocks"
                  :key="i"
                  class="summary-block"
                >
                  <div class="segment-meta">
                    <n-tag
                      size="small"
                      :bordered="false"
                      round
                      :style="{ background: speakerColor(blk.speaker) + '18', color: speakerColor(blk.speaker) }"
                    >
                      {{ blk.speaker }}
                    </n-tag>
                    <n-text depth="3" class="blk-time">{{ blk.time_range }}</n-text>
                  </div>
                  <n-text class="blk-summary">{{ blk.summary }}</n-text>
                </div>
              </template>
              <template v-else-if="viewingRecord.summary">
                <n-text strong style="font-size: 16px">{{ t('speechToText.summary') }}</n-text>
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
            <n-space v-if="records.length" vertical :size="10">
              <div v-for="item in records" :key="item.id" class="record-list-item">
                <div class="record-list-main" @click="viewRecord(item)">
                  <n-text strong>{{ item.title || t('speechToText.unnamedMeeting') }}</n-text>
                  <n-text depth="3" style="font-size: 14px">
                    {{ t('speechToText.recordMeta', { time: formatRecordTime(item.created_at), count: item.segment_count }) }}
                    <n-tag v-if="item.has_summary" size="tiny" :bordered="false" style="margin-left: 7px">
                      {{ t('speechToText.summarized') }}
                    </n-tag>
                  </n-text>
                </div>
                <n-button size="small" quaternary type="error" @click.stop="confirmDeleteRecord(item)">
                  <template #icon><n-icon :component="TrashOutline" /></template>
                </n-button>
              </div>
            </n-space>
            <n-pagination
              v-if="recordsTotal > LIST_PAGE_SIZE"
              :page="recordsPage"
              :page-size="LIST_PAGE_SIZE"
              :item-count="recordsTotal"
              size="small"
              style="margin-top: 10px"
              @update:page="onRecordsPageChange"
            />
            <n-text v-if="!records.length" depth="3">{{ t('speechToText.noSavedRecords') }}</n-text>
          </template>
        </n-spin>
      </n-drawer-content>
    </n-drawer>

    <n-spin :show="loadingMeta" class="speech-spin" local>
      <div class="speech-alerts">
        <n-alert
          v-if="!loadingMeta && !configured"
          type="warning"
          :title="t('speechToText.unavailableTitle')"
          class="page-alert"
        >
          <p>{{ FEATURE_UNAVAILABLE }}</p>
          <template #action>
            <n-button size="small" :loading="loadingMeta" @click="loadMeta">{{ t('speechToText.recheck') }}</n-button>
          </template>
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
        <n-card :title="t('speechToText.audioSource')" size="small" class="panel panel-source">
          <div class="panel-body">
            <div class="source-mode-switch" role="tablist">
              <button
                v-for="opt in sourceModeOptions"
                :key="opt.key"
                type="button"
                role="tab"
                class="source-mode-btn"
                :class="{ 'source-mode-btn--active': sourceMode === opt.key }"
                :aria-selected="sourceMode === opt.key"
                @click="sourceMode = opt.key"
              >
                <n-icon :component="opt.icon" :size="15" />
                <span>{{ opt.label }}</span>
              </button>
            </div>

            <div v-if="sourceMode === 'record'" class="record-block source-main" :class="{ 'record-block--live': recording }">
              <div class="record-stage">
                <div class="record-timer" :class="{ 'record-timer--live': recording }">
                  <span v-if="recording" class="record-pulse" aria-hidden="true" />
                  <span class="record-timer-text">{{ formatDuration(recordSeconds) }}</span>
                </div>
                <audio-waveform
                  :stream="recordStream"
                  :active="recording"
                  :height="100"
                  :placeholder="t('speechToText.wavePlaceholder')"
                />
              </div>

              <div class="record-controls">
                <n-button
                  :type="recording ? 'error' : 'default'"
                  :secondary="recording"
                  size="medium"
                  :disabled="!configured"
                  @click="toggleRecording"
                >
                  <template #icon>
                    <n-icon :component="recording ? StopCircleOutline : MicOutline" />
                  </template>
                  {{ recording ? t('speechToText.stopRecording') : t('speechToText.startRecording') }}
                </n-button>
                <div class="record-status-tags">
                  <n-tag v-if="recording && streamRecognize" type="info" size="small" :bordered="false" round>
                    <template #icon>
                      <n-icon :component="RadioOutline" />
                    </template>
                    {{ t('speechToText.liveTranscribing') }}
                  </n-tag>
                  <n-tag v-if="pendingStreamCount" size="small" :bordered="false" round>
                    {{ t('speechToText.segmentsRecognizing', { count: pendingStreamCount }) }}
                  </n-tag>
                </div>
              </div>

              <n-text depth="3" class="record-hint">{{ recordHint }}</n-text>
              <n-checkbox v-model:checked="streamRecognize" :disabled="recording" class="stream-check">
                {{ t('speechToText.streamRecognizeLabel') }}
              </n-checkbox>

              <div v-if="liveSegments.length" class="live-segments">
                <div
                  v-for="item in liveSegments"
                  :key="item.id"
                  class="live-seg-row"
                  :class="item.status"
                >
                  <n-tag size="tiny" :type="item.status === 'done' ? 'success' : item.status === 'error' ? 'error' : 'info'" round>
                    {{ item.timeLabel }}
                  </n-tag>
                  <n-spin v-if="item.status === 'transcribing'" :size="14" />
                  <n-text class="live-seg-text">{{ item.text || t('speechToText.recognizing') }}</n-text>
                </div>
              </div>
            </div>

            <div v-else-if="sourceMode === 'upload'" class="upload-fill source-main">
              <file-drop-zone
                accept="audio/*,.webm,.wav,.mp3,.m4a,.ogg,.flac"
                :title="t('speechToText.uploadDropTitle')"
                :hint="t('speechToText.uploadMaxSize', { mb: meta?.max_file_mb || 100 })"
                :file-name="audioFile?.name || ''"
                icon="upload"
                :disabled="!configured"
                @change="onUploadChange"
              />
            </div>

            <div v-else class="video-url-block source-main">
              <div class="video-url-icon">
                <n-icon :component="LinkOutline" :size="22" />
              </div>
              <n-input
                v-model:value="videoUrl"
                type="textarea"
                :placeholder="t('speechToText.videoUrlPlaceholder')"
                :autosize="{ minRows: 3, maxRows: 5 }"
                :disabled="!configured"
              />
              <n-text depth="3" class="video-url-hint">
                {{ t('speechToText.videoUrlHint', { mb: meta?.max_file_mb || 100 }) }}
              </n-text>
            </div>

            <div v-if="audioFile && sourceMode !== 'videoUrl'" class="audio-actions">
              <n-text depth="3" class="audio-ready-text">{{ t('speechToText.audioReady', { name: audioFile.name }) }}</n-text>
              <n-button size="small" quaternary @click="resetAll">{{ t('speechToText.clear') }}</n-button>
            </div>

            <div class="speech-options">
              <n-text class="options-title">{{ t('speechToText.optionsTitle') }}</n-text>
              <div class="options-field">
                <n-text class="field-label">{{ t('speechToText.recognizeLanguage') }}</n-text>
                <n-select v-model:value="language" :options="languageOptions" size="small" />
              </div>
              <div class="options-checks">
                <n-checkbox
                  v-model:checked="diarize"
                  :disabled="!meta?.diarization_available"
                >
                  {{ t('speechToText.diarize') }}
                </n-checkbox>
                <n-checkbox
                  v-if="meta?.summarize_available"
                  v-model:checked="autoSummarize"
                >
                  {{ t('speechToText.autoSummarize') }}
                </n-checkbox>
              </div>
            </div>

            <n-button
              type="primary"
              block
              size="medium"
              class="transcribe-btn"
              :loading="transcribing"
              :disabled="!canTranscribe"
              @click="runTranscribe"
            >
              <template #icon>
                <n-icon :component="CloudUploadOutline" />
              </template>
              {{
                streamRecognize && segments.length
                  ? t('speechToText.retranscribeAll')
                  : t('speechToText.startTranscribe')
              }}
            </n-button>
          </div>
        </n-card>

        <div class="speech-output-column">
          <n-card :title="t('speechToText.transcriptResult')" size="small" class="panel panel-transcript">
            <template #header-extra>
              <n-button size="tiny" quaternary :disabled="!transcript" @click="copyText(transcript)">
                <template #icon><n-icon :component="CopyOutline" /></template>
                {{ t('speechToText.copy') }}
              </n-button>
            </template>

            <div class="panel-body">
              <div v-if="segments.length" class="segment-list">
                <div v-for="(seg, i) in segments" :key="i" class="segment-row">
                  <div class="segment-meta">
                    <n-tag
                      size="small"
                      :bordered="false"
                      round
                      :style="{ background: speakerColor(seg.speaker) + '18', color: speakerColor(seg.speaker) }"
                    >
                      {{ seg.speaker }}
                    </n-tag>
                    <n-text depth="3" class="seg-time">{{ formatTime(seg.start) }}</n-text>
                  </div>
                  <n-text class="seg-text">{{ seg.text }}</n-text>
                </div>
              </div>
              <div v-else-if="!transcript" class="panel-empty">
                <n-text depth="3">{{ t('speechToText.transcriptEmpty') }}</n-text>
              </div>

              <div class="textarea-fill">
                <n-input
                  v-model:value="transcript"
                  type="textarea"
                  :placeholder="t('speechToText.transcriptPlaceholder')"
                />
              </div>
            </div>
          </n-card>

          <n-card :title="t('speechToText.smartSummary')" size="small" class="panel panel-summary">
            <div class="panel-body">
              <div class="summary-toolbar">
                <n-select
                  v-model:value="summaryStyle"
                  :options="summaryStyleOptions"
                  size="small"
                  class="summary-style-select"
                />
                <n-button
                  size="small"
                  secondary
                  :loading="summarizing"
                  :disabled="!canSummarize"
                  @click="runSummarize"
                >
                  <template #icon><n-icon :component="SparklesOutline" /></template>
                  {{ t('speechToText.generateSummary') }}
                </n-button>
                <div class="summary-toolbar-actions">
                  <n-button
                    size="tiny"
                    quaternary
                    :disabled="!buildSummaryExportText()"
                    @click="copyText(buildSummaryExportText())"
                  >
                    <template #icon><n-icon :component="CopyOutline" /></template>
                    {{ t('speechToText.copy') }}
                  </n-button>
                  <n-button
                    v-if="hasPerm('feature.kg')"
                    size="tiny"
                    quaternary
                    :loading="importingKg"
                    :disabled="!canImportKg"
                    @click="runImportKg()"
                  >
                    <template #icon><n-icon :component="GitNetworkOutline" /></template>
                    {{ t('speechToText.importKg') }}
                  </n-button>
                  <n-button
                    size="tiny"
                    quaternary
                    :loading="importingLibrary"
                    :disabled="!canImportLibrary"
                    @click="runImportLibrary()"
                  >
                    <template #icon><n-icon :component="LibraryOutline" /></template>
                    {{ t('speechToText.importLibrary') }}
                  </n-button>
                </div>
              </div>

              <div v-if="summaryBlocks.length" class="summary-blocks">
                <div v-for="(blk, i) in summaryBlocks" :key="i" class="summary-block">
                  <div class="segment-meta">
                    <n-tag
                      size="small"
                      :bordered="false"
                      round
                      :style="{ background: speakerColor(blk.speaker) + '18', color: speakerColor(blk.speaker) }"
                    >
                      {{ blk.speaker }}
                    </n-tag>
                    <n-text depth="3" class="blk-time">{{ blk.time_range }}</n-text>
                  </div>
                  <n-text class="blk-summary">{{ blk.summary }}</n-text>
                </div>
              </div>
              <div v-else-if="!summary" class="panel-empty panel-empty--compact">
                <n-text depth="3">{{ t('speechToText.summaryEmpty') }}</n-text>
              </div>

              <div class="textarea-fill">
                <n-input
                  v-model:value="summary"
                  type="textarea"
                  :placeholder="
                    meta?.summarize_available
                      ? t('speechToText.summaryPlaceholderAvailable')
                      : t('speechToText.summaryPlaceholderUnavailable')
                  "
                  :disabled="!meta?.summarize_available"
                />
              </div>
            </div>
          </n-card>
        </div>
      </div>
    </n-spin>
  </FeatureSubsystemShell>
</template>

<style scoped>
.speech-spin {
  flex: 1;
  min-height: 0;
  min-width: 0;
  max-width: 100%;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  padding-top: 8px;
  overflow-y: auto;
}
.speech-spin :deep(.n-spin-container),
.speech-spin :deep(.n-spin-content) {
  flex: 1;
  min-height: 0;
  min-width: 0;
  max-width: 100%;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
}
.speech-alerts {
  flex-shrink: 0;
}
.speech-layout {
  flex: none;
  min-width: 0;
  max-width: 100%;
  display: grid;
  grid-template-columns: minmax(280px, 0.92fr) minmax(0, 1.2fr);
  gap: 16px;
  align-items: start;
  box-sizing: border-box;
  padding-bottom: 24px;
}
.speech-output-column {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}
.panel {
  border-radius: var(--platform-card-radius, 12px);
  min-width: 0;
  max-width: 100%;
  display: flex;
  flex-direction: column;
  background: var(--platform-card-bg, var(--platform-bg-elevated));
}
.panel :deep(.n-card__content) {
  display: flex;
  flex-direction: column;
}
.panel-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 来源模式分段切换 */
.source-mode-switch {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 4px;
  padding: 4px;
  border-radius: var(--platform-radius-sm, 9px);
  background: var(--platform-bg-secondary);
  flex-shrink: 0;
}
.source-mode-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin: 0;
  padding: 8px 6px;
  border: none;
  border-radius: var(--platform-radius-xs, 6px);
  background: transparent;
  color: var(--platform-text-secondary);
  font: inherit;
  font-size: var(--platform-font-size-sm, 12px);
  font-weight: 500;
  cursor: pointer;
  transition:
    background 0.18s var(--platform-ease-smooth),
    color 0.18s var(--platform-ease-smooth),
    box-shadow 0.18s var(--platform-ease-smooth);
}
.source-mode-btn:hover {
  color: var(--platform-text);
  background: color-mix(in srgb, var(--platform-bg-elevated) 70%, transparent);
}
.source-mode-btn--active {
  color: var(--platform-accent);
  background: var(--platform-bg-elevated-solid, #fff);
  box-shadow: var(--platform-shadow-sm);
}
.source-main {
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
.video-url-block {
  min-height: 180px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 16px;
  border-radius: var(--platform-radius-sm, 9px);
  border: 1px solid var(--platform-border-strong);
  background: var(--platform-bg-secondary);
}
.video-url-icon {
  width: 36px;
  height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--platform-radius-xs, 6px);
  color: var(--platform-accent);
  background: var(--platform-accent-soft);
}
.video-url-hint {
  font-size: var(--platform-font-size-sm, 12px);
  line-height: 1.5;
}
.panel-transcript,
.panel-summary {
  min-height: 280px;
}
.textarea-fill {
  min-height: 160px;
  display: flex;
}
.textarea-fill :deep(.n-input) {
  height: 100%;
  min-height: 160px;
}
.textarea-fill :deep(textarea) {
  height: 100% !important;
  min-height: 160px;
  resize: vertical;
  font-size: var(--platform-font-size-base, 13px);
  line-height: var(--platform-line-body, 1.55);
}
.page-alert {
  margin-bottom: 12px;
}

/* 录音区 */
.record-block {
  min-height: 200px;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 12px;
  padding: 14px;
  border-radius: var(--platform-radius-sm, 9px);
  border: 1px solid var(--platform-border-strong);
  background: var(--platform-bg-secondary);
  transition: border-color 0.2s var(--platform-ease-smooth);
}
.record-block--live {
  border-color: var(--platform-accent-border);
}
.record-stage {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.record-timer {
  display: inline-flex;
  align-items: center;
  align-self: flex-start;
  gap: 8px;
  padding: 4px 10px;
  border-radius: var(--platform-radius-pill);
  background: var(--platform-bg-elevated-solid, #fff);
  border: 1px solid var(--platform-border);
  color: var(--platform-text-secondary);
  font-variant-numeric: tabular-nums;
}
.record-timer--live {
  color: var(--platform-danger);
  border-color: color-mix(in srgb, var(--platform-danger) 28%, var(--platform-border));
  background: var(--platform-danger-soft);
}
.record-pulse {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--platform-danger);
  animation: speech-pulse 1.2s var(--platform-ease-smooth) infinite;
}
.record-timer-text {
  font-size: var(--platform-font-size-sm, 12px);
  font-weight: 600;
  letter-spacing: 0.02em;
}
@keyframes speech-pulse {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.45;
    transform: scale(0.85);
  }
}
.record-controls {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}
.record-status-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.record-hint {
  font-size: var(--platform-font-size-sm, 12px);
  line-height: 1.45;
}
.stream-check {
  font-size: var(--platform-font-size-sm, 12px);
}
.live-segments {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 160px;
  overflow-y: auto;
  padding: 8px;
  border-radius: var(--platform-radius-xs, 6px);
  background: var(--platform-bg-elevated-solid, #fff);
  border: 1px solid var(--platform-border);
}
.live-seg-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: var(--platform-font-size-sm, 12px);
}
.live-seg-row.error .live-seg-text {
  color: var(--platform-danger);
}
.live-seg-text {
  flex: 1;
  line-height: 1.45;
}
.audio-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  border-radius: var(--platform-radius-xs, 6px);
  background: var(--platform-accent-soft);
  border: 1px solid var(--platform-accent-border-soft);
}
.audio-ready-text {
  font-size: var(--platform-font-size-sm, 12px);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 转写选项 */
.speech-options {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border-radius: var(--platform-radius-sm, 9px);
  background: var(--platform-bg-secondary);
  border: 1px solid var(--platform-border);
  flex-shrink: 0;
}
.options-title {
  font-size: var(--platform-font-size-sm, 12px);
  font-weight: 600;
  color: var(--platform-text);
}
.options-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.field-label {
  display: block;
  font-size: var(--platform-font-size-sm, 12px);
  color: var(--platform-text-secondary);
}
.options-checks {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.transcribe-btn {
  flex-shrink: 0;
  margin-top: 2px;
}

/* 转写时间线 */
.segment-list,
.summary-blocks,
.record-segments {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 240px;
  overflow-y: auto;
  padding-right: 2px;
}
.segment-row,
.summary-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  border-radius: var(--platform-radius-xs, 6px);
  background: var(--platform-bg-secondary);
  border: 1px solid transparent;
  transition: border-color 0.16s var(--platform-ease-smooth);
}
.segment-row:hover,
.summary-block:hover {
  border-color: var(--platform-border-strong);
}
.segment-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}
.seg-time,
.blk-time {
  font-size: var(--platform-font-size-xs, 9px);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.seg-text,
.blk-summary {
  font-size: var(--platform-font-size-base, 13px);
  line-height: var(--platform-line-body, 1.55);
  color: var(--platform-text);
}

.summary-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.summary-style-select {
  width: 128px;
}
.summary-toolbar-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 2px;
  margin-left: auto;
}

.panel-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 72px;
  padding: 16px;
  border-radius: var(--platform-radius-xs, 6px);
  border: 1px dashed var(--platform-border-strong);
  background: var(--platform-bg-secondary);
  text-align: center;
  font-size: var(--platform-font-size-sm, 12px);
}
.panel-empty--compact {
  min-height: 48px;
  padding: 12px;
}

.record-list-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: var(--platform-radius-sm, 9px);
  border: 1px solid var(--platform-border);
  background: var(--platform-bg-elevated);
  cursor: default;
  transition:
    background 0.16s var(--platform-ease-smooth),
    border-color 0.16s var(--platform-ease-smooth);
}
.record-list-item:hover {
  border-color: color-mix(in srgb, var(--platform-accent) 22%, var(--platform-border));
  box-shadow: inset 3px 0 0 var(--platform-accent);
}
.record-list-main {
  flex: 1;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

@media (max-width: 900px) {
  .speech-layout {
    grid-template-columns: 1fr;
  }
  .source-mode-btn span {
    display: none;
  }
  .source-mode-btn {
    padding: 10px;
  }
  .summary-toolbar-actions {
    margin-left: 0;
    width: 100%;
  }
}
</style>
