<script setup>
import { usePlatformUi } from "../composables/usePlatformUi";
import { useI18n } from "../composables/useI18n.js";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  NAlert,
  NButton,
  NCard,
  NGi,
  NGrid,
  NIcon,
  NInput,
  NSelect,
  NSlider,
  NSpace,
  NSpin,
  NTag,
  NText,
} from "naive-ui";
import {
  DownloadOutline,
  PlayOutline,
  PauseOutline,
  RefreshOutline,
  VolumeHighOutline,
} from "@vicons/ionicons5";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import {
  downloadSpeechBlob,
  fetchTextToSpeechMeta,
  synthesizeTextToSpeech,
} from "../api/textToSpeech.js";
import { FEATURE_UNAVAILABLE } from "../utils/uiMessage";

const ui = usePlatformUi();
const { t } = useI18n();

const meta = ref(null);
const loadingMeta = ref(true);
const error = ref("");
const text = ref("");
const voiceId = ref("claire");
const emotion = ref("");
const speed = ref(1);
const responseFormat = ref("mp3");
const synthesizing = ref(false);
const audioUrl = ref("");
const audioFilename = ref("");
const audioRef = ref(null);
const playing = ref(false);

const SAMPLE_TEXT = computed(() => t("textToSpeech.sampleText"));

const configured = computed(() => meta.value?.configured ?? false);
const maxChars = computed(() => meta.value?.max_input_chars ?? 2000);
const charCount = computed(() => (text.value || "").length);
const charOverLimit = computed(() => charCount.value > maxChars.value);

const voiceOptions = computed(() => {
  const voices = meta.value?.voices || [];
  return voices.map((v) => ({
    label:
      v.gender === "male"
        ? `${v.label}${t("textToSpeech.voiceMale")}`
        : `${v.label}${t("textToSpeech.voiceFemale")}`,
    value: v.id,
  }));
});

const emotionOptions = computed(() => [
  { label: t("textToSpeech.emotionDefault"), value: "" },
  ...(meta.value?.emotions || []).map((e) => ({ label: e.label, value: e.id })),
]);

const formatOptions = computed(() =>
  (meta.value?.supported_formats || ["mp3", "wav"]).map((f) => ({
    label: f.toUpperCase(),
    value: f,
  }))
);

const canSynthesize = computed(
  () =>
    configured.value &&
    !synthesizing.value &&
    text.value.trim().length > 0 &&
    !charOverLimit.value
);

const hasAudio = computed(() => Boolean(audioUrl.value));

function ensureVoiceSelection() {
  const voices = meta.value?.voices || [];
  if (!voices.length) return;
  const ids = new Set(voices.map((v) => v.id));
  if (!ids.has(voiceId.value)) {
    voiceId.value = voices.find((v) => v.id === "claire")?.id || voices[0].id;
  }
}

function revokeAudioUrl() {
  if (audioUrl.value) {
    URL.revokeObjectURL(audioUrl.value);
    audioUrl.value = "";
  }
  playing.value = false;
}

function onAudioPlay() {
  playing.value = true;
}

function onAudioPause() {
  playing.value = false;
}

function onAudioEnded() {
  playing.value = false;
}

async function loadMeta() {
  loadingMeta.value = true;
  error.value = "";
  try {
    meta.value = await fetchTextToSpeechMeta();
    if (meta.value?.default_format) {
      responseFormat.value = meta.value.default_format;
    }
    ensureVoiceSelection();
  } catch (e) {
    error.value = e.message || t("textToSpeech.loadConfigFailed");
  } finally {
    loadingMeta.value = false;
  }
}

function fillSample() {
  text.value = SAMPLE_TEXT.value;
}

function clearText() {
  text.value = "";
}

async function runSynthesize() {
  if (!canSynthesize.value) return;
  synthesizing.value = true;
  error.value = "";
  revokeAudioUrl();
  try {
    const { blob, filename } = await synthesizeTextToSpeech({
      text: text.value.trim(),
      voiceId: voiceId.value,
      emotion: emotion.value || null,
      speed: speed.value,
      responseFormat: responseFormat.value,
    });
    audioFilename.value = filename;
    audioUrl.value = URL.createObjectURL(blob);
    ui.success(t("textToSpeech.synthComplete"));
    requestAnimationFrame(() => {
      audioRef.value?.play?.().catch(() => {});
    });
  } catch (e) {
    error.value = e.message || t("textToSpeech.synthFailed");
    ui.error(error.value);
  } finally {
    synthesizing.value = false;
  }
}

function togglePlayback() {
  const el = audioRef.value;
  if (!el) return;
  if (el.paused) {
    el.play().catch(() => ui.warning(t("textToSpeech.cannotPlay")));
  } else {
    el.pause();
  }
}

function downloadAudio() {
  if (!audioUrl.value) return;
  fetch(audioUrl.value)
    .then((r) => r.blob())
    .then((blob) => downloadSpeechBlob(blob, audioFilename.value || "speech.mp3"))
    .catch(() => ui.error(t("textToSpeech.downloadFailed")));
}

watch(responseFormat, () => {
  if (hasAudio.value) revokeAudioUrl();
});

onMounted(loadMeta);
onBeforeUnmount(revokeAudioUrl);
</script>

<template>
  <FeatureSubsystemShell fill>
    <NSpin :show="loadingMeta" class="tts-spin">
      <div class="tts-page">
        <NAlert
          v-if="!loadingMeta && !configured"
          type="warning"
          :title="FEATURE_UNAVAILABLE"
          style="margin-bottom: 16px"
        >
          {{ t('textToSpeech.configHint') }}
        </NAlert>

        <NAlert v-if="error && configured" type="error" closable style="margin-bottom: 16px" @close="error = ''">
          {{ error }}
        </NAlert>

        <NGrid v-if="meta" cols="1 m:2" responsive="screen" :x-gap="20" :y-gap="20" class="tts-grid">
          <NGi>
            <NCard :title="t('textToSpeech.inputText')" size="small" class="tts-card">
              <template #header-extra>
                <NSpace size="small">
                  <NButton size="tiny" quaternary @click="fillSample">{{ t('textToSpeech.sample') }}</NButton>
                  <NButton size="tiny" quaternary @click="clearText">{{ t('textToSpeech.clear') }}</NButton>
                </NSpace>
              </template>

              <NInput
                v-model:value="text"
                type="textarea"
                :rows="10"
                :placeholder="t('textToSpeech.inputPlaceholder')"
                :maxlength="maxChars + 200"
                show-count
              />

              <div class="tts-meta-row">
                <NText depth="3" :type="charOverLimit ? 'error' : undefined">
                  {{ t('textToSpeech.charCount', { count: charCount, max: maxChars }) }}
                </NText>
                <NTag v-if="meta?.model" size="small" round type="info">
                  {{ meta.model }}
                </NTag>
              </div>
            </NCard>
          </NGi>

          <NGi>
            <NCard :title="t('textToSpeech.synthesisSettings')" size="small" class="tts-card">
              <div class="tts-field">
                <label class="tts-label">{{ t('textToSpeech.voice') }}</label>
                <NSelect v-model:value="voiceId" :options="voiceOptions" />
              </div>

              <div class="tts-field">
                <label class="tts-label">{{ t('textToSpeech.emotion') }}</label>
                <NSelect v-model:value="emotion" :options="emotionOptions" clearable />
              </div>

              <div class="tts-field">
                <label class="tts-label">{{ t('textToSpeech.speed', { speed: speed.toFixed(1) }) }}</label>
                <NSlider v-model:value="speed" :min="0.5" :max="2" :step="0.1" />
              </div>

              <div class="tts-field">
                <label class="tts-label">{{ t('textToSpeech.outputFormat') }}</label>
                <NSelect v-model:value="responseFormat" :options="formatOptions" />
              </div>

              <NButton
                type="primary"
                block
                size="large"
                :loading="synthesizing"
                :disabled="!canSynthesize"
                class="tts-generate-btn"
                @click="runSynthesize"
              >
                <template #icon>
                  <NIcon><VolumeHighOutline /></NIcon>
                </template>
                {{ t('textToSpeech.generate') }}
              </NButton>
            </NCard>

            <NCard :title="t('textToSpeech.previewAndDownload')" size="small" class="tts-card tts-player-card">
              <div v-if="hasAudio" class="tts-player">
                <audio
                  ref="audioRef"
                  :src="audioUrl"
                  controls
                  class="tts-audio"
                  @play="onAudioPlay"
                  @pause="onAudioPause"
                  @ended="onAudioEnded"
                />
                <NSpace justify="center" style="margin-top: 12px">
                  <NButton secondary @click="togglePlayback">
                    <template #icon>
                      <NIcon><component :is="playing ? PauseOutline : PlayOutline" /></NIcon>
                    </template>
                    {{ playing ? t('textToSpeech.pause') : t('textToSpeech.play') }}
                  </NButton>
                  <NButton secondary @click="downloadAudio">
                    <template #icon>
                      <NIcon><DownloadOutline /></NIcon>
                    </template>
                    {{ t('textToSpeech.download') }}
                  </NButton>
                  <NButton quaternary @click="runSynthesize">
                    <template #icon>
                      <NIcon><RefreshOutline /></NIcon>
                    </template>
                    {{ t('textToSpeech.regenerate') }}
                  </NButton>
                </NSpace>
              </div>
              <div v-else class="tts-player-empty">
                <NIcon size="48" depth="3"><VolumeHighOutline /></NIcon>
                <NText depth="3">{{ t('textToSpeech.playerEmpty') }}</NText>
              </div>
            </NCard>
          </NGi>
        </NGrid>
        <NGrid v-else-if="!loadingMeta" cols="1" class="tts-grid">
          <NGi>
            <NAlert type="warning">{{ t('textToSpeech.loadFailed') }}</NAlert>
          </NGi>
        </NGrid>
      </div>
    </NSpin>
  </FeatureSubsystemShell>
</template>

<style scoped>
.tts-spin {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.tts-spin :deep(.n-spin-content) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.tts-page {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 4px 0 24px;
  box-sizing: border-box;
}

.tts-grid {
  align-items: start;
}

.tts-card {
  margin-bottom: 16px;
}

.tts-card:last-child {
  margin-bottom: 0;
}

.tts-meta-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10px;
  gap: 8px;
}

.tts-field {
  margin-bottom: 18px;
}

.tts-field:last-of-type {
  margin-bottom: 20px;
}

.tts-label {
  display: block;
  font-size: 13px;
  color: var(--n-text-color-2);
  margin-bottom: 6px;
}

.tts-generate-btn {
  margin-top: 4px;
}

.tts-player-card {
  min-height: 160px;
}

.tts-player {
  display: flex;
  flex-direction: column;
}

.tts-audio {
  width: 100%;
  border-radius: 8px;
}

.tts-player-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  min-height: 120px;
  padding: 24px;
}
</style>
