<script setup>
import { computed, defineAsyncComponent, ref } from "vue";
import { useI18n } from "../composables/useI18n.js";
import {
  NButton,
  NIcon,
  NSpace,
  NSpin,
  NTag,
  NText } from "naive-ui";
import {
  ChevronDownOutline,
  ChevronUpOutline,
  FolderOpenOutline,
  OpenOutline } from "@vicons/ionicons5";
const ComparePdfPreview = defineAsyncComponent(() => import("./ComparePdfPreview.vue"));
import { PREVIEW_KIND } from "../utils/documentPreview.js";

const props = defineProps({
  columnIndex: { type: Number, required: true },
  doc: { type: Object, default: null },
  content: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  pdfSrc: { type: String, default: "" },
  pdfPage: { type: Number, default: 1 },
  roleLabel: { type: String, default: "" },
  isBaseline: { type: Boolean, default: false },
  isSearchTarget: { type: Boolean, default: false },
  diffSide: { type: String, default: "none" },
  paragraphs: { type: Array, default: () => [] },
  plainPreview: { type: String, default: "" },
  searchHits: { type: Array, default: () => [] },
  activeHitIndex: { type: Number, default: -1 },
  activeHit: { type: Object, default: null },
  hitNavLabel: { type: String, default: "" },
  canHitPrev: { type: Boolean, default: false },
  canHitNext: { type: Boolean, default: false },
  previewKind: { type: String, default: "" },
  pdfHighlights: { type: Array, default: () => [] },
  diffItems: { type: Array, default: () => [] },
  activeDiffId: { type: [String, Number], default: null },
  pdfCaption: { type: String, default: "" },
  imageSrc: { type: String, default: "" },
  highlightHtml: { type: Function, required: true },
  diffClassForSide: { type: Function, required: true },
  diffActiveForPara: { type: Function, default: () => false },
  inlineDiffForPara: { type: Function, default: () => null },
  paraHitState: { type: Function, required: true },
  docDisplayTitle: { type: Function, required: true },
  hitPage: { type: Function, required: true },
  highlightSnippet: { type: Function, required: true },
  allowPick: { type: Boolean, default: true },
});

const emit = defineEmits([
  "pick",
  "open-pdf",
  "scroll-ref",
  "prev-hit",
  "next-hit",
  "update:pdfPage",
]);

const { t } = useI18n();

const pdfNumPages = ref(1);

const panelClass = computed(() =>
  props.isBaseline
    ? "doc-panel--baseline"
    : props.isSearchTarget
      ? "doc-panel--target"
      : "doc-panel--extra"
);

const showsPdfPreview = computed(
  () => props.previewKind === PREVIEW_KIND.PDF && Boolean(props.pdfSrc)
);

const showsImagePreview = computed(
  () => props.previewKind === PREVIEW_KIND.IMAGE && Boolean(props.imageSrc)
);

const showsHtmlPreview = computed(
  () => props.previewKind === PREVIEW_KIND.HTML && Boolean(props.imageSrc)
);

const showsExtractedText = computed(
  () =>
    !showsPdfPreview.value &&
    !showsImagePreview.value &&
    !showsHtmlPreview.value
);

function onPdfReady({ numPages }) {
  pdfNumPages.value = Math.max(1, Number(numPages) || 1);
}

function goPdfPage(delta) {
  const next = (props.pdfPage || 1) + delta;
  if (next >= 1 && next <= pdfNumPages.value) {
    emit("update:pdfPage", next);
  }
}
</script>

<template>
  <section class="doc-panel" :class="panelClass">
    <header class="doc-panel-head">
      <div class="doc-panel-head-main">
        <span
          class="doc-panel-badge"
          :class="{ 'doc-panel-badge--target': isSearchTarget && !isBaseline }"
        >
          {{ roleLabel }}
        </span>
        <n-text v-if="doc" class="doc-panel-name" :title="doc.file_name">
          {{ docDisplayTitle(doc) }}
        </n-text>
        <n-text v-else depth="3" class="doc-panel-placeholder">{{ t("compare.notSelected") }}</n-text>
      </div>
      <n-space :size="7">
        <n-space
          v-if="showsPdfPreview && pdfNumPages > 1"
          :size="5"
          align="center"
          class="doc-panel-page-nav"
        >
          <n-button size="tiny" quaternary :disabled="pdfPage <= 1" @click="goPdfPage(-1)">
            {{ t("compare.prevPage") }}
          </n-button>
          <n-text depth="3" class="doc-panel-page-label">
            {{ t("compare.pageNav", { page: pdfPage, total: pdfNumPages }) }}
          </n-text>
          <n-button
            size="tiny"
            quaternary
            :disabled="pdfPage >= pdfNumPages"
            @click="goPdfPage(1)"
          >
            {{ t("compare.nextPage") }}
          </n-button>
        </n-space>
        <n-button v-if="allowPick" size="tiny" secondary @click="$emit('pick', columnIndex)">
          <template #icon>
            <n-icon :component="FolderOpenOutline" />
          </template>
          {{ t("compare.pick") }}
        </n-button>
        <n-button v-if="doc" size="tiny" quaternary @click="$emit('open-pdf', doc)">
          <template #icon>
            <n-icon :component="OpenOutline" />
          </template>
          {{ t("compare.original") }}
        </n-button>
      </n-space>
    </header>
    <div class="doc-panel-preview">
      <div v-if="showsPdfPreview" class="pdf-preview-wrap">
        <ComparePdfPreview
          :key="`pdf-col-${columnIndex}-${pdfSrc}`"
          :src="pdfSrc.split('#')[0]"
          :page="pdfPage"
          :external-loading="loading"
          :highlights="pdfHighlights"
          :diff-items="diffItems"
          :diff-side="diffSide"
          :active-diff-id="activeDiffId"
          :caption="pdfCaption"
          @ready="onPdfReady"
          @page-change="(page) => emit('update:pdfPage', page)"
        />
        <div
          v-if="isSearchTarget && activeHit && searchHits.length"
          class="pdf-hit-bar"
        >
          <n-space align="center" :size="7" class="pdf-hit-nav">
            <n-button size="tiny" quaternary :disabled="!canHitPrev" @click="$emit('prev-hit')">
              <template #icon>
                <n-icon :component="ChevronUpOutline" />
              </template>
            </n-button>
            <n-text depth="3">{{ hitNavLabel }}</n-text>
            <n-button size="tiny" quaternary :disabled="!canHitNext" @click="$emit('next-hit')">
              <template #icon>
                <n-icon :component="ChevronDownOutline" />
              </template>
            </n-button>
          </n-space>
          <n-tag size="small" type="warning" :bordered="false">
            {{ t("compare.page", { page: hitPage(activeHit) }) }}
          </n-tag>
          <span class="pdf-hit-snippet" v-html="highlightSnippet(activeHit.snippet)" />
        </div>
      </div>
      <n-spin v-else :show="loading" class="preview-spin platform-local-spin" local>
        <div v-if="showsImagePreview" class="image-preview-wrap">
          <img :src="imageSrc" :alt="docDisplayTitle(doc)" class="image-preview" />
        </div>
        <iframe
          v-else-if="showsHtmlPreview"
          :key="`html-col-${columnIndex}-${imageSrc}`"
          :src="imageSrc"
          class="pdf-frame"
          sandbox="allow-same-origin"
          :title="t('compare.previewTitle', { role: roleLabel })"
        />
        <template v-else-if="showsExtractedText">
          <pre v-if="plainPreview" class="plain-preview">{{ plainPreview }}</pre>
          <div
            v-else-if="doc && !loading"
            :ref="(el) => $emit('scroll-ref', { el, index: columnIndex })"
            class="doc-scroll"
          >
            <template v-if="paragraphs.length">
              <div
                v-for="p in paragraphs"
                :key="`col-${columnIndex}-p-${p.block_index ?? p.index}`"
                class="para-block"
                :data-block-index="p.block_index ?? p.index"
                :class="{
                  'para-search-hit': isSearchTarget && paraHitState(p.text).isHit,
                  'para-search-hit--active':
                    isSearchTarget && paraHitState(p.text).isActive,
                  'para-diff-active': diffActiveForPara(diffSide, p),
                  'para-diff-delete': diffClassForSide(diffSide, p) === 'hl-delete',
                  'para-diff-add': diffClassForSide(diffSide, p) === 'hl-add',
                  'para-diff-modify': diffClassForSide(diffSide, p) === 'hl-modify'}"
              >
                <n-text depth="3" class="page-label">
                  {{ t("compare.page", { page: p.page }) }}
                  <span v-if="p.bbox" class="bbox-hint">{{ t("compare.layoutBlock") }}</span>
                </n-text>
                <div
                  class="para-text"
                  v-html="
                    highlightHtml(p.text, {
                      diffClass:
                        diffSide !== 'none' ? diffClassForSide(diffSide, p) : null,
                      inlineDiff:
                        diffSide !== 'none' ? inlineDiffForPara(diffSide, p) : null,
                      searchActive:
                        isSearchTarget &&
                        (paraHitState(p.text).isHit || paraHitState(p.text).isActive),
                      hitSnippet:
                        isSearchTarget && paraHitState(p.text).isActive && activeHit
                          ? activeHit.snippet
                          : null})
                  "
                />
              </div>
            </template>
            <n-text v-else depth="3" class="empty-hint">
              {{ content?.warning || t("compare.noTextContent") }}
            </n-text>
          </div>
          <n-text v-else-if="!doc" depth="3" class="empty-hint">{{ t("compare.pickDoc") }}</n-text>
        </template>
      </n-spin>
    </div>
  </section>
</template>

<style scoped>
.doc-panel {
  min-height: 0;
  height: 100%;
  max-height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--platform-surface, #fff);
  border: 1px solid var(--platform-border, rgba(15, 23, 42, 0.08));
  border-radius: var(--platform-radius-sm, 10px);
  box-shadow: var(--platform-shadow);
  overflow: hidden;
}
.doc-panel--baseline {
  border-top: 2px solid #60a5fa;
}
.doc-panel--target {
  border-top: 2px solid var(--platform-accent);
}
.doc-panel--extra {
  border-top: 2px solid #94a3b8;
}
.doc-panel-head {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--platform-border, rgba(15, 23, 42, 0.06));
  background: rgba(248, 250, 252, 0.9);
}
.doc-panel-head-main {
  min-width: 0;
  flex: 1;
  display: flex;
  align-items: center;
  gap: 10px;
}
.doc-panel-badge {
  flex-shrink: 0;
  font-size: var(--platform-font-size-base);
  padding: 2px 10px;
  border-radius: 5px;
  background: rgba(96, 165, 250, 0.15);
  color: var(--platform-accent);
}
.doc-panel-badge--target {
  background: var(--platform-accent-muted);
  color: var(--platform-accent-pressed);
}
.doc-panel-name {
  font-size: 16px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.doc-panel-placeholder {
  font-size: var(--platform-font-size-base);
}
.doc-panel-page-nav {
  flex-shrink: 0;
}
.doc-panel-page-label {
  font-size: var(--platform-font-size-base);
  white-space: nowrap;
}
.doc-panel-preview {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #e8eaed;
}
.preview-spin {
  flex: 1;
  min-height: 0;
  width: 100%;
  display: flex;
  flex-direction: column;
}
.preview-spin :deep(.n-spin-container),
.preview-spin :deep(.n-spin-content) {
  flex: 1;
  min-height: 0;
  height: 100%;
  width: 100%;
  display: flex;
  flex-direction: column;
}
.preview-spin :deep(.n-spin-content) > * {
  flex: 1;
  min-height: 0;
}
.pdf-preview-wrap {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.image-preview-wrap {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding: 10px;
  background: #fff;
}
.image-preview {
  display: block;
  width: auto;
  height: auto;
  max-width: none;
  object-fit: none;
  image-rendering: high-quality;
}
.pdf-frame {
  flex: 1;
  min-height: 0;
  width: 100%;
  height: 100%;
  border: none;
  background: #fff;
  display: block;
}
.pdf-hit-bar {
  flex-shrink: 0;
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 7px 12px;
  font-size: 14px;
  line-height: 1.45;
  max-height: 86px;
  overflow-y: auto;
  background: #fff;
  border-top: 1px solid var(--platform-border, rgba(15, 23, 42, 0.08));
}
.pdf-hit-nav {
  flex-shrink: 0;
}
.pdf-hit-snippet {
  flex: 1;
  min-width: 0;
  word-break: break-word;
}
.pdf-hit-snippet :deep(mark.hl-search) {
  background: color-mix(in srgb, var(--platform-accent) 35%, transparent);
  border-radius: 2px;
  padding: 0 2px;
}
.plain-preview,
.doc-scroll {
  flex: 1;
  min-height: 0;
  margin: 0;
  overflow: auto;
  background: #fff;
}
.plain-preview {
  padding: 14px 17px;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 16px;
  line-height: 1.55;
  font-family: inherit;
}
.empty-hint {
  padding: 38px 19px;
  text-align: center;
  display: block;
  background: #fff;
}
.doc-scroll {
  padding: 10px 12px;
}
.para-block {
  margin-bottom: 17px;
  padding: 10px 12px;
  border-radius: 7px;
  border: 1px solid transparent;
}
.para-block.para-search-hit {
  border-color: color-mix(in srgb, var(--platform-accent) 45%, transparent);
  background: color-mix(in srgb, var(--platform-accent) 8%, transparent);
}
.para-block.para-search-hit--active {
  border-color: color-mix(in srgb, var(--platform-accent) 85%, transparent);
  background: color-mix(in srgb, var(--platform-accent) 16%, transparent);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--platform-accent) 20%, transparent);
}
.para-block.para-diff-active {
  border-color: rgba(234, 179, 8, 0.85);
  background: rgba(234, 179, 8, 0.12);
  box-shadow: 0 0 0 2px rgba(234, 179, 8, 0.25);
}
.para-block.para-diff-delete {
  border-color: rgba(239, 68, 68, 0.35);
}
.para-block.para-diff-add {
  border-color: rgba(34, 197, 94, 0.35);
}
.para-block.para-diff-modify {
  border-color: rgba(234, 179, 8, 0.35);
}
.bbox-hint {
  opacity: 0.65;
  font-size: 12px;
}
.para-block.para-flash {
  animation: para-flash 2s ease-out;
}
@keyframes para-flash {
  0%,
  15% {
    box-shadow: 0 0 0 4px color-mix(in srgb, var(--platform-accent) 55%, transparent);
  }
  100% {
    box-shadow: none;
  }
}
.page-label {
  font-size: 13px;
  display: block;
  margin-bottom: 5px;
}
.para-text {
  font-size: 16px;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
}
.para-text :deep(.hl-delete) {
  background: rgba(239, 68, 68, 0.22);
  border-radius: 2px;
}
.para-text :deep(.hl-add) {
  background: rgba(34, 197, 94, 0.22);
  border-radius: 2px;
}
.para-text :deep(.hl-modify) {
  background: rgba(234, 179, 8, 0.28);
  border-radius: 2px;
}
.para-text :deep(mark.hl-search) {
  background: color-mix(in srgb, var(--platform-accent) 35%, transparent);
  color: inherit;
  padding: 0 2px;
  border-radius: 2px;
}
.para-text :deep(mark.hl-search--active) {
  background: color-mix(in srgb, var(--platform-accent) 62%, transparent);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--platform-accent) 45%, transparent);
}
</style>
