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
  GitNetworkOutline } from "@vicons/ionicons5";
import FileDropZone from "../components/FileDropZone.vue";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import ListRefreshButton from "../components/ListRefreshButton.vue";
import { LIST_PAGE_SIZE } from "../constants/listPage.js";
import AudioWaveform from "../components/AudioWaveform.vue";
import {
  deleteMeetingRecord,
  fetchMeetingRecord,
  fetchSpeechMeta,
  listMeetingRecords,
  saveMeetingRecord,
  summarizeSpeech,
  transcribeSpeech } from "../api/client";
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
  () => hasPerm("feature.kg_palantir") && !!buildSummaryExportText().length
);

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
  const colors = ["#2080f0", "#8b5cf6", "#f0a020", "#d03050", "#5b9cf5"];
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
    ui.error(t("speechToText.micAccessDenied"));
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
        path: "/system/kg-palantir",
        query: { focusEntityId: res.root_entity_id },
      });
    }
  } catch (e) {
    ui.error(e.message);
  } finally {
    importingKg.value = false;
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
      <n-space :size="8">
        <n-button quaternary @click="openRecordsDrawer">
          <template #icon><n-icon :component="FolderOpenOutline" /></template>
          {{ t('speechToText.meetingRecords') }}
        </n-button>
        <n-button type="primary" secondary :disabled="!canSave" :loading="saving" @click="openSaveModal">
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

    <n-drawer v-model:show="recordsDrawerOpen" :width="520" placement="right">
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
            <n-space vertical :size="12">
              <n-button size="small" quaternary @click="viewingRecord = null">{{ t('speechToText.backToList') }}</n-button>
              <n-text strong>{{ viewingRecord.title }}</n-text>
              <n-text depth="3" style="font-size: 12px">
                {{ formatRecordTime(viewingRecord.created_at) }}
              </n-text>
              <n-button size="small" type="primary" @click="applyRecordToEditor(viewingRecord)">
                {{ t('speechToText.loadToEditor') }}
              </n-button>
              <n-button
                v-if="hasPerm('feature.kg_palantir')"
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
              <n-text strong style="font-size: 13px">{{ t('speechToText.transcript') }}</n-text>
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
                <n-text strong style="font-size: 13px">{{ t('speechToText.timelineSummary') }}</n-text>
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
                <n-text strong style="font-size: 13px">{{ t('speechToText.summary') }}</n-text>
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
                  <n-text strong>{{ item.title || t('speechToText.unnamedMeeting') }}</n-text>
                  <n-text depth="3" style="font-size: 12px">
                    {{ t('speechToText.recordMeta', { time: formatRecordTime(item.created_at), count: item.segment_count }) }}
                    <n-tag v-if="item.has_summary" size="tiny" :bordered="false" style="margin-left: 6px">
                      {{ t('speechToText.summarized') }}
                    </n-tag>
                  </n-text>
                </div>
                <n-button size="tiny" quaternary type="error" @click.stop="confirmDeleteRecord(item)">
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
              style="margin-top: 8px"
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
          <n-card :title="t('speechToText.audioSource')" class="panel panel-source">
            <div class="panel-body">
            <n-space vertical :size="16" class="source-space">
              <n-space :size="8">
                <n-button
                  :type="sourceMode === 'record' ? 'primary' : 'default'"
                  :secondary="sourceMode !== 'record'"
                  @click="sourceMode = 'record'"
                >
                  {{ t('speechToText.browserRecord') }}
                </n-button>
                <n-button
                  :type="sourceMode === 'upload' ? 'primary' : 'default'"
                  :secondary="sourceMode !== 'upload'"
                  @click="sourceMode = 'upload'"
                >
                  {{ t('speechToText.uploadFile') }}
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
                    {{ recording ? t('speechToText.stopRecording') : t('speechToText.startRecording') }}
                  </n-button>
                  <n-tag v-if="recording && streamRecognize" type="warning" size="small" :bordered="false">
                    <template #icon>
                      <n-icon :component="RadioOutline" />
                    </template>
                    {{ t('speechToText.liveTranscribing') }}
                  </n-tag>
                  <n-tag v-if="pendingStreamCount" size="small" :bordered="false">
                    {{ t('speechToText.segmentsRecognizing', { count: pendingStreamCount }) }}
                  </n-tag>
                </n-space>
                <n-text depth="3" class="record-hint">{{ recordHint }}</n-text>
                <n-checkbox v-model:checked="streamRecognize" :disabled="recording">
                  {{ t('speechToText.streamRecognizeLabel') }}
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
                    <n-text class="live-seg-text">{{ item.text || t('speechToText.recognizing') }}</n-text>
                  </div>
                </div>
              </div>

              <div v-else class="upload-fill source-main">
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

              <div v-if="audioFile" class="audio-actions">
                <n-text depth="3">{{ t('speechToText.audioReady', { name: audioFile.name }) }}</n-text>
                <n-button size="small" quaternary @click="resetAll">{{ t('speechToText.clear') }}</n-button>
              </div>

              <div>
                <n-text class="field-label">{{ t('speechToText.recognizeLanguage') }}</n-text>
                <n-select v-model:value="language" :options="languageOptions" />
              </div>

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
                    ? t('speechToText.retranscribeAll')
                    : t('speechToText.startTranscribe')
                }}
              </n-button>
            </n-space>
            </div>
          </n-card>

          <div class="speech-output-column">
          <n-card :title="t('speechToText.transcriptResult')" class="panel panel-transcript">
            <template #header-extra>
              <n-button size="small" quaternary :disabled="!transcript" @click="copyText(transcript)">
                <template #icon><n-icon :component="CopyOutline" /></template>
                {{ t('speechToText.copy') }}
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
                  :placeholder="t('speechToText.transcriptPlaceholder')"
                />
              </div>
            </div>
          </n-card>

          <n-card :title="t('speechToText.smartSummary')" class="panel panel-summary">
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
                  {{ t('speechToText.generateSummary') }}
                </n-button>
                <n-button
                  size="small"
                  quaternary
                  :disabled="!buildSummaryExportText()"
                  @click="copyText(buildSummaryExportText())"
                >
                  {{ t('speechToText.copy') }}
                </n-button>
                <n-button
                  v-if="hasPerm('feature.kg_palantir')"
                  size="small"
                  quaternary
                  :loading="importingKg"
                  :disabled="!canImportKg"
                  @click="runImportKg()"
                >
                  <template #icon><n-icon :component="GitNetworkOutline" /></template>
                  {{ t('speechToText.importKg') }}
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
  min-width: 0;
  max-width: 100%;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
}
.speech-spin :deep(.n-spin-container) {
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
  flex: 1;
  min-height: 0;
  min-width: 0;
  max-width: 100%;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.15fr);
  gap: 16px;
  align-items: stretch;
  box-sizing: border-box;
  overflow: hidden;
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
  min-width: 0;
  max-width: 100%;
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
  gap: 10px;
  padding: 12px 14px;
  border-radius: calc(var(--platform-radius-sm) + 2px);
  border: 1px solid var(--platform-border);
  background: var(--platform-ui-glass-fill-strong, var(--platform-bg-elevated));
  box-shadow: var(--platform-ui-layer-shadow, var(--platform-shadow-sm));
  cursor: default;
  transition:
    background 0.16s var(--platform-ease-smooth),
    box-shadow 0.16s var(--platform-ease-smooth),
    border-color 0.16s var(--platform-ease-smooth);
}

.record-list-item:hover {
  border-color: color-mix(in srgb, var(--platform-accent) 22%, var(--platform-border));
  box-shadow:
    inset 3px 0 0 var(--platform-accent),
    var(--platform-ui-layer-shadow, var(--platform-shadow-sm));
}

.record-list-main {
  flex: 1;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.record-list-main:hover {
  opacity: 1;
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
