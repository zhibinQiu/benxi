<script setup>
defineOptions({ name: "CompareView" });
import { usePlatformUi } from "../composables/usePlatformUi";
import { useI18n } from "../composables/useI18n.js";
import {
  computed,
  nextTick,
  onActivated,
  onBeforeUnmount,
  onDeactivated,
  onMounted,
  ref,
  watch,
} from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  NButton,
  NCard,
  NIcon,
  NInput,
  NSpace,
  NSpin,
  NTag,
  NText,
  NCheckbox,
  NCheckboxGroup,
  NEmpty,
  NModal,
  NPagination,
  NSelect } from "naive-ui";
import {
  ArrowBackOutline,
  DocumentsOutline,
  GitCompareOutline,
  LayersOutline,
  SearchOutline } from "@vicons/ionicons5";
import {
  createCompareJob,
  fetchCompareJob,
  waitCompareJob,
  fetchCompareDocumentContent,
  fetchCompareDocumentFileBlob,
  getCompareDocumentDownload,
  searchCompareDocuments,
  fetchCompareDocuments,
  fetchVersionCompareAdjacent,
  pollVersionCompareAdjacent,
  askVersionCompare,
} from "../api/compare.js";
import { fetchDocument, fetchDocumentFileBlob } from "../api/documents.js";
import CompareDocColumn from "../components/CompareDocColumn.vue";
import CompareDocPicker from "../components/CompareDocPicker.vue";
import ListRefreshButton from "../components/ListRefreshButton.vue";
import MarkdownRichContent from "../components/MarkdownRichContent.vue";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import {
  MIN_COMPARE_COLS,
  MAX_CROSS_COLS,
  MAX_VERSION_COLS,
  DIFF_TYPE_CLASS as diffTypeClass,
  docSideKey,
  docDisplayTitle,
  buildCompareDoc,
  formatTimelineDate,
  comparePreviewKind,
  usesOriginalFilePreview,
  buildPdfDiffHighlights,
  diffCaptionForSide,
  buildParagraphsFromContent,
  hitPage,
  paraMatchesHit,
  diffAnchorBlocks,
  diffMatchesPara,
} from "../utils/compareDocument.js";
import { PREVIEW_KIND } from "../utils/documentPreview.js";
import { openExternal } from "../utils/openExternal.js";
import { PLATFORM_Z } from "../constants/zIndex.js";
import {
  clearCompareViewSession,
  loadCompareViewSession,
  saveCompareViewSession,
} from "../utils/compareViewPersist.js";
import { LIST_PAGE_SIZE } from "../constants/listPage.js";

const ui = usePlatformUi();
const { t } = useI18n();
const route = useRoute();
const router = useRouter();

/** entry | workspace */
const phase = ref("entry");
/** version | cross */
const compareMode = ref(null);

/** @type {import('vue').Ref<Array<{ doc: object, content: object|null, loading: boolean, pdfBaseUrl: string|null, pdfPage: number }>>} */
const columns = ref([]);
const activeTargetIndex = ref(1);
const columnScrollRefs = ref({});

const job = ref(null);
const versionCompareRelation = ref(null);
const versionPairRows = ref([]);
const activePairIndex = ref(0);
const versionAskQuery = ref("");
const versionAskAnswer = ref("");
const versionAskLoading = ref(false);
const comparing = ref(false);
const searchQuery = ref("");
const searchHits = ref([]);
const searching = ref(false);
const fieldMatch = ref(true);
const activeDiffId = ref(null);
const activeHitIndex = ref(-1);
const hitListRef = ref(null);

const showPicker = ref(false);
const pickerColumnIndex = ref(0);

const versionBaseDoc = ref(null);
const versionList = ref([]);
const versionLoading = ref(false);
const checkedVersionIds = ref([]);
const showVersionDocPicker = ref(false);
const showVersionSelectModal = ref(false);

const CROSS_DOC_PAGE_SIZE = LIST_PAGE_SIZE;
const CROSS_COMPARE_DOC_COUNT = 2;

const crossDocs = ref([]);
const showCrossSelectModal = ref(false);
const checkedCrossDocIds = ref([]);
const crossDocList = ref([]);
const crossDocLoading = ref(false);
const crossDocPage = ref(1);
const crossDocTotal = ref(0);
const crossDocKeyword = ref("");

let skipComparePersist = false;
let comparePersistTimer = null;

function buildComparePersistPayload() {
  if (phase.value !== "workspace" || columns.value.length < MIN_COMPARE_COLS) {
    return null;
  }
  return {
    phase: phase.value,
    compareMode: compareMode.value,
    columns: columns.value.map((col) => ({
      doc: col.doc,
      pdfPage: col.pdfPage || 1,
    })),
    activeTargetIndex: activeTargetIndex.value,
    job: job.value,
    versionCompareRelation: versionCompareRelation.value,
    versionPairRows: versionPairRows.value,
    activePairIndex: activePairIndex.value,
    versionAskQuery: versionAskQuery.value,
    versionAskAnswer: versionAskAnswer.value,
    searchQuery: searchQuery.value,
    searchHits: searchHits.value,
    activeDiffId: activeDiffId.value,
    activeHitIndex: activeHitIndex.value,
    fieldMatch: fieldMatch.value,
    versionBaseDoc: versionBaseDoc.value,
    checkedVersionIds: checkedVersionIds.value,
    crossDocs: crossDocs.value,
    checkedCrossDocIds: checkedCrossDocIds.value,
  };
}

function flushComparePersist() {
  if (comparePersistTimer) {
    clearTimeout(comparePersistTimer);
    comparePersistTimer = null;
  }
  if (skipComparePersist) return;
  const payload = buildComparePersistPayload();
  if (payload) {
    saveCompareViewSession(payload);
  } else {
    clearCompareViewSession();
  }
}

function scheduleComparePersist() {
  if (skipComparePersist) return;
  if (comparePersistTimer) clearTimeout(comparePersistTimer);
  comparePersistTimer = setTimeout(flushComparePersist, 400);
}

async function restoreCompareSession(saved) {
  skipComparePersist = true;
  try {
    const docs = (saved.columns || []).map((c) => c.doc).filter((d) => d?.id);
    if (docs.length < MIN_COMPARE_COLS) return;

    phase.value = "workspace";
    compareMode.value = saved.compareMode ?? "cross";
    activeTargetIndex.value = saved.activeTargetIndex ?? 1;
    fieldMatch.value = saved.fieldMatch ?? true;
    searchQuery.value = saved.searchQuery || "";
    searchHits.value = saved.searchHits || [];
    activeDiffId.value = saved.activeDiffId ?? null;
    activeHitIndex.value = saved.activeHitIndex ?? -1;
    versionAskQuery.value = saved.versionAskQuery || "";
    versionAskAnswer.value = saved.versionAskAnswer || "";
    activePairIndex.value = saved.activePairIndex ?? 0;
    versionBaseDoc.value = saved.versionBaseDoc ?? null;
    checkedVersionIds.value = saved.checkedVersionIds || [];
    crossDocs.value = saved.crossDocs || [];
    checkedCrossDocIds.value = saved.checkedCrossDocIds || [];
    job.value = saved.job ?? null;
    versionPairRows.value = saved.versionPairRows || [];

    columns.value = docs.map((doc, i) => ({
      doc,
      content: null,
      loading: false,
      pdfBaseUrl: null,
      pdfPage: saved.columns?.[i]?.pdfPage ?? 1,
    }));
    columnScrollRefs.value = {};
    syncActivePairRelation();

    await hydrateAllColumns();

    if (compareMode.value === "version") {
      if (!versionPairRows.value.length) {
        await loadPrecomputedVersionTimeline({ silent: true });
      } else {
        syncActivePairRelation();
      }
    } else if (compareMode.value === "cross" && saved.job?.id) {
      try {
        const fresh = await fetchCompareJob(saved.job.id);
        if (fresh) {
          job.value = fresh;
          if (fresh.status === "done") syncContentFromJob();
        }
      } catch {
        /* 保留缓存的对比结果 */
      }
    }
  } finally {
    skipComparePersist = false;
    scheduleComparePersist();
  }
}

async function initCompareViewFromRouteOrSession() {
  const mode = route.query.mode;
  const documentId = route.query.documentId;
  if (mode === "version" && typeof documentId === "string" && documentId) {
    await applyCompareRouteQuery();
    return;
  }

  if (phase.value === "workspace" && columns.value.length >= MIN_COMPARE_COLS) {
    return;
  }

  const saved = loadCompareViewSession();
  if (saved?.phase === "workspace" && (saved.columns?.length || 0) >= MIN_COMPARE_COLS) {
    await restoreCompareSession(saved);
  }
}

const baselineColumn = computed(() => columns.value[0] || null);
const targetColumn = computed(() => columns.value[activeTargetIndex.value] || null);
const baselineDoc = computed(() => baselineColumn.value?.doc || null);
const targetDoc = computed(() => targetColumn.value?.doc || null);

const canCompare = computed(() => {
  if (columns.value.length < MIN_COMPARE_COLS || comparing.value) return false;
  if (!baselineDoc.value || !targetDoc.value) return false;
  const keys = columns.value.map((c) => docSideKey(c.doc)).filter(Boolean);
  return new Set(keys).size === keys.length;
});

const canStartCrossCompare = computed(
  () => checkedCrossDocIds.value.length === CROSS_COMPARE_DOC_COUNT
);

const crossDocPageCount = computed(() =>
  Math.max(1, Math.ceil(crossDocTotal.value / CROSS_DOC_PAGE_SIZE))
);

const crossDocOptions = computed(() =>
  crossDocList.value.map((d) => ({
    id: d.id,
    title: d.title,
    file_name: d.file_name,
    label: `${d.title} · ${d.file_name}`,
  }))
);

const canStartVersionCompare = computed(
  () =>
    versionBaseDoc.value &&
    checkedVersionIds.value.length >= MIN_COMPARE_COLS &&
    checkedVersionIds.value.length <= MAX_VERSION_COLS
);

const targetColumnOptions = computed(() =>
  columns.value.slice(1).map((col, i) => ({
    label: `${columnRoleLabel(i + 1)} · ${docDisplayTitle(col.doc)}`,
    value: i + 1}))
);

const uploadedVersionOptions = computed(() =>
  [...versionList.value]
    .sort((a, b) => a.version_no - b.version_no)
    .map((v) => ({
      id: v.id,
      version_no: v.version_no,
      file_name: v.file_name,
      file_size: v.file_size,
      is_current: v.is_current,
      change_description: v.change_description,
      created_at: v.created_at,
      label: `v${v.version_no}${v.is_current ? t("compare.versionCurrent") : ""} · ${new Date(v.created_at).toLocaleDateString()} · ${v.file_name}${v.change_description ? ` · ${v.change_description.slice(0, 40)}${v.change_description.length > 40 ? "…" : ""}` : ""}`,
    }))
);

const canSearch = computed(
  () => targetDoc.value && searchQuery.value.trim() && !searching.value
);

function diffTypeText(type) {
  return t(`compare.diffType.${type}`) || type || t("compare.diffType.unknown");
}

function columnRoleLabel(index) {
  if (compareMode.value === "version") {
    const no = columns.value[index]?.doc?.version_no;
    return no != null ? `v${no}` : t("compare.roleVersion", { index: index + 1 });
  }
  if (compareMode.value === "cross") {
    const doc = columns.value[index]?.doc;
    if (doc?.version_no != null && columns.value.length === CROSS_COMPARE_DOC_COUNT) {
      return index === 0 ? t("compare.roleBaseline") : t("compare.roleTarget");
    }
  }
  if (index === 0) return t("compare.roleBaseline");
  if (index === activeTargetIndex.value) {
    return columns.value.length > 2
      ? t("compare.roleTargetIndexed", { index })
      : t("compare.roleTarget");
  }
  return t("compare.roleColumn", { index: index + 1 });
}

function onColumnPick(index) {
  if (compareMode.value !== "cross") return;
  openPicker(index);
}

function columnDiffSide(index) {
  if (compareMode.value === "version") {
    const pairIdx = activePairIndex.value;
    if (index === pairIdx) return "baseline";
    if (index === pairIdx + 1) return "target";
    return "none";
  }
  if (index === 0) return "baseline";
  if (index === activeTargetIndex.value) return "target";
  return "none";
}

function colPreviewKind(col) {
  return (
    col?.content?.preview_kind ||
    comparePreviewKind(col?.content?.file_name || col?.doc?.file_name)
  );
}

function colUsesOriginalPreview(col) {
  return usesOriginalFilePreview(colPreviewKind(col));
}

function colPdfSrc(col) {
  return col.pdfBaseUrl || col.content?.preview_url || "";
}

function colPdfPage(col, index) {
  return col.pdfPage || 1;
}

function colImageSrc(col) {
  return col.content?.preview_url || "";
}

function colPdfHighlights(col, index) {
  return buildPdfDiffHighlights(
    diffItems.value,
    columnDiffSide(index),
    col.pdfPage || 1,
    activeDiffId.value
  );
}

function colPdfCaption(col, index) {
  if (!activeDiffId.value) return "";
  const side = columnDiffSide(index);
  if (side === "none") return "";
  const d = diffItems.value.find((x) => x.id === activeDiffId.value);
  if (!d) return "";
  const text = diffCaptionForSide(d, side);
  if (!text) return "";
  const label = diffTypeText(d.diff_type);
  return `${label}：${text.length > 200 ? `${text.slice(0, 200)}…` : text}`;
}

function colParagraphs(col) {
  return buildParagraphsFromContent(col.content);
}

function colPlainPreview(col) {
  if (!col.content || colUsesOriginalPreview(col)) return "";
  if (colParagraphs(col).length) return "";
  return col.content.full_text?.trim() || "";
}

function revokeBlobUrl(url) {
  if (url && String(url).startsWith("blob:")) {
    URL.revokeObjectURL(url);
  }
}

watch(activeTargetIndex, () => {
  job.value = null;
  searchHits.value = [];
  activeHitIndex.value = -1;
  activeDiffId.value = null;
  if (compareMode.value === "cross") {
    versionCompareRelation.value = null;
  }
});

const showDiffAside = computed(() =>
  compareMode.value === "version"
    ? versionPairRows.value.some((r) => r.status === "done")
    : job.value?.status === "done"
);

const versionCompareRunning = computed(
  () =>
    compareMode.value === "version" &&
    (comparing.value ||
      versionPairRows.value.some((r) => ["pending", "running"].includes(r.status)))
);

const crossComparePending = computed(
  () =>
    compareMode.value === "cross" &&
    canCompare.value &&
    !job.value &&
    !comparing.value
);

const crossLlmSummary = computed(
  () => (compareMode.value === "cross" && job.value?.payload?.llm_summary) || ""
);

const crossCompareRunning = computed(
  () => compareMode.value === "cross" && comparing.value
);

const activeVersionPair = computed(
  () => versionPairRows.value[activePairIndex.value] || null
);

/** 版本对比：仅 2 个版本时左右双栏 + 右侧提问 */
const isVersionPairLayout = computed(
  () => compareMode.value === "version" && columns.value.length === 2
);
/** 版本对比：3 个及以上版本时网格分行，每行最多 2 栏 */
const isVersionGridLayout = computed(
  () => compareMode.value === "version" && columns.value.length > 2
);

/** 跨文档对比：双栏布局与版本对比 2 版一致 */
const isCrossPairLayout = computed(
  () => compareMode.value === "cross" && columns.value.length === CROSS_COMPARE_DOC_COUNT
);

const showCompareAside = computed(() => {
  if (compareMode.value === "version" && columns.value.length >= 2) {
    return true;
  }
  if (compareMode.value === "cross" && columns.value.length >= MIN_COMPARE_COLS) {
    return true;
  }
  return (
    searchHits.value.length > 0 ||
    showDiffAside.value ||
    versionCompareRunning.value ||
    crossCompareRunning.value
  );
});

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

const rightParagraphs = computed(() => colParagraphs(targetColumn.value));

const diffItems = computed(() => {
  if (compareMode.value === "version") {
    if (versionCompareRelation.value?.status !== "done") return [];
    return versionCompareRelation.value.diff_items || [];
  }
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

function highlightHtml(text, { diffClass, searchActive, hitSnippet, inlineDiff } = {}) {
  let html = escapeHtml(text || "");
  if (!html) return "<span class='para-empty'>（空段落）</span>";

  if (inlineDiff?.spans?.length && inlineDiff.text) {
    const raw = inlineDiff.text;
    const sideKey = inlineDiff.side === "baseline" ? "left" : "right";
    let cursor = 0;
    const parts = [];
    const ordered = [...inlineDiff.spans].sort(
      (a, b) => (a[`${sideKey}_start`] || 0) - (b[`${sideKey}_start`] || 0)
    );
    for (const span of ordered) {
      const start = span[`${sideKey}_start`] ?? 0;
      const end = span[`${sideKey}_end`] ?? start;
      if (start > cursor) {
        parts.push(escapeHtml(raw.slice(cursor, start)));
      }
      const chunk = raw.slice(start, end);
      const cls =
        span.tag === "delete"
          ? diffTypeClass.delete
          : span.tag === "insert"
            ? diffTypeClass.add
            : diffTypeClass.modify;
      parts.push(chunk ? `<span class="${cls}">${escapeHtml(chunk)}</span>` : "");
      cursor = end;
    }
    if (cursor < raw.length) parts.push(escapeHtml(raw.slice(cursor)));
    html = parts.join("") || html;
  } else if (diffClass) {
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
  columns.value.forEach((col) => {
    const docId = col.doc?.id;
    if (!docId || !docs[docId] || colUsesOriginalPreview(col)) return;
    col.content = {
      ...(col.content || {}),
      ...docs[docId],
      preview_url: col.content?.preview_url || null};
  });
}

async function loadOriginalPreviewUrl(doc) {
  const fileName = doc.file_name || "";
  try {
    const blob = doc.version_id
      ? await fetchDocumentFileBlob(doc.id, doc.version_id)
      : await fetchCompareDocumentFileBlob(doc.id);
    return URL.createObjectURL(blob);
  } catch {
    const dl = await getCompareDocumentDownload(doc.id).catch(() => null);
    return dl?.download_url || null;
  }
}

async function hydrateColumn(index) {
  const col = columns.value[index];
  const doc = col?.doc;
  if (!doc?.id) return;
  revokeBlobUrl(col.content?.preview_url);
  col.loading = true;
  try {
    const fileName = doc.file_name || "";
    const previewKind = comparePreviewKind(fileName);
    col.pdfBaseUrl = null;
    col.pdfPage = 1;

    if (usesOriginalFilePreview(previewKind)) {
      const [preview_url, content] = await Promise.all([
        loadOriginalPreviewUrl(doc),
        fetchCompareDocumentContent(doc.id, doc.version_id || null).catch(() => null),
      ]);
      const rootUrl = preview_url ? String(preview_url).split("#")[0] : null;
      col.pdfBaseUrl = previewKind === PREVIEW_KIND.PDF ? rootUrl : null;
      col.content = {
        file_name: fileName,
        preview_kind: previewKind,
        preview_url: rootUrl,
        pages: content?.pages || [],
        blocks: content?.blocks || [],
        full_text: content?.full_text || ""};
      return;
    }

    const content = await fetchCompareDocumentContent(
      doc.id,
      doc.version_id || null
    );
    col.content = {
      pages: content.pages || [],
      blocks: content.blocks || [],
      full_text: content.full_text || "",
      file_name: content.file_name || fileName,
      preview_kind: previewKind,
      parse_quality: content.parse_quality,
      warning: content.warning,
      preview_url: null};
  } catch (e) {
    ui.error(e.message);
    col.content = null;
  } finally {
    col.loading = false;
  }
}

async function hydrateAllColumns() {
  await Promise.all(columns.value.map((_, i) => hydrateColumn(i)));
}

function diffClassForSide(side, para) {
  if (!diffItems.value.length) return null;
  for (const d of diffItems.value) {
    if (!diffMatchesPara(d, side, para)) continue;
    if (d.diff_type === "delete" && side === "baseline") return diffTypeClass.delete;
    if (d.diff_type === "add" && side === "target") return diffTypeClass.add;
    if (d.diff_type === "modify") return diffTypeClass.modify;
  }
  return null;
}

function diffActiveForPara(side, para) {
  if (!activeDiffId.value) return false;
  const d = diffItems.value.find((x) => x.id === activeDiffId.value);
  return d ? diffMatchesPara(d, side, para) : false;
}

function inlineDiffForPara(side, para) {
  if (!activeDiffId.value) return null;
  const d = diffItems.value.find((x) => x.id === activeDiffId.value);
  if (!d || d.diff_type !== "modify" || !diffMatchesPara(d, side, para)) return null;
  const spans = d.anchor_json?.inline_spans;
  if (!spans?.length) return null;
  return { side, spans, text: side === "baseline" ? d.text_left : d.text_right };
}

function initColumnsFromDocs(docs) {
  columns.value = docs.map((doc) => ({
    doc,
    content: null,
    loading: false,
    pdfBaseUrl: null,
    pdfPage: 1}));
  activeTargetIndex.value = docs.length > 1 ? 1 : 0;
  columnScrollRefs.value = {};
}

function resetWorkspaceState() {
  columns.value.forEach((col) => revokeBlobUrl(col.content?.preview_url));
  columns.value = [];
  columnScrollRefs.value = {};
  activeTargetIndex.value = 1;
  job.value = null;
  versionCompareRelation.value = null;
  versionPairRows.value = [];
  activePairIndex.value = 0;
  versionAskQuery.value = "";
  versionAskAnswer.value = "";
  searchHits.value = [];
  activeHitIndex.value = -1;
  activeDiffId.value = null;
}

function syncActivePairRelation() {
  const row = versionPairRows.value[activePairIndex.value];
  versionCompareRelation.value = row || null;
  if (row && columns.value.length > activePairIndex.value + 1) {
    activeTargetIndex.value = activePairIndex.value + 1;
  }
}

function selectVersionPair(index) {
  activePairIndex.value = index;
  syncActivePairRelation();
  activeDiffId.value = null;
  versionAskAnswer.value = "";
}

async function loadPrecomputedVersionTimeline({ silent = false } = {}) {
  if (compareMode.value !== "version" || columns.value.length < 2) return;
  const docId = columns.value[0]?.doc?.id;
  const versionIds = columns.value.map((c) => c.doc?.version_id).filter(Boolean);
  if (!docId || versionIds.length < 2) return;

  comparing.value = true;
  try {
    let rows = await fetchVersionCompareAdjacent(docId, versionIds);
    const pending = rows.some((r) =>
      ["pending", "running"].includes(r.status)
    );
    if (pending) {
      if (!silent) {
        ui.info(t("compare.precomputePending"));
      }
      rows = await pollVersionCompareAdjacent(docId, versionIds);
    }
    versionPairRows.value = rows;
    syncActivePairRelation();
    if (!silent) {
      const failed = rows.filter((r) => r.status === "failed");
      if (failed.length) {
        ui.warning(failed[0].error_message || t("compare.precomputePartialFailed"));
      }
    }
  } catch (e) {
    if (!silent) ui.warning(e.message);
  } finally {
    comparing.value = false;
  }
}

async function runVersionAsk() {
  const q = versionAskQuery.value.trim();
  const row = versionPairRows.value[activePairIndex.value];
  const docId = columns.value[0]?.doc?.id;
  if (!q || !row || !docId) return;
  if (row.status !== "done") {
    ui.warning(t("compare.waitVersionCompare"));
    return;
  }
  versionAskLoading.value = true;
  versionAskAnswer.value = "";
  try {
    const data = await askVersionCompare(docId, {
      leftVersionId: row.from_version_id,
      rightVersionId: row.to_version_id,
      question: q,
    });
    versionAskAnswer.value = data.answer || "";
    if (data.relation) {
      versionPairRows.value[activePairIndex.value] = data.relation;
      syncActivePairRelation();
    }
  } catch (e) {
    ui.error(e.message);
  } finally {
    versionAskLoading.value = false;
  }
}

function enterWorkspace() {
  phase.value = "workspace";
  job.value = null;
  versionCompareRelation.value = null;
  versionPairRows.value = [];
  activePairIndex.value = 0;
  searchHits.value = [];
  activeHitIndex.value = -1;
  hydrateAllColumns().then(async () => {
    if (compareMode.value === "version") {
      await loadPrecomputedVersionTimeline();
    }
  });
}

function openVersionDocPickerFlow() {
  compareMode.value = "version";
  versionBaseDoc.value = null;
  versionList.value = [];
  checkedVersionIds.value = [];
  showVersionDocPicker.value = true;
}

function openCrossDocPickerFlow() {
  compareMode.value = "cross";
  crossDocs.value = [];
  checkedCrossDocIds.value = [];
  crossDocKeyword.value = "";
  crossDocPage.value = 1;
  showCrossSelectModal.value = true;
  void loadCrossDocList();
}

async function loadCrossDocList() {
  crossDocLoading.value = true;
  try {
    const data = await fetchCompareDocuments({
      page: crossDocPage.value,
      page_size: CROSS_DOC_PAGE_SIZE,
      keyword: crossDocKeyword.value || undefined,
    });
    crossDocList.value = data.items || [];
    crossDocTotal.value = data.total ?? 0;
  } catch (e) {
    ui.error(e.message);
  } finally {
    crossDocLoading.value = false;
  }
}

function onCrossDocSearch() {
  crossDocPage.value = 1;
  void loadCrossDocList();
}

function onCrossDocPageChange(page) {
  crossDocPage.value = page;
  void loadCrossDocList();
}

function onCrossDocCheckUpdate(ids) {
  if (ids.length > CROSS_COMPARE_DOC_COUNT) {
    checkedCrossDocIds.value = ids.slice(-CROSS_COMPARE_DOC_COUNT);
    ui.info(t("compare.maxCrossDocs", { count: CROSS_COMPARE_DOC_COUNT }));
    return;
  }
  checkedCrossDocIds.value = ids;
}

function pickLatestUploadedVersion(versions) {
  const uploaded = (versions || []).filter((v) => v.uploaded && v.file_size > 0);
  if (!uploaded.length) return null;
  const current = uploaded.find((v) => v.is_current);
  if (current) return current;
  return uploaded.sort((a, b) => b.version_no - a.version_no)[0];
}

async function resolveCrossDocsWithLatestVersions(docRows) {
  const resolved = [];
  for (const row of docRows) {
    const doc = await fetchDocument(row.id);
    const version = pickLatestUploadedVersion(doc.versions);
    if (!version) {
      throw new Error(
        t("compare.noUploadedVersionCannotCompare", {
          title: doc.title || row.title,
        })
      );
    }
    resolved.push(
      buildCompareDoc(
        {
          id: doc.id,
          title: doc.title || row.title,
          file_name: row.file_name || version.file_name,
          file_size: version.file_size,
          created_at: version.created_at || doc.updated_at,
        },
        version
      )
    );
  }
  return resolved;
}

function cancelCrossSelect() {
  showCrossSelectModal.value = false;
  checkedCrossDocIds.value = [];
  crossDocs.value = [];
}

async function confirmCrossCompare() {
  if (!canStartCrossCompare.value) {
    ui.warning(t("compare.pickCrossDocCount", { count: CROSS_COMPARE_DOC_COUNT }));
    return;
  }
  const pickedRows = crossDocOptions.value.filter((d) =>
    checkedCrossDocIds.value.includes(d.id)
  );
  if (pickedRows.length !== CROSS_COMPARE_DOC_COUNT) return;

  crossDocLoading.value = true;
  try {
    const docs = await resolveCrossDocsWithLatestVersions(pickedRows);
    crossDocs.value = docs;
    showCrossSelectModal.value = false;
    startCrossCompare(docs);
  } catch (e) {
    ui.error(e.message);
  } finally {
    crossDocLoading.value = false;
  }
}

function goEntry() {
  phase.value = "entry";
  compareMode.value = null;
  resetWorkspaceState();
  versionBaseDoc.value = null;
  versionList.value = [];
  checkedVersionIds.value = [];
  crossDocs.value = [];
  checkedCrossDocIds.value = [];
  showCrossSelectModal.value = false;
  clearCompareViewSession();
}

function goSetupFromWorkspace() {
  resetWorkspaceState();
  if (compareMode.value === "version") {
    openVersionDocPickerFlow();
  } else {
    openCrossDocPickerFlow();
  }
}

async function prepareVersionCompare(docId, baseDoc = null) {
  checkedVersionIds.value = [];
  versionLoading.value = true;
  try {
    const doc = await fetchDocument(docId);
    const currentVersion = (doc.versions || []).find((v) => v.is_current);
    versionBaseDoc.value =
      baseDoc ||
      {
        id: doc.id,
        title: doc.title,
        file_name:
          doc.file_name ||
          currentVersion?.file_name ||
          doc.versions?.[0]?.file_name ||
          "",
      };
    versionList.value = (doc.versions || []).filter((v) => v.uploaded);
    if (versionList.value.length < MIN_COMPARE_COLS) {
      ui.warning(t("compare.needTwoVersions"));
      versionBaseDoc.value = null;
      versionList.value = [];
      return false;
    }
    showVersionSelectModal.value = true;
    return true;
  } catch (e) {
    ui.error(e.message);
    versionBaseDoc.value = null;
    return false;
  } finally {
    versionLoading.value = false;
  }
}

async function onVersionBaseSelected(row) {
  compareMode.value = "version";
  await prepareVersionCompare(row.id, row);
}

async function applyCompareRouteQuery() {
  const mode = route.query.mode;
  const documentId = route.query.documentId;
  if (mode !== "version" || typeof documentId !== "string" || !documentId) {
    return;
  }

  const nextQuery = { ...route.query };
  delete nextQuery.mode;
  delete nextQuery.documentId;
  router.replace({ query: nextQuery });

  compareMode.value = "version";
  await prepareVersionCompare(documentId);
}

function onVersionCheckUpdate(ids) {
  if (ids.length > MAX_VERSION_COLS) {
    checkedVersionIds.value = ids.slice(-MAX_VERSION_COLS);
    ui.info(t("compare.maxVersions", { max: MAX_VERSION_COLS }));
    return;
  }
  checkedVersionIds.value = ids;
}

function confirmVersionCompare() {
  startVersionCompare();
  showVersionSelectModal.value = false;
}

function cancelVersionSelect() {
  showVersionSelectModal.value = false;
  versionBaseDoc.value = null;
  versionList.value = [];
  checkedVersionIds.value = [];
}

function startVersionCompare() {
  const count = checkedVersionIds.value.length;
  if (count < MIN_COMPARE_COLS || count > MAX_VERSION_COLS) {
    ui.warning(
      t("compare.pickVersionRange", { min: MIN_COMPARE_COLS, max: MAX_VERSION_COLS })
    );
    return;
  }
  const picked = versionList.value
    .filter((v) => checkedVersionIds.value.includes(v.id))
    .sort((a, b) => a.version_no - b.version_no);
  if (picked.length !== count) return;
  compareMode.value = "version";
  initColumnsFromDocs(
    picked.map((v) => buildCompareDoc(versionBaseDoc.value, v))
  );
  enterWorkspace();
}

function startCrossCompare(docs = crossDocs.value) {
  if (docs.length < MIN_COMPARE_COLS || docs.length > MAX_CROSS_COLS) {
    ui.warning(t("compare.pickDocRange", { min: MIN_COMPARE_COLS, max: MAX_CROSS_COLS }));
    return;
  }
  compareMode.value = "cross";
  initColumnsFromDocs(docs);
  enterWorkspace();
}

function openPicker(columnIndex) {
  pickerColumnIndex.value = columnIndex;
  showPicker.value = true;
}

async function onWorkspaceDocSelect(row) {
  crossDocLoading.value = true;
  try {
    const doc = await fetchDocument(row.id);
    const version = pickLatestUploadedVersion(doc.versions);
    if (!version) {
      ui.warning(
        t("compare.noUploadedVersion", { title: doc.title || row.title })
      );
      return;
    }
    const compareDoc = buildCompareDoc(
      {
        id: doc.id,
        title: doc.title || row.title,
        file_name: row.file_name || version.file_name,
        file_size: version.file_size,
        created_at: version.created_at || doc.updated_at,
      },
      version
    );
    const idx = pickerColumnIndex.value;
    if (columns.value[idx]) {
      revokeBlobUrl(columns.value[idx].content?.preview_url);
      columns.value[idx].doc = compareDoc;
      columns.value[idx].content = null;
      columns.value[idx].pdfBaseUrl = null;
      columns.value[idx].pdfPage = 1;
      await hydrateColumn(idx);
    }
    if (compareMode.value !== "version") compareMode.value = "cross";
    showPicker.value = false;
    job.value = null;
    versionCompareRelation.value = null;
    searchHits.value = [];
    activeHitIndex.value = -1;
    activeDiffId.value = null;
  } catch (e) {
    ui.error(e.message);
  } finally {
    crossDocLoading.value = false;
  }
}

function setColumnScrollRef({ el, index }) {
  if (el) columnScrollRefs.value[index] = el;
}

function setColumnPdfPage(index, page) {
  const col = columns.value[index];
  if (!col) return;
  col.pdfPage = Math.max(1, Number(page) || 1);
}

async function openOriginalPdf(doc) {
  if (!doc?.id) return;
  try {
    if (doc.version_id) {
      const blob = await fetchDocumentFileBlob(doc.id, doc.version_id);
      const url = URL.createObjectURL(blob);
      openExternal(url);
      window.setTimeout(() => URL.revokeObjectURL(url), 60000);
      return;
    }
    const data = await getCompareDocumentDownload(doc.id);
    if (data?.download_url) openExternal(data.download_url);
  } catch (e) {
    ui.error(e.message);
  }
}

async function runCompare() {
  if (compareMode.value === "version") {
    await loadPrecomputedVersionTimeline();
    return;
  }
  if (!baselineDoc.value || !targetDoc.value) return;
  comparing.value = true;
  job.value = null;
  versionCompareRelation.value = null;
  searchHits.value = [];
  try {
    const created = await createCompareJob({
      leftDocumentId: baselineDoc.value.id,
      rightDocumentId: targetDoc.value.id,
    });
    job.value =
      created?.status === "pending" || created?.status === "running"
        ? await waitCompareJob(created.id)
        : created;
    if (job.value.status === "failed") {
      ui.error(job.value.error_message || t("compare.compareFailed"));
    } else {
      syncContentFromJob();
      ui.success(
        columns.value.length > 2
          ? t("compare.compareDoneMulti", {
              title: docDisplayTitle(targetDoc.value),
            })
          : t("compare.compareDone")
      );
    }
  } catch (e) {
    ui.error(e.message);
  } finally {
    comparing.value = false;
  }
}

async function ensureTargetSearchIndex() {
  const col = targetColumn.value;
  if (!col?.doc?.id || colParagraphs(col).length) return;
  try {
    const content = await fetchCompareDocumentContent(col.doc.id);
    if (col.content) {
      col.content = {
        ...col.content,
        pages: content.pages || [],
        full_text: content.full_text || ""};
    }
  } catch {
    /* 仅用于定位跳转 */
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

  const col = targetColumn.value;
  if (!col) return;

  if (colUsesOriginalPreview(col) && colPreviewKind(col) === PREVIEW_KIND.PDF) {
    col.pdfPage = hitPage(hit);
    return;
  }

  const idx = findParaIndexByHit(hit);
  const root = columnScrollRefs.value[activeTargetIndex.value];
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
  void initCompareViewFromRouteOrSession();
});

watch(
  () => [route.query.mode, route.query.documentId],
  () => {
    void initCompareViewFromRouteOrSession();
  }
);

watch(
  [
    phase,
    compareMode,
    columns,
    activeTargetIndex,
    job,
    versionCompareRelation,
    versionPairRows,
    activePairIndex,
    versionAskQuery,
    versionAskAnswer,
    searchQuery,
    searchHits,
    activeDiffId,
    activeHitIndex,
    fieldMatch,
    versionBaseDoc,
    checkedVersionIds,
    crossDocs,
    checkedCrossDocIds,
  ],
  scheduleComparePersist,
  { deep: true }
);

onDeactivated(() => {
  flushComparePersist();
});

onActivated(() => {
  scheduleComparePersist();
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onCompareKeydown);
  columns.value.forEach((col) => revokeBlobUrl(col.content?.preview_url));
  flushComparePersist();
});

async function runSearch() {
  if (!targetDoc.value?.id || !searchQuery.value.trim()) return;
  searching.value = true;
  activeHitIndex.value = -1;
  try {
    await ensureTargetSearchIndex();
    searchHits.value = await searchCompareDocuments({
      rightDocumentId: targetDoc.value.id,
      query: searchQuery.value.trim(),
      fieldMatch: fieldMatch.value,
    });
    if (!searchHits.value.length) {
      ui.info(t("compare.searchNoHits"));
      return;
    }
    await jumpToHit(searchHits.value[0], 0);
  } catch (e) {
    ui.error(e.message);
  } finally {
    searching.value = false;
  }
}

function onHitClick(hit, index) {
  jumpToHit(hit, index);
}

function onDiffClick(d) {
  activeDiffId.value = d.id;
  scrollToDiffItem(d);
}

async function scrollToDiffItem(d) {
  await nextTick();
  for (let i = 0; i < columns.value.length; i += 1) {
    const side = columnDiffSide(i);
    if (side === "none") continue;
    const col = columns.value[i];
    const blocks = diffAnchorBlocks(d, side);
    const page = blocks[0]?.page;
    if (
      page &&
      colUsesOriginalPreview(col) &&
      colPreviewKind(col) === PREVIEW_KIND.PDF
    ) {
      col.pdfPage = Number(page) || 1;
      continue;
    }
    const blockIndex = blocks[0]?.block_index;
    if (blockIndex == null) continue;
    const root = columnScrollRefs.value[i];
    const el = root?.querySelector?.(`[data-block-index="${blockIndex}"]`);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.classList.add("para-flash");
      window.setTimeout(() => el.classList.remove("para-flash"), 2000);
    }
  }
}
</script>

<template>
  <FeatureSubsystemShell fill>
    <template #extra>
      <n-space v-if="phase === 'workspace'" :size="8" align="center" wrap>
        <n-button size="small" quaternary @click="goSetupFromWorkspace">
          <template #icon>
            <n-icon :component="ArrowBackOutline" />
          </template>
          {{ t("compare.reselect") }}
        </n-button>
        <n-tag size="small" :bordered="false" type="info">
          {{ compareMode === "version" ? t("compare.modeVersion") : t("compare.modeCross") }}
          · {{ t("compare.columnCount", { count: columns.length }) }}
        </n-tag>
        <n-select
          v-if="compareMode === 'cross' && columns.length > 2"
          v-model:value="activeTargetIndex"
          size="small"
          style="width: min(220px, 42vw)"
          :options="targetColumnOptions"
          :placeholder="t('compare.targetColumnPlaceholder')"
        />
        <n-input
          v-model:value="searchQuery"
          size="small"
          :placeholder="t('compare.searchPlaceholder')"
          clearable
          style="width: min(220px, 36vw)"
          :disabled="!targetDoc"
          @keyup.enter="runSearch"
          @keydown="onSearchKeydown"
        >
          <template #prefix>
            <n-icon :component="SearchOutline" />
          </template>
        </n-input>
        <n-button size="small" type="primary" :disabled="!canSearch" :loading="searching" @click="runSearch">
          {{ t("compare.search") }}
        </n-button>
        <n-checkbox v-model:checked="fieldMatch" size="small">{{ t("compare.fieldMatch") }}</n-checkbox>
        <n-button
          v-if="compareMode === 'cross' && crossComparePending"
          size="small"
          type="primary"
          :loading="comparing"
          @click="runCompare"
        >
          <template #icon>
            <n-icon :component="GitCompareOutline" />
          </template>
          {{ t("compare.startCompare") }}
        </n-button>
        <ListRefreshButton
          v-if="compareMode === 'cross' && job?.status === 'done'"
          :label="t('compare.refreshDiff')"
          :disabled="!canCompare"
          :loading="comparing"
          @click="runCompare"
        />
        <ListRefreshButton
          v-if="compareMode === 'version'"
          :label="t('compare.refreshDiff')"
          :loading="comparing"
          @click="loadPrecomputedVersionTimeline()"
        />
      </n-space>
    </template>

    <!-- 入口：选择对比模式 -->
    <div v-if="phase === 'entry'" class="compare-entry">
      <div class="compare-mode-grid">
        <n-card class="compare-mode-card" hoverable @click="openVersionDocPickerFlow">
          <div class="compare-mode-icon compare-mode-icon--version">
            <n-icon :component="LayersOutline" :size="28" />
          </div>
          <n-text class="compare-mode-title">{{ t("compare.versionModeTitle") }}</n-text>
        </n-card>
        <n-card class="compare-mode-card" hoverable @click="openCrossDocPickerFlow">
          <div class="compare-mode-icon compare-mode-icon--cross">
            <n-icon :component="DocumentsOutline" :size="28" />
          </div>
          <n-text class="compare-mode-title">{{ t("compare.crossModeTitle") }}</n-text>
        </n-card>
      </div>
    </div>

    <!-- 对比工作台 -->
    <div v-else class="compare-workspace">
      <n-card
        v-if="compareMode === 'version' && columns.length > 2"
        size="small"
        class="version-timeline-card"
        :title="t('compare.versionTimeline')"
      >
        <div class="version-timeline">
          <template v-for="(col, i) in columns" :key="col.doc.version_id || i">
            <div
              class="version-timeline-node"
              :class="{
                active: i === activePairIndex || i === activePairIndex + 1,
                current: i === columns.length - 1,
              }"
            >
              <div class="version-timeline-dot">v{{ col.doc.version_no }}</div>
              <n-text depth="3" class="version-timeline-date">
                {{ formatTimelineDate(col.doc.created_at) }}
              </n-text>
              <n-text
                v-if="col.doc.change_description"
                depth="3"
                class="version-timeline-note"
              >
                {{ col.doc.change_description }}
              </n-text>
            </div>
            <button
              v-if="i < columns.length - 1"
              type="button"
              class="version-timeline-segment"
              :class="{ active: activePairIndex === i }"
              @click="selectVersionPair(i)"
            >
              <span class="version-timeline-segment-label">
                v{{ col.doc.version_no }}→v{{ columns[i + 1]?.doc?.version_no }}
              </span>
              <n-tag
                v-if="versionPairRows[i]"
                size="tiny"
                :bordered="false"
                :type="
                  versionPairRows[i].status === 'done'
                    ? 'success'
                    : versionPairRows[i].status === 'failed'
                      ? 'error'
                      : 'info'
                "
              >
                {{
                  versionPairRows[i].status === "done"
                    ? t("compare.diffCount", {
                        count: versionPairRows[i].diff_count || 0,
                      })
                    : versionPairRows[i].status === "failed"
                      ? t("compare.statusFailed")
                      : "…"
                }}
              </n-tag>
            </button>
          </template>
        </div>
      </n-card>

      <div
        class="compare-workspace-body"
        :class="{
          'compare-workspace-body--version-pair': isVersionPairLayout,
          'compare-workspace-body--version-grid': isVersionGridLayout,
          'compare-workspace-body--cross-pair': isCrossPairLayout,
        }"
      >
      <div
        class="compare-columns"
        :class="[
          `compare-columns--${columns.length}`,
          {
            'compare-columns--version-pair': isVersionPairLayout,
            'compare-columns--version-grid': isVersionGridLayout,
            'compare-columns--cross-pair': isCrossPairLayout,
          },
        ]"
      >
        <CompareDocColumn
          v-for="(col, index) in columns"
          :key="docSideKey(col.doc)"
          :column-index="index"
          :doc="col.doc"
          :content="col.content"
          :loading="col.loading"
          :comparing="comparing"
          :pdf-src="colPdfSrc(col)"
          :pdf-page="colPdfPage(col, index)"
          :preview-kind="colPreviewKind(col)"
          :pdf-highlights="colPdfHighlights(col, index)"
          :diff-items="diffItems"
          :active-diff-id="activeDiffId"
          :pdf-caption="colPdfCaption(col, index)"
          :image-src="colImageSrc(col)"
          :role-label="columnRoleLabel(index)"
          :is-baseline="index === 0"
          :is-search-target="index === activeTargetIndex"
          :diff-side="columnDiffSide(index)"
          :paragraphs="colParagraphs(col)"
          :plain-preview="colPlainPreview(col)"
          :search-hits="searchHits"
          :active-hit-index="activeHitIndex"
          :active-hit="activeHit"
          :hit-nav-label="hitNavLabel"
          :can-hit-prev="canHitPrev"
          :can-hit-next="canHitNext"
          :highlight-html="highlightHtml"
          :diff-class-for-side="diffClassForSide"
          :diff-active-for-para="diffActiveForPara"
          :inline-diff-for-para="inlineDiffForPara"
          :para-hit-state="paraHitState"
          :doc-display-title="docDisplayTitle"
          :hit-page="hitPage"
          :highlight-snippet="highlightSnippet"
          :allow-pick="compareMode === 'cross'"
          @pick="onColumnPick"
          @open-pdf="openOriginalPdf"
          @scroll-ref="setColumnScrollRef"
          @update:pdf-page="(page) => setColumnPdfPage(index, page)"
          @prev-hit="goPrevHit"
          @next-hit="goNextHit"
        />
      </div>

      <aside
        v-if="showCompareAside"
        class="compare-aside"
        :class="{
          'compare-aside--version-pair': isVersionPairLayout,
          'compare-aside--cross-pair': isCrossPairLayout,
        }"
      >
        <n-card
          v-if="compareMode === 'version' && versionCompareRelation?.status === 'done'"
          size="small"
          :title="t('compare.versionAskTitle')"
          class="aside-card aside-card--version-ask"
        >
          <n-space vertical :size="8">
            <n-input
              v-model:value="versionAskQuery"
              type="textarea"
              :placeholder="t('compare.versionAskPlaceholder')"
              :autosize="{ minRows: 2, maxRows: 4 }"
              @keyup.enter.exact="runVersionAsk"
            />
            <n-button
              size="small"
              type="primary"
              :loading="versionAskLoading"
              :disabled="!versionAskQuery.trim()"
              @click="runVersionAsk"
            >
              {{ t("compare.ask") }}
            </n-button>
            <MarkdownRichContent
              v-if="versionAskAnswer"
              class="version-ask-answer"
              :content="versionAskAnswer"
            />
          </n-space>
        </n-card>

        <n-card
          v-if="compareMode === 'version' && activeVersionPair?.status === 'done'"
          size="small"
          :title="t('compare.changeSummary')"
          class="aside-card version-summary-card"
        >
          <n-space vertical :size="10">
            <div v-if="activeVersionPair.to_change_description">
              <n-text depth="3" class="version-summary-label">{{ t("compare.newVersionNote") }}</n-text>
              <MarkdownRichContent
                class="version-summary-body"
                :content="activeVersionPair.to_change_description"
              />
            </div>
            <div v-if="activeVersionPair.llm_summary">
              <n-text depth="3" class="version-summary-label">{{ t("compare.aiDiffSummary") }}</n-text>
              <MarkdownRichContent
                class="version-summary-body"
                :content="activeVersionPair.llm_summary"
              />
            </div>
            <n-text
              v-if="!activeVersionPair.to_change_description && !activeVersionPair.llm_summary"
              depth="3"
            >
              {{ t("compare.noVersionSummary") }}
            </n-text>
          </n-space>
        </n-card>

        <n-card
          v-if="compareMode === 'version' && versionPairRows.length && columns.length > 2"
          size="small"
          :title="t('compare.timelineChanges')"
          class="aside-card aside-card--version-timeline"
        >
          <div class="version-pair-list">
            <div
              v-for="(row, idx) in versionPairRows"
              :key="row.id || idx"
              class="version-pair-row"
              :class="{ active: activePairIndex === idx, running: ['pending', 'running'].includes(row.status) }"
              @click="selectVersionPair(idx)"
            >
              <n-space align="center" justify="space-between" style="width: 100%">
                <n-text>
                  v{{ row.from_version_no }} → v{{ row.to_version_no }}
                </n-text>
                <n-tag size="small" :bordered="false" :type="row.status === 'done' ? 'success' : row.status === 'failed' ? 'error' : 'info'">
                  {{
                    row.status === "done"
                      ? t("compare.diffCount", { count: row.diff_count || 0 })
                      : row.status === "failed"
                        ? t("compare.statusFailed")
                        : t("compare.statusComparing")
                  }}
                </n-tag>
              </n-space>
              <n-text v-if="row.to_change_description" depth="3" class="version-pair-summary">
                {{ t("compare.versionNotePrefix") }}{{ row.to_change_description.slice(0, 120) }}{{ row.to_change_description.length > 120 ? "…" : "" }}
              </n-text>
              <n-text v-if="row.llm_summary" depth="3" class="version-pair-summary">
                {{ row.llm_summary.slice(0, 160) }}{{ row.llm_summary.length > 160 ? "…" : "" }}
              </n-text>
            </div>
          </div>
        </n-card>

        <n-card
          v-if="compareMode === 'cross' && crossComparePending"
          size="small"
          :title="t('compare.crossPendingTitle')"
          class="aside-card aside-card--cross-pending"
        >
          <n-space vertical :size="10">
            <n-text depth="3">{{ t("compare.crossPendingHint") }}</n-text>
            <n-button type="primary" :loading="comparing" @click="runCompare">
              <template #icon>
                <n-icon :component="GitCompareOutline" />
              </template>
              {{ t("compare.startCompare") }}
            </n-button>
          </n-space>
        </n-card>

        <n-card
          v-if="compareMode === 'cross' && crossLlmSummary"
          size="small"
          :title="t('compare.aiDiffSummary')"
          class="aside-card version-summary-card"
        >
          <MarkdownRichContent
            class="version-summary-body"
            :content="crossLlmSummary"
          />
        </n-card>

        <n-card
          v-if="crossCompareRunning"
          size="small"
          :title="t('compare.crossComparingTitle')"
          class="aside-card aside-card--cross-running"
        >
          <n-text depth="3">{{ t("compare.crossComparingHint") }}</n-text>
        </n-card>

        <n-card
          v-if="versionCompareRunning"
          size="small"
          :title="t('compare.versionComparingTitle')"
          class="aside-card aside-card--version-running"
        >
          <n-text depth="3">{{ t("compare.versionComparingHint") }}</n-text>
        </n-card>

        <n-card
          v-if="showDiffAside"
          size="small"
          :title="t('compare.diffList')"
          class="aside-card aside-card--diff-list"
        >
          <n-text depth="3" class="aside-hint">
            <template v-if="compareMode === 'version' && versionCompareRelation">
              {{
                t("compare.diffListVersionPair", {
                  from: versionCompareRelation.from_version_no,
                  to: versionCompareRelation.to_version_no,
                  count: diffItems.length,
                })
              }}
            </template>
            <template v-else-if="compareMode === 'cross'">
              {{
                t("compare.diffListCross", {
                  left: docDisplayTitle(baselineDoc),
                  right: docDisplayTitle(targetDoc),
                  count: diffItems.length,
                })
              }}
            </template>
            <template v-else>
              {{
                t("compare.diffListMulti", {
                  count: diffItems.length,
                  target: docDisplayTitle(targetDoc),
                })
              }}
            </template>
          </n-text>
          <div class="diff-list">
            <div
              v-for="d in diffItems"
              :key="d.id"
              class="diff-item"
              :class="{ active: activeDiffId === d.id }"
              @click="onDiffClick(d)"
            >
              <n-tag size="small" :bordered="false">{{ diffTypeText(d.diff_type) }}</n-tag>
              <n-text class="diff-snippet" depth="2">
                {{
                  (d.text_right || d.text_left || d.anchor_json?.description || "").slice(
                    0,
                    120
                  )
                }}
              </n-text>
            </div>
            <n-text
              v-if="!diffItems.length && compareMode === 'cross' && crossLlmSummary"
              depth="3"
            >
              {{ crossLlmSummary }}
            </n-text>
            <n-text v-else-if="!diffItems.length" depth="3">{{ t("compare.noTextDiff") }}</n-text>
          </div>
        </n-card>

        <n-card v-if="searchHits.length" size="small" class="aside-card">
          <template #header>
            <n-space align="center" justify="space-between" style="width: 100%">
              <span>{{ t("compare.searchHits") }}</span>
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
                  h.source === "knowflow" ? t("compare.hitSourceSmart") : t("compare.hitSourceFulltext")
                }}</n-tag>
                <n-tag v-if="hitPage(h) > 0" size="tiny" :bordered="false">P{{ hitPage(h) }}</n-tag>
                <n-text depth="3">{{
                  t("compare.hitScore", { score: h.score?.toFixed?.(2) ?? h.score })
                }}</n-text>
              </n-space>
              <div class="hit-snippet" v-html="highlightSnippet(h.snippet)" />
            </div>
          </div>
        </n-card>
      </aside>
      </div>
    </div>

    <CompareDocPicker
      v-model:show="showVersionDocPicker"
      :title="t('compare.pickDocTitle')"
      @select="onVersionBaseSelected"
    />
    <n-modal
      v-model:show="showVersionSelectModal"
      preset="card"
      :title="t('compare.pickVersionTitle')"
      :z-index="PLATFORM_Z.featureModal"
      style="width: min(520px, 92vw)"
      :mask-closable="false"
    >
      <n-space vertical :size="14">
        <div v-if="versionBaseDoc">
          <n-text depth="3" style="font-size: 12px; display: block; margin-bottom: 6px">
            {{ t("compare.selectedDoc") }}
          </n-text>
          <n-text class="compare-version-doc">
            {{ versionBaseDoc.title }}
            <n-text depth="3">（{{ versionBaseDoc.file_name }}）</n-text>
          </n-text>
        </div>
        <div>
          <n-text depth="3" style="font-size: 12px; display: block; margin-bottom: 8px">
            {{
              t("compare.pickVersionsHint", {
                selected: checkedVersionIds.length,
                max: MAX_VERSION_COLS,
              })
            }}
          </n-text>
          <n-spin :show="versionLoading" local>
            <n-checkbox-group
              v-if="uploadedVersionOptions.length"
              :value="checkedVersionIds"
              @update:value="onVersionCheckUpdate"
            >
              <n-space vertical :size="8">
                <n-checkbox
                  v-for="v in uploadedVersionOptions"
                  :key="v.id"
                  :value="v.id"
                  :label="v.label"
                />
              </n-space>
            </n-checkbox-group>
            <n-empty v-else :description="t('compare.noUploadedVersions')" size="small" />
          </n-spin>
        </div>
      </n-space>
      <template #footer>
        <n-space justify="end">
          <n-button @click="cancelVersionSelect">{{ t("compare.cancel") }}</n-button>
          <n-button
            type="primary"
            :disabled="!canStartVersionCompare"
            @click="confirmVersionCompare"
          >
            <template #icon>
              <n-icon :component="GitCompareOutline" />
            </template>
            {{ t("compare.viewVersionChanges") }}
          </n-button>
        </n-space>
      </template>
    </n-modal>
    <n-modal
      v-model:show="showCrossSelectModal"
      preset="card"
      :title="t('compare.pickCrossTitle')"
      :z-index="PLATFORM_Z.featureModal"
      style="width: min(560px, 92vw)"
      :mask-closable="false"
    >
      <n-space vertical :size="14">
        <n-space :size="10">
          <n-input
            v-model:value="crossDocKeyword"
            :placeholder="t('compare.searchDocPlaceholder')"
            clearable
            style="flex: 1"
            @keyup.enter="onCrossDocSearch"
          />
          <n-button type="primary" @click="onCrossDocSearch">{{ t("compare.searchBtn") }}</n-button>
        </n-space>
        <div>
          <n-text depth="3" style="font-size: 12px; display: block; margin-bottom: 8px">
            {{
              t("compare.pickCrossHint", {
                selected: checkedCrossDocIds.length,
                count: CROSS_COMPARE_DOC_COUNT,
              })
            }}
          </n-text>
          <n-spin :show="crossDocLoading" local>
            <n-checkbox-group
              v-if="crossDocOptions.length"
              :value="checkedCrossDocIds"
              @update:value="onCrossDocCheckUpdate"
            >
              <n-space vertical :size="8">
                <n-checkbox
                  v-for="d in crossDocOptions"
                  :key="d.id"
                  :value="d.id"
                  :label="d.label"
                />
              </n-space>
            </n-checkbox-group>
            <n-empty v-else :description="t('compare.noComparableDocs')" size="small" />
          </n-spin>
          <n-space
            v-if="crossDocPageCount > 1"
            justify="center"
            style="margin-top: 12px"
          >
            <n-pagination
              :page="crossDocPage"
              :page-count="crossDocPageCount"
              :page-slot="7"
              @update:page="onCrossDocPageChange"
            />
          </n-space>
        </div>
      </n-space>
      <template #footer>
        <n-space justify="end">
          <n-button @click="cancelCrossSelect">{{ t("compare.cancel") }}</n-button>
          <n-button
            type="primary"
            :disabled="!canStartCrossCompare"
            :loading="crossDocLoading"
            @click="confirmCrossCompare"
          >
            <template #icon>
              <n-icon :component="GitCompareOutline" />
            </template>
            {{ t("compare.confirmSelection") }}
          </n-button>
        </n-space>
      </template>
    </n-modal>
    <CompareDocPicker
      v-model:show="showPicker"
      :title="t('compare.replaceDocTitle')"
      :exclude-ids="
        columns
          .map((c, i) => (i !== pickerColumnIndex ? c.doc?.id : null))
          .filter(Boolean)
      "
      @select="onWorkspaceDocSelect"
    />
  </FeatureSubsystemShell>
</template>

<style scoped>
.compare-entry {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 24px 16px 32px;
  min-height: 0;
}
.compare-entry-lead {
  font-size: 13px;
  margin-bottom: 20px;
  text-align: center;
}
.compare-mode-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(240px, 320px));
  gap: 16px;
  width: 100%;
  max-width: 720px;
}
.compare-mode-card {
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.compare-mode-card:hover {
  transform: translateY(-2px);
}
.compare-mode-card :deep(.n-card__content) {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 10px;
  padding-top: 4px;
}
.compare-mode-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.compare-mode-icon--version {
  background: rgba(96, 165, 250, 0.18);
  color: var(--platform-accent);
}
.compare-mode-icon--cross {
  background: color-mix(in srgb, var(--platform-accent) 15%, transparent);
  color: var(--platform-accent-pressed);
}
.compare-mode-title {
  font-size: 16px;
  font-weight: 600;
}
.compare-mode-desc {
  font-size: 12px;
  line-height: 1.55;
}
.compare-version-doc {
  font-size: 14px;
  font-weight: 500;
}
.compare-workspace {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow: hidden;
  box-sizing: border-box;
  width: 100%;
  max-width: 100%;
  --compare-aside-width: min(300px, 28vw);
  --compare-body-gap: 14px;
}
.compare-workspace-body {
  flex: 1;
  min-width: 0;
  min-height: 0;
  max-width: 100%;
  display: flex;
  flex-direction: row;
  gap: var(--compare-body-gap);
  overflow: hidden;
  box-sizing: border-box;
}
.compare-workspace-body--version-pair,
.compare-workspace-body--cross-pair,
.compare-workspace-body--version-grid {
  min-height: 0;
  overflow: hidden;
}
.version-timeline-card {
  flex-shrink: 0;
}
.version-timeline {
  display: flex;
  align-items: flex-start;
  gap: 0;
  overflow-x: auto;
  padding: 4px 0 8px;
}
.version-timeline-node {
  flex: 0 0 auto;
  min-width: 88px;
  max-width: 140px;
  text-align: center;
  padding: 0 4px;
}
.version-timeline-node.active .version-timeline-dot {
  border-color: var(--n-primary-color);
  background: var(--platform-accent-muted);
}
.version-timeline-dot {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 40px;
  height: 40px;
  border-radius: 999px;
  border: 2px solid var(--n-border-color);
  font-size: 12px;
  font-weight: 600;
  margin: 0 auto 4px;
}
.version-timeline-date {
  display: block;
  font-size: 11px;
  line-height: 1.3;
}
.version-timeline-note {
  font-size: 11px;
  line-height: 1.35;
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.version-timeline-segment {
  flex: 1 1 48px;
  min-width: 48px;
  align-self: center;
  margin-top: -18px;
  padding: 6px 4px;
  border: none;
  border-top: 2px dashed var(--n-border-color);
  background: transparent;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  color: inherit;
}
.version-timeline-segment.active {
  border-top-color: var(--n-primary-color);
  border-top-style: solid;
}
.version-timeline-segment-label {
  font-size: 11px;
  opacity: 0.85;
  white-space: nowrap;
}
.compare-columns {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  height: 100%;
  display: flex;
  gap: 10px;
  overflow-x: auto;
  align-items: stretch;
  padding-bottom: 2px;
}
.compare-columns > :deep(.doc-panel) {
  flex: 1 1 0;
  min-width: min(260px, 38vw);
}

/* 版本对比 · 2 版：左两栏文档 + 右侧提问 */
.compare-workspace-body--version-pair {
  --compare-aside-width: min(260px, 22vw);
  display: grid;
  grid-template-columns: minmax(0, 1fr) var(--compare-aside-width);
  gap: var(--compare-body-gap);
  align-items: stretch;
}

.compare-workspace-body--version-pair .compare-columns--version-pair {
  min-width: 0;
  min-height: 0;
  max-width: 100%;
  height: 100%;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  overflow: hidden;
  align-items: stretch;
}

.compare-workspace-body--version-pair .compare-columns--version-pair > :deep(.doc-panel) {
  flex: none;
  min-width: 0;
  min-height: 0;
  height: 100%;
}

.compare-aside--version-pair {
  width: 100%;
  max-width: var(--compare-aside-width);
  flex-shrink: 0;
}

.compare-aside--version-pair .aside-card--version-ask {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.compare-aside--version-pair .aside-card--version-ask :deep(.n-card__content) {
  flex: 1;
  min-height: 0;
}

/* 跨文档对比 · 双栏：布局与版本对比 2 版一致 */
.compare-workspace-body--cross-pair {
  --compare-aside-width: min(260px, 22vw);
  display: grid;
  grid-template-columns: minmax(0, 1fr) var(--compare-aside-width);
  gap: var(--compare-body-gap);
  align-items: stretch;
}

.compare-workspace-body--cross-pair .compare-columns--cross-pair {
  min-width: 0;
  min-height: 0;
  max-width: 100%;
  height: 100%;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  overflow: hidden;
  align-items: stretch;
}

.compare-workspace-body--cross-pair .compare-columns--cross-pair > :deep(.doc-panel) {
  flex: none;
  min-width: 0;
  min-height: 0;
  height: 100%;
}

.compare-aside--cross-pair {
  width: 100%;
  max-width: var(--compare-aside-width);
  flex-shrink: 0;
}

/* 版本对比 · 3+ 版：主区网格 + 右侧栏 */
.compare-workspace-body--version-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) var(--compare-aside-width);
  gap: var(--compare-body-gap);
  align-items: stretch;
}

.compare-workspace-body--version-grid .compare-columns--version-grid {
  min-width: 0;
  max-width: 100%;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-auto-rows: minmax(280px, 1fr);
  gap: 10px;
  overflow-x: hidden;
  overflow-y: auto;
  align-content: start;
  align-items: stretch;
}

.compare-workspace-body--version-grid .compare-columns--version-grid > :deep(.doc-panel) {
  flex: none;
  min-width: 0;
  min-height: 280px;
  height: auto;
}

.compare-aside {
  width: var(--compare-aside-width);
  max-width: var(--compare-aside-width);
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
  overflow-y: auto;
  box-sizing: border-box;
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
.version-pair-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
}
.version-pair-row {
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid var(--n-border-color);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.version-pair-row.active {
  border-color: var(--n-primary-color);
  background: var(--platform-accent-muted);
}
.version-pair-row.running {
  opacity: 0.85;
}
.version-pair-summary {
  font-size: 12px;
  line-height: 1.45;
}
.version-summary-label {
  display: block;
  font-size: 11px;
  margin-bottom: 4px;
}
.version-summary-body {
  display: block;
  font-size: 13px;
  line-height: 1.55;
}
.version-summary-body :deep(.md-rich p) {
  margin: 0 0 0.45em;
}
.version-summary-body :deep(.md-rich ul),
.version-summary-body :deep(.md-rich ol) {
  margin: 0.35em 0;
  padding-left: 1.2em;
}
.version-ask-answer {
  font-size: 13px;
  line-height: 1.55;
}
.version-ask-answer :deep(.md-rich p) {
  margin: 0 0 0.45em;
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
.hit-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: min(42vh, 360px);
  overflow-y: auto;
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
  border-color: color-mix(in srgb, var(--platform-accent) 75%, transparent);
  background: color-mix(in srgb, var(--platform-accent) 8%, transparent);
}
.hit-snippet :deep(mark.hl-search) {
  background: color-mix(in srgb, var(--platform-accent) 35%, transparent);
  border-radius: 2px;
  padding: 0 1px;
}
@media (max-width: 900px) {
  .compare-mode-grid {
    grid-template-columns: 1fr;
    max-width: 360px;
  }
  .compare-workspace {
    --compare-aside-width: 100%;
  }
  .compare-workspace-body {
    flex-direction: column;
  }
  .compare-workspace-body--version-pair,
  .compare-workspace-body--version-grid {
    display: flex;
    flex-direction: column;
  }
  .compare-workspace-body--version-pair .compare-columns--version-pair,
  .compare-workspace-body--version-grid .compare-columns--version-grid {
    grid-template-columns: 1fr;
    grid-auto-rows: minmax(260px, auto);
    overflow-y: auto;
  }
  .compare-columns {
    flex-direction: column;
    overflow-x: visible;
    overflow-y: auto;
  }
  .compare-columns > :deep(.doc-panel) {
    min-width: 0;
    min-height: 280px;
  }
  .compare-aside,
  .compare-aside--version-pair {
    width: 100%;
    max-width: 100%;
    flex-direction: column;
    flex-wrap: nowrap;
  }
  .compare-aside--version-pair .aside-card--version-ask {
    flex: none;
  }
  .aside-card {
    flex: none;
    min-width: 0;
    width: 100%;
  }
}
</style>
