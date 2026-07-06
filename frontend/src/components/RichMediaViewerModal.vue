<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { NButton, NSpace } from "naive-ui";
import AdminFormModal from "./AdminFormModal.vue";
import { useI18n } from "../composables/useI18n.js";
import { usePlatformUi } from "../composables/usePlatformUi.js";
import {
  downloadEchartPng,
  downloadImageElement,
  downloadSvgAsPng,
  downloadSvgElement,
  exportCodeBlockMarkdown,
  exportInlineMindmapMarkdown,
  exportInlineMindmapOpml,
  exportMermaidSourceMarkdown,
} from "../utils/richMediaExport.js";
import { loadEcharts } from "../utils/echartsLoader.js";

const props = defineProps({
  show: { type: Boolean, default: false },
  payload: { type: Object, default: null },
});

const emit = defineEmits(["update:show"]);

const { t } = useI18n();
const ui = usePlatformUi();
const viewportRef = ref(null);
const echartHostRef = ref(null);
let echartInstance = null;

const modalTitle = computed(() => props.payload?.title || t("richMedia.viewTitle"));

const canSaveImage = computed(() =>
  ["image", "mermaid", "echart"].includes(props.payload?.type)
);

const canExportMarkdown = computed(() =>
  ["mermaid", "code"].includes(props.payload?.type)
);

const canExportOpml = computed(() =>
  props.payload?.type === "mermaid" && props.payload?.isMindmap
);

function close() {
  emit("update:show", false);
}

function disposeEchart() {
  echartInstance?.dispose?.();
  echartInstance = null;
}

async function renderEchartInModal() {
  disposeEchart();
  const option = props.payload?.echartOption;
  if (!option || !echartHostRef.value || !props.show) return;
  const echarts = await loadEcharts();
  await nextTick();
  if (!props.show || props.payload?.type !== "echart" || !echartHostRef.value) return;
  echartInstance = echarts.init(echartHostRef.value, undefined, { renderer: "canvas" });
  echartInstance.setOption(option, { notMerge: true });
  echartInstance.resize();
}

watch(
  () => [props.show, props.payload?.type, props.payload?.echartOption],
  async ([visible, type]) => {
    if (!visible) {
      disposeEchart();
      return;
    }
    if (type === "echart") {
      await nextTick();
      await renderEchartInModal();
    } else {
      disposeEchart();
    }
  }
);

onBeforeUnmount(disposeEchart);

function getSvgElement() {
  return viewportRef.value?.querySelector("svg") || null;
}

async function onSaveImage() {
  const payload = props.payload;
  if (!payload) return;
  const stem = (payload.title || "diagram").replace(/[\\/:*?"<>|]+/g, "_").slice(0, 60);
  try {
    if (payload.type === "image") {
      const img = viewportRef.value?.querySelector("img");
      if (!img) throw new Error(t("richMedia.saveFailed"));
      await downloadImageElement(img, `${stem}.png`);
      ui.success(t("richMedia.savePngSuccess"));
      return;
    }
    if (payload.type === "mermaid") {
      const svg = getSvgElement();
      if (!svg) throw new Error(t("richMedia.saveFailed"));
      const result = await downloadSvgAsPng(svg, `${stem}.png`);
      if (result?.fallback) {
        ui.warning(t("richMedia.savePngFallbackSvg"));
      } else {
        ui.success(t("richMedia.savePngSuccess"));
      }
      return;
    }
    if (payload.type === "echart") {
      if (!echartInstance) throw new Error(t("richMedia.saveFailed"));
      downloadEchartPng(echartInstance, `${stem}.png`);
      ui.success(t("richMedia.savePngSuccess"));
    }
  } catch (e) {
    ui.error(e.message || t("richMedia.saveFailed"));
  }
}

async function onSaveSvg() {
  const svg = getSvgElement();
  if (!svg) return;
  const stem = (props.payload?.title || "diagram").replace(/[\\/:*?"<>|]+/g, "_").slice(0, 60);
  try {
    downloadSvgElement(svg, `${stem}.svg`);
    ui.success(t("richMedia.saveSvgSuccess"));
  } catch (e) {
    ui.error(e.message || t("richMedia.saveFailed"));
  }
}

function onExportMarkdown() {
  const payload = props.payload;
  if (!payload) return;
  try {
    if (payload.type === "mermaid") {
      if (payload.isMindmap) {
        exportInlineMindmapMarkdown(payload.mermaidSource, payload.title);
      } else {
        exportMermaidSourceMarkdown(payload.mermaidSource, payload.title);
      }
      return;
    }
    if (payload.type === "code") {
      exportCodeBlockMarkdown(payload.code, payload.language, payload.title);
    }
  } catch (e) {
    ui.error(e.message || t("richMedia.exportFailed"));
  }
}

function onExportOpml() {
  try {
    exportInlineMindmapOpml(props.payload?.mermaidSource, props.payload?.title);
  } catch (e) {
    ui.error(e.message || t("richMedia.exportFailed"));
  }
}
</script>

<template>
  <AdminFormModal
    :show="show"
    :title="modalTitle"
    width="min(880px, 92vw)"
    @update:show="emit('update:show', $event)"
  >
    <div class="rich-media-viewer">
      <div ref="viewportRef" class="rich-media-viewer__viewport">
      <img
        v-if="payload?.type === 'image'"
        class="rich-media-viewer__image"
        :src="payload.imageUrl"
        :alt="payload.title"
      />
      <div
        v-else-if="payload?.type === 'mermaid'"
        class="rich-media-viewer__mermaid"
        v-html="payload.svgHtml"
      />
      <div
        v-else-if="payload?.type === 'echart'"
        ref="echartHostRef"
        class="rich-media-viewer__echart"
      />
      <pre v-else-if="payload?.type === 'code'" class="rich-media-viewer__code"><code>{{ payload.code }}</code></pre>
      </div>
    </div>

    <template #footer>
      <NSpace>
        <NButton v-if="canSaveImage" type="primary" @click="onSaveImage">
          {{ t("richMedia.savePng") }}
        </NButton>
        <NButton v-if="payload?.type === 'mermaid'" @click="onSaveSvg">
          {{ t("richMedia.saveSvg") }}
        </NButton>
        <NButton v-if="canExportMarkdown" @click="onExportMarkdown">
          {{ t("richMedia.exportMarkdown") }}
        </NButton>
        <NButton v-if="canExportOpml" @click="onExportOpml">
          {{ t("richMedia.exportOpml") }}
        </NButton>
        <NButton @click="close">{{ t("common.close") }}</NButton>
      </NSpace>
    </template>
  </AdminFormModal>
</template>

<style scoped>
.rich-media-viewer {
  max-height: calc(66.67vh - 7.5rem);
  min-height: 0;
}

.rich-media-viewer__viewport {
  overflow: auto;
  max-height: calc(66.67vh - 7.5rem);
  padding: 14px 10px 19px;
  border-radius: 14px;
  background: color-mix(in srgb, var(--platform-bg) 45%, transparent);
}

.rich-media-viewer__image {
  display: block;
  max-width: 100%;
  height: auto;
  margin: 0 auto;
  border-radius: 10px;
}

.rich-media-viewer__mermaid :deep(svg) {
  display: block;
  max-width: 100%;
  width: auto;
  height: auto;
  margin: 0 auto;
}

.rich-media-viewer__echart {
  width: 100%;
  height: min(432px, calc(66.67vh - 10rem));
  min-height: 288px;
}

.rich-media-viewer__code {
  margin: 0;
  padding: 14px 17px;
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.05);
  overflow: auto;
  font-size: 16px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
