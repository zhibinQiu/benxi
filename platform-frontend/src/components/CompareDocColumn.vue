<script setup>
import { computed } from "vue";
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
import ComparePdfPreview from "./ComparePdfPreview.vue";
import { PREVIEW_KIND } from "../utils/documentPreview.js";

const props = defineProps({
  columnIndex: { type: Number, required: true },
  doc: { type: Object, default: null },
  content: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  comparing: { type: Boolean, default: false },
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
  allowPick: { type: Boolean, default: true }});

defineEmits(["pick", "open-pdf", "scroll-ref", "prev-hit", "next-hit"]);

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
        <n-text v-else depth="3" class="doc-panel-placeholder">未选择</n-text>
      </div>
      <n-space :size="6">
        <n-button v-if="allowPick" size="tiny" secondary @click="$emit('pick', columnIndex)">
          <template #icon>
            <n-icon :component="FolderOpenOutline" />
          </template>
          选择
        </n-button>
        <n-button v-if="doc" size="tiny" quaternary @click="$emit('open-pdf', doc)">
          <template #icon>
            <n-icon :component="OpenOutline" />
          </template>
          原文
        </n-button>
      </n-space>
    </header>
    <div class="doc-panel-preview">
      <n-spin :show="loading || comparing" class="preview-spin">
        <div v-if="showsPdfPreview" class="pdf-preview-wrap">
          <ComparePdfPreview
            :key="`pdf-col-${columnIndex}-${pdfSrc}-${pdfPage}`"
            :src="pdfSrc.split('#')[0]"
            :page="pdfPage"
            :highlights="pdfHighlights"
            :diff-items="diffItems"
            :diff-side="diffSide"
            :active-diff-id="activeDiffId"
            :caption="pdfCaption"
          />
          <div
            v-if="isSearchTarget && activeHit && searchHits.length"
            class="pdf-hit-bar"
          >
            <n-space align="center" :size="6" class="pdf-hit-nav">
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
              第 {{ hitPage(activeHit) }} 页
            </n-tag>
            <span class="pdf-hit-snippet" v-html="highlightSnippet(activeHit.snippet)" />
          </div>
        </div>
        <div v-else-if="showsImagePreview" class="image-preview-wrap">
          <img :src="imageSrc" :alt="docDisplayTitle(doc)" class="image-preview" />
        </div>
        <iframe
          v-else-if="showsHtmlPreview"
          :key="`html-col-${columnIndex}-${imageSrc}`"
          :src="imageSrc"
          class="pdf-frame"
          sandbox="allow-same-origin"
          :title="`${roleLabel}预览`"
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
                  第 {{ p.page }} 页
                  <span v-if="p.bbox" class="bbox-hint"> · 版面块</span>
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
              {{ content?.warning || "暂无文本内容" }}
            </n-text>
          </div>
          <n-text v-else-if="!doc" depth="3" class="empty-hint">请选择文档</n-text>
        </template>
      </n-spin>
    </div>
  </section>
</template>

<style scoped>
.doc-panel {
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--platform-surface, #fff);
  border: 1px solid var(--platform-border, rgba(15, 23, 42, 0.08));
  border-radius: var(--platform-radius-sm, 8px);
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
  gap: 8px;
  padding: 8px 10px;
  border-bottom: 1px solid var(--platform-border, rgba(15, 23, 42, 0.06));
  background: rgba(248, 250, 252, 0.9);
}
.doc-panel-head-main {
  min-width: 0;
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
}
.doc-panel-badge {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(96, 165, 250, 0.15);
  color: #2563eb;
}
.doc-panel-badge--target {
  background: var(--platform-accent-muted);
  color: var(--platform-accent-pressed);
}
.doc-panel-name {
  font-size: 13px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.doc-panel-placeholder {
  font-size: 12px;
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
.preview-spin :deep(.n-spin-body),
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
  padding: 8px;
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
  background: #525659;
  display: block;
}
.pdf-hit-bar {
  flex-shrink: 0;
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 6px 10px;
  font-size: 12px;
  line-height: 1.45;
  max-height: 72px;
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
  background: rgba(139, 92, 246, 0.35);
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
  padding: 12px 14px;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 13px;
  line-height: 1.55;
  font-family: inherit;
}
.empty-hint {
  padding: 32px 16px;
  text-align: center;
  display: block;
  background: #fff;
}
.doc-scroll {
  padding: 8px 10px;
}
.para-block {
  margin-bottom: 14px;
  padding: 8px 10px;
  border-radius: 6px;
  border: 1px solid transparent;
}
.para-block.para-search-hit {
  border-color: rgba(139, 92, 246, 0.45);
  background: rgba(139, 92, 246, 0.08);
}
.para-block.para-search-hit--active {
  border-color: rgba(139, 92, 246, 0.85);
  background: rgba(139, 92, 246, 0.16);
  box-shadow: 0 0 0 2px rgba(139, 92, 246, 0.2);
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
  font-size: 10px;
}
.para-block.para-flash {
  animation: para-flash 2s ease-out;
}
@keyframes para-flash {
  0%,
  15% {
    box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.55);
  }
  100% {
    box-shadow: none;
  }
}
.page-label {
  font-size: 11px;
  display: block;
  margin-bottom: 4px;
}
.para-text {
  font-size: 13px;
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
  background: rgba(139, 92, 246, 0.35);
  color: inherit;
  padding: 0 2px;
  border-radius: 2px;
}
.para-text :deep(mark.hl-search--active) {
  background: rgba(139, 92, 246, 0.62);
  box-shadow: 0 0 0 1px rgba(139, 92, 246, 0.45);
}
</style>
