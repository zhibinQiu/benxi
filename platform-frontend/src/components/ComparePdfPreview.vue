<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { NSpin, NText } from "naive-ui";
import * as pdfjsLib from "pdfjs-dist";
import pdfjsWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import {
  bboxToViewportBox,
  buildTextLayerHighlightBoxes,
} from "../utils/comparePdfHighlights.js";

/** Nginx 若未配置 .mjs → application/javascript，动态 import worker 会失败 */
let pdfWorkerInitPromise = null;

function initPdfWorker() {
  if (pdfWorkerInitPromise) return pdfWorkerInitPromise;
  pdfWorkerInitPromise = (async () => {
    const res = await fetch(pdfjsWorkerUrl);
    if (!res.ok) {
      throw new Error(`PDF worker 加载失败 (${res.status})`);
    }
    const blob = new Blob([await res.arrayBuffer()], { type: "application/javascript" });
    pdfjsLib.GlobalWorkerOptions.workerSrc = URL.createObjectURL(blob);
  })();
  return pdfWorkerInitPromise;
}

/** 双栏对比时列宽较窄，需高于布局倍率渲染以避免文字发糊 */
const MIN_PDF_RENDER_SCALE = 2;
const MAX_PDF_RENDER_SCALE = 4;
const MAX_DEVICE_PIXEL_RATIO = 3;

const emit = defineEmits(["ready", "page-change"]);

const props = defineProps({
  src: { type: String, default: "" },
  page: { type: Number, default: 1 },
  highlights: { type: Array, default: () => [] },
  diffItems: { type: Array, default: () => [] },
  diffSide: { type: String, default: "none" },
  activeDiffId: { type: [String, Number], default: null },
  caption: { type: String, default: "" },
  /** width：按宽度铺满；page：整页缩放进视口（文档详情预览） */
  fitMode: { type: String, default: "width" },
  /** 滚到顶/底时继续滚动触发翻页 */
  wheelPageFlip: { type: Boolean, default: true },
});

const numPages = ref(0);

const canvasRef = ref(null);
const scrollRef = ref(null);
const wrapRef = ref(null);
const loading = ref(false);
const error = ref("");
const overlayBoxes = ref([]);
const canvasSize = ref({ width: 0, height: 0 });

let pdfDoc = null;
let renderTask = null;
let loadToken = 0;
let resizeObserver = null;

function diffBoxClass(diffType, active) {
  const base = `pdf-diff-box pdf-diff-box--${diffType || "modify"}`;
  return active ? `${base} pdf-diff-box--active` : base;
}

function resetDoc() {
  if (renderTask) {
    try {
      renderTask.cancel();
    } catch {
      /* ignore */
    }
    renderTask = null;
  }
  const doc = pdfDoc;
  pdfDoc = null;
  if (doc) {
    void doc.destroy?.().catch(() => {});
  }
  numPages.value = 0;
  overlayBoxes.value = [];
  canvasSize.value = { width: 0, height: 0 };
  const canvas = canvasRef.value;
  if (canvas) {
    const ctx = canvas.getContext("2d");
    if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
    canvas.width = 0;
    canvas.height = 0;
  }
}

async function ensurePdf() {
  const src = String(props.src || "").trim();
  if (!src) {
    resetDoc();
    return null;
  }
  if (pdfDoc && pdfDoc._src === src) return pdfDoc;
  resetDoc();
  loading.value = true;
  error.value = "";
  const token = ++loadToken;
  try {
    await initPdfWorker();
    if (token !== loadToken) return null;
    const task = pdfjsLib.getDocument(src);
    const doc = await task.promise;
    if (token !== loadToken) {
      await doc.destroy();
      return null;
    }
    doc._src = src;
    pdfDoc = doc;
    numPages.value = doc.numPages;
    emit("ready", { numPages: doc.numPages });
    return doc;
  } catch (e) {
    if (token === loadToken) {
      error.value = e?.message || "PDF 加载失败";
      pdfDoc = null;
    }
    return null;
  } finally {
    if (token === loadToken) loading.value = false;
  }
}

async function buildOverlayBoxes(page, viewport) {
  const pageNo = props.page;
  const boxes = [];
  const bboxCovered = new Set();

  for (const hit of props.highlights || []) {
    if (!Array.isArray(hit.bbox) || hit.bbox.length < 4) continue;
    const box = bboxToViewportBox(hit.bbox, viewport, page);
    if (!box) continue;
    const key = `bbox-${hit.id}-${Math.round(box.left)}-${Math.round(box.top)}`;
    bboxCovered.add(String(hit.id));
    boxes.push({
      key,
      ...box,
      diffType: hit.diffType,
      active: Boolean(hit.active),
    });
  }

  const uncoveredDiffIds = props.diffItems
    .map((d) => String(d.id))
    .filter((id) => !bboxCovered.has(id));

  if (uncoveredDiffIds.length > 0) {
    const textBoxes = await buildTextLayerHighlightBoxes(page, viewport, pdfjsLib, {
      diffItems: props.diffItems,
      side: props.diffSide,
      pageNo,
      activeDiffId: props.activeDiffId,
      onlyDiffIds: new Set(uncoveredDiffIds),
    });
    for (const box of textBoxes) {
      if (!boxes.some((b) => b.key === box.key)) boxes.push(box);
    }
  }

  return boxes;
}

async function renderPage() {
  const doc = await ensurePdf();
  const canvas = canvasRef.value;
  const wrap = wrapRef.value;
  if (!doc || !canvas || !wrap) {
    if (doc && String(props.src || "").trim()) {
      await nextTick();
      scheduleRender();
    }
    return;
  }

  const pageNo = Math.min(Math.max(Number(props.page) || 1, 1), doc.numPages);
  loading.value = true;
  error.value = "";
  const token = ++loadToken;
  try {
    const page = await doc.getPage(pageNo);
    if (token !== loadToken) return;

    const wrapWidth = Math.max(wrap.clientWidth - 16, 280);
    const wrapHeight = Math.max(wrap.clientHeight - 16, 240);
    const baseViewport = page.getViewport({ scale: 1 });
    const dpr = Math.min(window.devicePixelRatio || 1, MAX_DEVICE_PIXEL_RATIO);
    const scaleW = wrapWidth / baseViewport.width;
    const scaleH = wrapHeight / baseViewport.height;
    const cssScale =
      props.fitMode === "page"
        ? Math.min(scaleW, scaleH)
        : scaleW;
    const layoutViewport = page.getViewport({ scale: cssScale });
    const renderScale = Math.min(
      Math.max(cssScale * dpr, MIN_PDF_RENDER_SCALE),
      MAX_PDF_RENDER_SCALE
    );
    const renderViewport = page.getViewport({ scale: renderScale });

    const ctx = canvas.getContext("2d", { alpha: false });
    if (ctx) {
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = "high";
    }
    const cssWidth = Math.floor(layoutViewport.width);
    const cssHeight = Math.floor(layoutViewport.height);
    canvas.width = Math.floor(renderViewport.width);
    canvas.height = Math.floor(renderViewport.height);
    canvas.style.width = `${cssWidth}px`;
    canvas.style.height = `${cssHeight}px`;
    canvasSize.value = { width: cssWidth, height: cssHeight };

    if (renderTask) {
      renderTask.cancel();
      renderTask = null;
    }
    renderTask = page.render({
      canvasContext: ctx,
      viewport: renderViewport,
      intent: "display",
    });
    await renderTask.promise;
    if (token !== loadToken) return;

    overlayBoxes.value = await buildOverlayBoxes(page, layoutViewport);
  } catch (e) {
    if (token === loadToken && e?.name !== "RenderingCancelledException") {
      error.value = e?.message || "PDF 渲染失败";
    }
  } finally {
    if (token === loadToken) {
      loading.value = false;
      renderTask = null;
    }
  }
}

function scheduleRender() {
  nextTick(() => renderPage());
}

function onScrollWheel(e) {
  if (!props.wheelPageFlip || numPages.value <= 1) return;
  const el = scrollRef.value;
  if (!el) return;
  const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 10;
  const atTop = el.scrollTop <= 10;
  const page = Math.max(1, Number(props.page) || 1);
  if (e.deltaY > 0 && atBottom && page < numPages.value) {
    e.preventDefault();
    emit("page-change", page + 1);
  } else if (e.deltaY < 0 && atTop && page > 1) {
    e.preventDefault();
    emit("page-change", page - 1);
  }
}

watch(
  () => [
    props.src,
    props.page,
    props.highlights,
    props.diffItems,
    props.diffSide,
    props.activeDiffId,
    props.fitMode,
  ],
  scheduleRender,
  { deep: true, immediate: true }
);

onMounted(() => {
  scheduleRender();
  if (typeof ResizeObserver !== "undefined" && wrapRef.value) {
    resizeObserver = new ResizeObserver(() => scheduleRender());
    resizeObserver.observe(wrapRef.value);
  }
});

onBeforeUnmount(() => {
  loadToken += 1;
  resizeObserver?.disconnect();
  resizeObserver = null;
  resetDoc();
});
</script>

<template>
  <div ref="wrapRef" class="compare-pdf-preview">
    <n-spin :show="loading" class="compare-pdf-preview__spin">
      <div v-if="error" class="compare-pdf-preview__error">
        <n-text depth="3">{{ error }}</n-text>
      </div>
      <div
        v-else-if="src"
        ref="scrollRef"
        class="compare-pdf-preview__scroll"
        :class="{ 'compare-pdf-preview__scroll--from-top': fitMode === 'width' }"
        @wheel="onScrollWheel"
      >
        <div
          class="compare-pdf-preview__stage"
          :style="{ width: `${canvasSize.width}px`, height: `${canvasSize.height}px` }"
        >
          <canvas ref="canvasRef" class="compare-pdf-preview__canvas" />
          <div
            v-for="box in overlayBoxes"
            :key="box.key"
            class="pdf-diff-overlay"
            :class="diffBoxClass(box.diffType, box.active)"
            :style="{
              left: `${box.left}px`,
              top: `${box.top}px`,
              width: `${box.width}px`,
              height: `${box.height}px`,
            }"
          />
        </div>
      </div>
      <div v-if="caption" class="compare-pdf-preview__caption">
        <n-text depth="3">{{ caption }}</n-text>
      </div>
    </n-spin>
  </div>
</template>

<style scoped>
.compare-pdf-preview {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #525659;
}
.compare-pdf-preview__spin {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.compare-pdf-preview__spin :deep(.n-spin-container),
.compare-pdf-preview__spin :deep(.n-spin-content) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.compare-pdf-preview__scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 8px;
  box-sizing: border-box;
}
.compare-pdf-preview__scroll--from-top {
  align-items: flex-start;
}
.compare-pdf-preview__stage {
  position: relative;
  flex-shrink: 0;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.35);
}
.compare-pdf-preview__canvas {
  display: block;
  image-rendering: high-quality;
  image-rendering: -webkit-optimize-contrast;
}
.pdf-diff-overlay {
  position: absolute;
  pointer-events: none;
  border-radius: 2px;
  box-sizing: border-box;
}
.pdf-diff-box--delete {
  background: rgba(239, 68, 68, 0.16);
  border: 1.5px solid rgba(239, 68, 68, 0.45);
}
.pdf-diff-box--add {
  background: rgba(34, 197, 94, 0.16);
  border: 1.5px solid rgba(34, 197, 94, 0.45);
}
.pdf-diff-box--modify {
  background: rgba(234, 179, 8, 0.18);
  border: 1.5px solid rgba(234, 179, 8, 0.48);
}
.pdf-diff-box--active {
  box-shadow: 0 0 0 2px rgba(234, 179, 8, 0.35);
  z-index: 2;
}
.compare-pdf-preview__caption {
  flex-shrink: 0;
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.45;
  max-height: 72px;
  overflow-y: auto;
  background: #fff;
  border-top: 1px solid var(--platform-border, rgba(15, 23, 42, 0.08));
  word-break: break-word;
}
.compare-pdf-preview__error {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: #fff;
}
</style>
