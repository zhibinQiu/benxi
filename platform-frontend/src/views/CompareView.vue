<script setup>
import { computed, h, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import {
  NAlert,
  NButton,
  NCard,
  NDataTable,
  NIcon,
  NInput,
  NModal,
  NSpace,
  NSpin,
  NTag,
  NText,
  NCheckbox,
  useMessage,
} from "naive-ui";
import {
  ArrowBackOutline,
  ChevronDownOutline,
  ChevronUpOutline,
  GitCompareOutline,
  SearchOutline,
  FolderOpenOutline,
  OpenOutline,
  RefreshOutline,
} from "@vicons/ionicons5";
import {
  createCompareJob,
  waitCompareJob,
  fetchCompareDocuments,
  fetchCompareDocumentContent,
  fetchCompareDocumentFileBlob,
  getCompareDocumentDownload,
  searchCompareDocuments,
} from "../api/client";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";

const router = useRouter();
const message = useMessage();

const leftDoc = ref(null);
const rightDoc = ref(null);
const job = ref(null);
const comparing = ref(false);
const searchQuery = ref("");
const searchHits = ref([]);
const searching = ref(false);
const syncKnowflow = ref(true);
const fieldMatch = ref(true);
const activeDiffId = ref(null);
const activeHitIndex = ref(-1);
const hitListRef = ref(null);
const leftPdfBaseUrl = ref(null);
const rightPdfBaseUrl = ref(null);
const rightPdfPage = ref(1);
const rightDocScrollRef = ref(null);

const showPicker = ref(false);
const pickerSide = ref("left");
const libraryItems = ref([]);
const libraryLoading = ref(false);
const libraryKeyword = ref("");
const libraryPage = ref(1);

const diffTypeLabel = {
  add: "新增",
  delete: "删除",
  modify: "修改",
};

const diffTypeClass = {
  add: "hl-add",
  delete: "hl-delete",
  modify: "hl-modify",
};

const canCompare = computed(
  () =>
    leftDoc.value &&
    rightDoc.value &&
    leftDoc.value.id !== rightDoc.value.id &&
    !comparing.value
);

const canSearch = computed(
  () => rightDoc.value && searchQuery.value.trim() && !searching.value
);

const leftContent = ref(null);
const rightContent = ref(null);
const leftLoading = ref(false);
const rightLoading = ref(false);

function revokeBlobUrl(url) {
  if (url && String(url).startsWith("blob:")) {
    URL.revokeObjectURL(url);
  }
}

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onCompareKeydown);
  revokeBlobUrl(leftContent.value?.preview_url);
  revokeBlobUrl(rightContent.value?.preview_url);
  leftPdfBaseUrl.value = null;
  rightPdfBaseUrl.value = null;
});

const leftPdfSrc = computed(() => pdfSrcWithPage(leftPdfBaseUrl.value, 1));
const rightPdfSrc = computed(() =>
  pdfSrcWithPage(rightPdfBaseUrl.value, rightPdfPage.value)
);

const activeHit = computed(() =>
  activeHitIndex.value >= 0 ? searchHits.value[activeHitIndex.value] : null
);

const hitNavLabel = computed(() => {
  if (!searchHits.value.length || activeHitIndex.value < 0) return "";
  return `${activeHitIndex.value + 1} / ${searchHits.value.length}`;
});

const canHitPrev = computed(
  () => searchHits.value.length > 0 && activeHitIndex.value > 0
);
const canHitNext = computed(
  () =>
    searchHits.value.length > 0 &&
    activeHitIndex.value >= 0 &&
    activeHitIndex.value < searchHits.value.length - 1
);

function pdfSrcWithPage(base, page) {
  if (!base) return "";
  const root = String(base).split("#")[0];
  const p = Number(page);
  return p > 1 ? `${root}#page=${p}` : root;
}

function hitPage(hit) {
  const a = hit?.anchor_json || {};
  const p = a.page ?? a.page_num;
  const n = parseInt(p, 10);
  return Number.isFinite(n) && n > 0 ? n : 1;
}

function paraMatchesHit(paraText, hit) {
  const sn = (hit?.snippet || "").trim();
  const t = (paraText || "").trim();
  if (!sn || !t) return false;
  return t === sn || t.includes(sn) || sn.includes(t);
}

function paraHitState(paraText) {
  let isHit = false;
  let isActive = false;
  searchHits.value.forEach((hit, i) => {
    if (paraMatchesHit(paraText, hit)) {
      isHit = true;
      if (i === activeHitIndex.value) isActive = true;
    }
  });
  return { isHit, isActive };
}

function highlightSnippet(text) {
  return highlightHtml(text || "", { searchActive: true });
}

function buildParagraphsFromContent(content) {
  if (!content) return [];
  const paras = [];
  const pages = content.pages || [];
  for (const page of pages) {
    const text = page.text || "";
    let chunks = text.split(/\n\s*\n+/).map((p) => p.trim()).filter(Boolean);
    if (!chunks.length && text.trim()) chunks = [text.trim()];
    for (const chunk of chunks) {
      paras.push({ page: page.page || 1, index: paras.length, text: chunk });
    }
  }
  if (!paras.length && content.full_text?.trim()) {
    const chunks = content.full_text
      .split(/\n\s*\n+/)
      .map((p) => p.trim())
      .filter(Boolean);
    for (const chunk of chunks) {
      paras.push({ page: 1, index: paras.length, text: chunk });
    }
  }
  return paras;
}

const leftHasPdf = computed(() => isPdfFileName(leftContent.value?.file_name));
const rightHasPdf = computed(() => isPdfFileName(rightContent.value?.file_name));
const leftPlainPreview = computed(() => {
  if (!leftContent.value || leftHasPdf.value) return "";
  if (leftParagraphs.value.length) return "";
  return leftContent.value.full_text?.trim() || "";
});
const rightPlainPreview = computed(() => {
  if (!rightContent.value || rightHasPdf.value) return "";
  if (rightParagraphs.value.length) return "";
  return rightContent.value.full_text?.trim() || "";
});

const diffItems = computed(() => {
  if (!job.value?.diff_items) return [];
  const leftId = job.value.left_document_id;
  const rightId = job.value.right_document_id;
  return job.value.diff_items.filter(
    (d) => d.doc_a_id === leftId && d.doc_b_id === rightId
  );
});

const searchTerms = computed(() => {
  const q = searchQuery.value.trim().toLowerCase();
  if (!q) return [];
  return q.split(/\s+/).filter((t) => t.length >= 2 && !t.includes(":") && !t.includes("："));
});

function escapeHtml(s) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function escapeRegExp(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function snippetHighlightParts(snippet) {
  const sn = (snippet || "").trim();
  if (!sn) return [];
  if (sn.length <= 120) return [sn];
  return [sn.slice(0, 120), sn.slice(0, 60)];
}

function highlightHtml(text, { diffClass, searchActive, hitSnippet } = {}) {
  let html = escapeHtml(text || "");
  if (!html) return "<span class='para-empty'>（空段落）</span>";
  if (diffClass) {
    html = `<span class="${diffClass}">${html}</span>`;
  }
  if (searchActive) {
    let marked = false;
    if (hitSnippet) {
      for (const part of snippetHighlightParts(hitSnippet)) {
        if (!part || part.length < 4) continue;
        const idx = (text || "").indexOf(part);
        if (idx >= 0) {
          const re = new RegExp(escapeRegExp(part));
          html = html.replace(re, '<mark class="hl-search hl-search--active">$&</mark>');
          marked = true;
          break;
        }
      }
    }
    if (!marked && searchTerms.value.length) {
      for (const term of searchTerms.value) {
        const re = new RegExp(`(${escapeRegExp(term)})`, "gi");
        html = html.replace(re, '<mark class="hl-search">$1</mark>');
      }
    }
  }
  return html;
}

function syncContentFromJob() {
  const docs = job.value?.payload?.documents || {};
  if (leftDoc.value?.id && docs[leftDoc.value.id] && !leftHasPdf.value) {
    const prev = leftContent.value || {};
    leftContent.value = {
      ...prev,
      ...docs[leftDoc.value.id],
      preview_url: prev.preview_url,
    };
  }
  if (rightDoc.value?.id && docs[rightDoc.value.id] && !rightHasPdf.value) {
    const prev = rightContent.value || {};
    rightContent.value = {
      ...prev,
      ...docs[rightDoc.value.id],
      preview_url: prev.preview_url,
    };
  }
}

async function hydrateDocSide(doc, side) {
  if (!doc?.id) return;
  const loadingRef = side === "left" ? leftLoading : rightLoading;
  const contentRef = side === "left" ? leftContent : rightContent;
  revokeBlobUrl(contentRef.value?.preview_url);
  loadingRef.value = true;
  try {
    const fileName = doc.file_name || "";
    if (isPdfFileName(fileName)) {
      let preview_url = null;
      try {
        const blob = await fetchCompareDocumentFileBlob(doc.id);
        preview_url = URL.createObjectURL(blob);
      } catch {
        const dl = await getCompareDocumentDownload(doc.id).catch(() => null);
        preview_url = dl?.download_url || null;
      }
      const base = preview_url ? String(preview_url).split("#")[0] : null;
      if (side === "left") {
        leftPdfBaseUrl.value = base;
      } else {
        rightPdfBaseUrl.value = base;
        rightPdfPage.value = 1;
      }
      contentRef.value = {
        file_name: fileName,
        preview_url: base,
        pages: [],
        full_text: "",
      };
      return;
    }
    if (side === "left") leftPdfBaseUrl.value = null;
    else {
      rightPdfBaseUrl.value = null;
      rightPdfPage.value = 1;
    }
    const content = await fetchCompareDocumentContent(doc.id);
    contentRef.value = {
      pages: content.pages || [],
      full_text: content.full_text || "",
      file_name: content.file_name || fileName,
      parse_quality: content.parse_quality,
      warning: content.warning,
      preview_url: null,
    };
  } catch (e) {
    message.error(e.message);
    contentRef.value = null;
  } finally {
    loadingRef.value = false;
  }
}

function isPdfFileName(name) {
  return String(name || "").toLowerCase().endsWith(".pdf");
}

function diffClassForPara(side, paraText) {
  const t = (paraText || "").trim();
  if (!t || !diffItems.value.length) return null;
  for (const d of diffItems.value) {
    const left = (d.text_left || "").trim();
    const right = (d.text_right || "").trim();
    if (side === "left") {
      if (d.diff_type === "delete" && left && (left === t || left.includes(t) || t.includes(left))) {
        return diffTypeClass.delete;
      }
      if (d.diff_type === "modify" && left && (left === t || left.includes(t))) {
        return diffTypeClass.modify;
      }
    } else {
      if (d.diff_type === "add" && right && (right === t || right.includes(t) || t.includes(right))) {
        return diffTypeClass.add;
      }
      if (d.diff_type === "modify" && right && (right === t || right.includes(t))) {
        return diffTypeClass.modify;
      }
    }
  }
  return null;
}

const leftParagraphs = computed(() => buildParagraphsFromContent(leftContent.value));
const rightParagraphs = computed(() => buildParagraphsFromContent(rightContent.value));

const libraryColumns = [
  { title: "标题", key: "title", ellipsis: { tooltip: true } },
  { title: "文件名", key: "file_name", width: 180, ellipsis: { tooltip: true } },
  {
    title: "操作",
    key: "actions",
    width: 72,
    render: (row) =>
      h(
        NButton,
        { text: true, type: "primary", size: "small", onClick: () => selectDoc(row) },
        () => "选择"
      ),
  },
];

async function loadLibraryDocs() {
  libraryLoading.value = true;
  try {
    const data = await fetchCompareDocuments({
      page: libraryPage.value,
      page_size: 20,
      keyword: libraryKeyword.value || undefined,
    });
    libraryItems.value = data.items || [];
  } catch (e) {
    message.error(e.message);
  } finally {
    libraryLoading.value = false;
  }
}

function openPicker(side) {
  pickerSide.value = side;
  showPicker.value = true;
  libraryPage.value = 1;
  loadLibraryDocs();
}

function selectDoc(row) {
  if (pickerSide.value === "left") {
    leftDoc.value = row;
    hydrateDocSide(row, "left");
  } else {
    rightDoc.value = row;
    hydrateDocSide(row, "right");
  }
  showPicker.value = false;
  job.value = null;
  searchHits.value = [];
  activeHitIndex.value = -1;
}

async function openOriginalPdf(doc) {
  if (!doc?.id) return;
  try {
    const data = await getCompareDocumentDownload(doc.id);
    if (data?.download_url) window.open(data.download_url, "_blank");
  } catch (e) {
    message.error(e.message);
  }
}

async function runCompare() {
  if (!leftDoc.value || !rightDoc.value) return;
  comparing.value = true;
  job.value = null;
  searchHits.value = [];
  try {
    const created = await createCompareJob({
      leftDocumentId: leftDoc.value.id,
      rightDocumentId: rightDoc.value.id,
      syncKnowflow: syncKnowflow.value,
    });
    job.value =
      created?.status === "pending" || created?.status === "running"
        ? await waitCompareJob(created.id)
        : created;
    if (job.value.status === "failed") {
      message.error(job.value.error_message || "比对失败");
    } else {
      syncContentFromJob();
      message.success("段落差异分析完成");
    }
  } catch (e) {
    message.error(e.message);
  } finally {
    comparing.value = false;
  }
}

async function ensureRightSearchIndex() {
  if (!rightDoc.value?.id || rightParagraphs.value.length) return;
  try {
    const content = await fetchCompareDocumentContent(rightDoc.value.id);
    if (rightContent.value) {
      rightContent.value = {
        ...rightContent.value,
        pages: content.pages || [],
        full_text: content.full_text || "",
      };
    }
  } catch {
    /* 仅用于定位跳转，不影响预览 */
  }
}

function findParaIndexByHit(hit) {
  const paras = rightParagraphs.value;
  for (let i = 0; i < paras.length; i++) {
    if (paraMatchesHit(paras[i].text, hit)) return i;
  }
  const page = hitPage(hit);
  const byPage = paras.findIndex((p) => p.page === page);
  return byPage >= 0 ? byPage : 0;
}

async function jumpToHit(hit, index) {
  if (!hit) return;
  activeHitIndex.value = index;
  await nextTick();
  scrollActiveHitIntoAside();

  if (rightHasPdf.value) {
    rightPdfPage.value = hitPage(hit);
    return;
  }

  const idx = findParaIndexByHit(hit);
  const root = rightDocScrollRef.value;
  if (!root || idx < 0) return;
  const target = root.querySelectorAll(".para-block")[idx];
  if (target) {
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    target.classList.add("para-flash");
    window.setTimeout(() => target.classList.remove("para-flash"), 2200);
  }
}

function scrollActiveHitIntoAside() {
  const root = hitListRef.value;
  if (!root || activeHitIndex.value < 0) return;
  const el = root.querySelectorAll(".hit-item")[activeHitIndex.value];
  el?.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function goPrevHit() {
  if (!searchHits.value.length) return;
  const idx =
    activeHitIndex.value <= 0
      ? 0
      : activeHitIndex.value - 1;
  jumpToHit(searchHits.value[idx], idx);
}

function goNextHit() {
  if (!searchHits.value.length) return;
  const idx =
    activeHitIndex.value < 0
      ? 0
      : Math.min(activeHitIndex.value + 1, searchHits.value.length - 1);
  jumpToHit(searchHits.value[idx], idx);
}

function onSearchKeydown(e) {
  if (!searchHits.value.length) return;
  if (e.key === "ArrowDown" || (e.key === "Enter" && e.shiftKey)) {
    e.preventDefault();
    goNextHit();
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    goPrevHit();
  }
}

function onCompareKeydown(e) {
  if (e.target?.closest?.("input, textarea, [contenteditable=true]")) {
    if (e.key !== "F3") return;
  }
  if (e.key === "F3") {
    e.preventDefault();
    if (e.shiftKey) goPrevHit();
    else goNextHit();
  }
}

onMounted(() => {
  window.addEventListener("keydown", onCompareKeydown);
});

async function runSearch() {
  if (!rightDoc.value?.id || !searchQuery.value.trim()) return;
  searching.value = true;
  activeHitIndex.value = -1;
  try {
    await ensureRightSearchIndex();
    searchHits.value = await searchCompareDocuments({
      rightDocumentId: rightDoc.value.id,
      query: searchQuery.value.trim(),
      syncKnowflow: syncKnowflow.value,
      fieldMatch: fieldMatch.value,
    });
    if (!searchHits.value.length) {
      message.info("未找到匹配内容，可换关键词或关闭字段匹配");
      return;
    }
    await jumpToHit(searchHits.value[0], 0);
  } catch (e) {
    message.error(e.message);
  } finally {
    searching.value = false;
  }
}

function onHitClick(hit, index) {
  jumpToHit(hit, index);
}

function onDiffClick(d) {
  activeDiffId.value = d.id;
}
</script>

<template>
  <FeatureSubsystemShell fill>
    <template #extra>
      <n-space :size="8" align="center" wrap>
        <n-checkbox v-model:checked="syncKnowflow" size="small">向量检索</n-checkbox>
        <n-button
          size="small"
          secondary
          :disabled="!canCompare"
          :loading="comparing"
          @click="runCompare"
        >
          <template #icon>
            <n-icon :component="RefreshOutline" />
          </template>
          段落差异
        </n-button>
      </n-space>
    </template>

    <div class="compare-workspace">
      <div class="compare-columns">
        <section class="doc-panel doc-panel--left">
          <header class="doc-panel-head">
            <div class="doc-panel-head-main">
              <span class="doc-panel-badge">参照</span>
              <n-text v-if="leftDoc" class="doc-panel-name" :title="leftDoc.file_name">
                {{ leftDoc.title }}
              </n-text>
              <n-text v-else depth="3" class="doc-panel-placeholder">未选择文档</n-text>
            </div>
            <n-space :size="6">
              <n-button size="tiny" secondary @click="openPicker('left')">
                <template #icon>
                  <n-icon :component="FolderOpenOutline" />
                </template>
                选择
              </n-button>
              <n-button
                v-if="leftDoc"
                size="tiny"
                quaternary
                @click="openOriginalPdf(leftDoc)"
              >
                <template #icon>
                  <n-icon :component="OpenOutline" />
                </template>
                原文
              </n-button>
            </n-space>
          </header>
          <div class="doc-panel-preview">
            <n-spin :show="leftLoading || comparing" class="preview-spin">
              <template v-if="leftHasPdf">
                <div v-if="leftPdfSrc" class="pdf-preview-wrap">
                  <iframe :src="leftPdfSrc" class="pdf-frame" title="左侧文档预览" />
                </div>
                <n-text v-else-if="leftDoc && !leftLoading" depth="3" class="empty-hint">
                  预览加载失败，请点击「原文」
                </n-text>
              </template>
              <template v-else>
                <pre v-if="leftPlainPreview" class="plain-preview">{{ leftPlainPreview }}</pre>
                <div v-else-if="leftDoc && !leftLoading" class="doc-scroll">
                  <template v-if="leftParagraphs.length">
                    <div v-for="p in leftParagraphs" :key="'l-' + p.index" class="para-block">
                      <n-text depth="3" class="page-label">第 {{ p.page }} 页</n-text>
                      <div
                        class="para-text"
                        v-html="highlightHtml(p.text, { diffClass: diffClassForPara('left', p.text) })"
                      />
                    </div>
                  </template>
                  <n-text v-else depth="3" class="empty-hint">
                    {{ leftContent?.warning || "暂无文本内容" }}
                  </n-text>
                </div>
                <n-text v-else-if="!leftDoc" depth="3" class="empty-hint">请选择参照文档</n-text>
              </template>
            </n-spin>
          </div>
        </section>

        <section class="doc-panel doc-panel--right">
          <header class="doc-panel-head">
            <div class="doc-panel-head-main">
              <span class="doc-panel-badge doc-panel-badge--target">检索</span>
              <n-text v-if="rightDoc" class="doc-panel-name" :title="rightDoc.file_name">
                {{ rightDoc.title }}
              </n-text>
              <n-text v-else depth="3" class="doc-panel-placeholder">未选择文档</n-text>
            </div>
            <n-space :size="6">
              <n-button size="tiny" secondary @click="openPicker('right')">
                <template #icon>
                  <n-icon :component="FolderOpenOutline" />
                </template>
                选择
              </n-button>
              <n-button
                v-if="rightDoc"
                size="tiny"
                quaternary
                @click="openOriginalPdf(rightDoc)"
              >
                <template #icon>
                  <n-icon :component="OpenOutline" />
                </template>
                原文
              </n-button>
            </n-space>
          </header>
          <div class="doc-panel-search">
            <n-input
              v-model:value="searchQuery"
              size="small"
              placeholder="检索关键词，如：违约金、条款:责任"
              clearable
              :disabled="!rightDoc"
              @keyup.enter="runSearch"
              @keydown="onSearchKeydown"
            >
              <template #prefix>
                <n-icon :component="SearchOutline" />
              </template>
            </n-input>
            <n-button
              size="small"
              type="primary"
              :disabled="!canSearch"
              :loading="searching"
              @click="runSearch"
            >
              检索
            </n-button>
            <div v-if="searchHits.length" class="hit-nav">
              <n-button
                size="tiny"
                quaternary
                :disabled="!canHitPrev"
                title="上一个（↑）"
                @click="goPrevHit"
              >
                <template #icon>
                  <n-icon :component="ChevronUpOutline" />
                </template>
              </n-button>
              <n-text depth="2" class="hit-nav-label">{{ hitNavLabel }}</n-text>
              <n-button
                size="tiny"
                quaternary
                :disabled="!canHitNext"
                title="下一个（↓ / F3）"
                @click="goNextHit"
              >
                <template #icon>
                  <n-icon :component="ChevronDownOutline" />
                </template>
              </n-button>
            </div>
            <n-checkbox v-model:checked="fieldMatch" size="small">字段匹配</n-checkbox>
          </div>
          <div class="doc-panel-preview">
            <n-spin :show="rightLoading || comparing" class="preview-spin">
              <template v-if="rightHasPdf">
                <div v-if="rightPdfSrc" class="pdf-preview-wrap">
                  <iframe
                    :key="`right-pdf-p${rightPdfPage}`"
                    :src="rightPdfSrc"
                    class="pdf-frame"
                    title="右侧文档预览"
                  />
                  <div v-if="activeHit && searchHits.length" class="pdf-hit-bar">
                    <n-space align="center" :size="6" class="pdf-hit-nav">
                      <n-button size="tiny" quaternary :disabled="!canHitPrev" @click="goPrevHit">
                        <template #icon>
                          <n-icon :component="ChevronUpOutline" />
                        </template>
                      </n-button>
                      <n-text depth="3">{{ hitNavLabel }}</n-text>
                      <n-button size="tiny" quaternary :disabled="!canHitNext" @click="goNextHit">
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
                <n-text v-else-if="rightDoc && !rightLoading" depth="3" class="empty-hint">
                  预览加载失败，请点击「原文」
                </n-text>
              </template>
              <template v-else>
                <pre v-if="rightPlainPreview" class="plain-preview">{{ rightPlainPreview }}</pre>
                <div
                  v-else-if="rightDoc && !rightLoading"
                  ref="rightDocScrollRef"
                  class="doc-scroll"
                >
                  <template v-if="rightParagraphs.length">
                    <div
                      v-for="p in rightParagraphs"
                      :key="'r-' + p.index"
                      class="para-block"
                      :class="{
                        'para-search-hit': paraHitState(p.text).isHit,
                        'para-search-hit--active': paraHitState(p.text).isActive,
                      }"
                    >
                      <n-text depth="3" class="page-label">第 {{ p.page }} 页</n-text>
                      <div
                        class="para-text"
                        v-html="
                          highlightHtml(p.text, {
                            diffClass: diffClassForPara('right', p.text),
                            searchActive:
                              paraHitState(p.text).isHit || paraHitState(p.text).isActive,
                            hitSnippet:
                              paraHitState(p.text).isActive && activeHit
                                ? activeHit.snippet
                                : null,
                          })
                        "
                      />
                    </div>
                  </template>
                  <n-text v-else depth="3" class="empty-hint">
                    {{ rightContent?.warning || "暂无文本内容" }}
                  </n-text>
                </div>
                <n-text v-else-if="!rightDoc" depth="3" class="empty-hint">请选择检索目标</n-text>
              </template>
            </n-spin>
          </div>
        </section>
      </div>

      <aside
        v-if="searchHits.length || job?.status === 'done'"
        class="compare-aside"
      >
        <n-card
          v-if="job?.status === 'done'"
          size="small"
          title="差异列表"
          class="aside-card"
        >
          <n-text depth="3" class="aside-hint">
            共 {{ diffItems.length }} 处差异（相对左侧）
          </n-text>
          <div class="diff-list">
            <div
              v-for="d in diffItems"
              :key="d.id"
              class="diff-item"
              :class="{ active: activeDiffId === d.id }"
              @click="onDiffClick(d)"
            >
              <n-tag size="small" :bordered="false">{{ diffTypeLabel[d.diff_type] || d.diff_type }}</n-tag>
              <n-text class="diff-snippet" depth="2">
                {{ (d.text_right || d.text_left || "").slice(0, 120) }}
              </n-text>
            </div>
            <n-text v-if="!diffItems.length" depth="3">未发现段落级差异</n-text>
          </div>
        </n-card>

        <n-card v-if="searchHits.length" size="small" class="aside-card">
          <template #header>
            <n-space align="center" justify="space-between" style="width: 100%">
              <span>检索命中</span>
              <n-text v-if="hitNavLabel" depth="3" style="font-size: 12px">{{ hitNavLabel }}</n-text>
            </n-space>
          </template>
          <div ref="hitListRef" class="hit-list">
            <div
              v-for="(h, i) in searchHits"
              :key="h.id || `${h.document_id}-${i}`"
              class="hit-item"
              :class="{ active: activeHitIndex === i }"
              @click="onHitClick(h, i)"
            >
              <n-space align="center" :size="6">
                <n-tag size="tiny" type="info">{{
                  h.source === "knowflow" ? "向量" : "关键词"
                }}</n-tag>
                <n-tag v-if="hitPage(h) > 0" size="tiny" :bordered="false">P{{ hitPage(h) }}</n-tag>
                <n-text depth="3">得分 {{ h.score?.toFixed?.(2) ?? h.score }}</n-text>
              </n-space>
              <div class="hit-snippet" v-html="highlightSnippet(h.snippet)" />
            </div>
          </div>
        </n-card>
      </aside>
    </div>

    <n-modal
      v-model:show="showPicker"
      preset="card"
      :title="pickerSide === 'left' ? '选择左侧文档' : '选择右侧文档'"
      style="width: min(720px, 92vw)"
    >
      <n-space :size="10" style="margin-bottom: 12px">
        <n-input
          v-model:value="libraryKeyword"
          placeholder="搜索标题"
          clearable
          style="flex: 1"
          @keyup.enter="libraryPage = 1; loadLibraryDocs()"
        />
        <n-button type="primary" @click="libraryPage = 1; loadLibraryDocs()">搜索</n-button>
      </n-space>
      <n-data-table
        :columns="libraryColumns"
        :data="libraryItems"
        :loading="libraryLoading"
        :bordered="false"
        size="small"
      />
    </n-modal>
  </FeatureSubsystemShell>
</template>

<style scoped>
.compare-workspace {
  gap: 0;
}
.compare-workspace {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: row;
  gap: 10px;
  overflow: hidden;
}
.compare-columns {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 10px;
  align-items: stretch;
}
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
.doc-panel--left {
  border-top: 2px solid #60a5fa;
}
.doc-panel--right {
  border-top: 2px solid var(--platform-accent);
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
.doc-panel-search {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 6px 10px;
  border-bottom: 1px solid var(--platform-border, rgba(15, 23, 42, 0.06));
}
.hit-nav {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 0 4px;
  border-radius: 6px;
  background: rgba(139, 92, 246, 0.06);
}
.hit-nav-label {
  font-size: 12px;
  min-width: 3.2em;
  text-align: center;
  font-variant-numeric: tabular-nums;
}
.hit-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: min(42vh, 360px);
  overflow-y: auto;
}
.doc-panel-search :deep(.n-input) {
  flex: 1;
  min-width: 0;
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
.compare-aside {
  width: 260px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
  overflow-y: auto;
}
.aside-card {
  box-shadow: var(--platform-shadow);
}
.aside-card :deep(.n-card__content) {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.aside-hint {
  font-size: 12px;
}
.diff-list,
.hit-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.diff-item {
  padding: 8px;
  border-radius: 6px;
  cursor: pointer;
  border: 1px solid var(--n-border-color);
}
.diff-item:hover,
.diff-item.active {
  border-color: var(--n-primary-color);
  background: var(--platform-accent-muted);
}
.diff-snippet,
.hit-snippet {
  font-size: 12px;
  line-height: 1.45;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.hit-item {
  padding: 8px;
  border-radius: 6px;
  cursor: pointer;
  border: 1px solid var(--n-border-color);
  margin-bottom: 6px;
}
.hit-item:hover,
.hit-item.active {
  border-color: rgba(139, 92, 246, 0.75);
  background: rgba(139, 92, 246, 0.08);
}
.hit-snippet :deep(mark.hl-search) {
  background: rgba(139, 92, 246, 0.35);
  border-radius: 2px;
  padding: 0 1px;
}
@media (max-width: 900px) {
  .compare-workspace {
    flex-direction: column;
  }
  .compare-columns {
    grid-template-columns: 1fr;
  }
  .compare-aside {
    width: 100%;
    max-height: none;
    flex-direction: row;
    flex-wrap: wrap;
  }
  .aside-card {
    flex: 1;
    min-width: 260px;
  }
}
</style>
