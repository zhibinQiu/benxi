<script setup>
import { usePlatformUi } from "../composables/usePlatformUi";
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  NAlert,
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
  NSelect } from "naive-ui";
import {
  AddOutline,
  ArrowBackOutline,
  CloseOutline,
  ChevronDownOutline,
  ChevronUpOutline,
  DocumentsOutline,
  GitCompareOutline,
  LayersOutline,
  SearchOutline,
  FolderOpenOutline,
  OpenOutline,
  RefreshOutline } from "@vicons/ionicons5";
import {
  createCompareJob,
  waitCompareJob,
  fetchCompareDocumentContent,
  fetchCompareDocumentFileBlob,
  getCompareDocumentDownload,
  searchCompareDocuments,
  fetchVersionCompareAdjacent,
  pollVersionCompareAdjacent,
  askVersionCompare,
} from "../api/compare.js";
import { fetchDocument, fetchDocumentFileBlob } from "../api/documents.js";
import CompareDocColumn from "../components/CompareDocColumn.vue";
import CompareDocPicker from "../components/CompareDocPicker.vue";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import {
  MIN_COMPARE_COLS,
  MAX_CROSS_COLS,
  MAX_VERSION_COLS,
  DIFF_TYPE_LABEL as diffTypeLabel,
  DIFF_TYPE_CLASS as diffTypeClass,
  docSideKey,
  docDisplayTitle,
  buildCompareDoc,
  formatTimelineDate,
  isPdfFileName,
  pdfSrcWithPage,
  buildParagraphsFromContent,
  hitPage,
  paraMatchesHit,
  diffAnchorBlocks,
  diffMatchesPara,
} from "../utils/compareDocument.js";

const ui = usePlatformUi();

/** entry | version-setup | cross-setup | workspace */
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
const syncKnowflow = ref(true);
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

const crossDocs = ref([]);
const showCrossAddPicker = ref(false);

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

const canStartVersionCompare = computed(
  () =>
    versionBaseDoc.value &&
    checkedVersionIds.value.length >= MIN_COMPARE_COLS &&
    checkedVersionIds.value.length <= MAX_VERSION_COLS
);

const canStartCrossCompare = computed(
  () =>
    crossDocs.value.length >= MIN_COMPARE_COLS &&
    crossDocs.value.length <= MAX_CROSS_COLS
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
      label: `v${v.version_no}${v.is_current ? "（当前）" : ""} · ${new Date(v.created_at).toLocaleDateString()} · ${v.file_name}${v.change_description ? ` · ${v.change_description.slice(0, 40)}${v.change_description.length > 40 ? "…" : ""}` : ""}`,
    }))
);

const canSearch = computed(
  () => targetDoc.value && searchQuery.value.trim() && !searching.value
);

function columnRoleLabel(index) {
  if (compareMode.value === "version") {
    const no = columns.value[index]?.doc?.version_no;
    return no != null ? `v${no}` : `版本 ${index + 1}`;
  }
  if (index === 0) return "参照";
  if (index === activeTargetIndex.value) {
    return columns.value.length > 2 ? `对比 ${index}` : "对比";
  }
  return `栏 ${index + 1}`;
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

function colHasPdf(col) {
  if (compareMode.value === "version") return false;
  return isPdfFileName(col?.content?.file_name);
}

function colPdfSrc(col, index) {
  const page = index === activeTargetIndex.value ? col.pdfPage : 1;
  return pdfSrcWithPage(col.pdfBaseUrl, page);
}

function colParagraphs(col) {
  return buildParagraphsFromContent(col.content);
}

function colPlainPreview(col) {
  if (!col.content || colHasPdf(col)) return "";
  if (colParagraphs(col).length) return "";
  return col.content.full_text?.trim() || "";
}

function revokeBlobUrl(url) {
  if (url && String(url).startsWith("blob:")) {
    URL.revokeObjectURL(url);
  }
}

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onCompareKeydown);
  columns.value.forEach((col) => revokeBlobUrl(col.content?.preview_url));
});

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

const activeVersionPair = computed(
  () => versionPairRows.value[activePairIndex.value] || null
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
    if (!docId || !docs[docId] || colHasPdf(col)) return;
    col.content = {
      ...(col.content || {}),
      ...docs[docId],
      preview_url: col.content?.preview_url || null};
  });
}

async function hydrateColumn(index) {
  const col = columns.value[index];
  const doc = col?.doc;
  if (!doc?.id) return;
  revokeBlobUrl(col.content?.preview_url);
  col.loading = true;
  try {
    const fileName = doc.file_name || "";
    const versionCompare = compareMode.value === "version" && doc.version_id;
    if (isPdfFileName(fileName) && !versionCompare) {
      let preview_url = null;
      try {
        const blob = doc.version_id
          ? await fetchDocumentFileBlob(doc.id, doc.version_id)
          : await fetchCompareDocumentFileBlob(doc.id);
        preview_url = URL.createObjectURL(blob);
      } catch {
        const dl = await getCompareDocumentDownload(doc.id).catch(() => null);
        preview_url = dl?.download_url || null;
      }
      col.pdfBaseUrl = preview_url ? String(preview_url).split("#")[0] : null;
      col.pdfPage = 1;
      col.content = {
        file_name: fileName,
        preview_url: col.pdfBaseUrl,
        pages: [],
        full_text: ""};
      return;
    }
    col.pdfBaseUrl = null;
    col.pdfPage = 1;
    if (isPdfFileName(fileName) && versionCompare) {
      try {
        const blob = await fetchDocumentFileBlob(doc.id, doc.version_id);
        col.pdfBaseUrl = URL.createObjectURL(blob);
      } catch {
        col.pdfBaseUrl = null;
      }
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
      parse_quality: content.parse_quality,
      warning: content.warning,
      preview_url: col.pdfBaseUrl};
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
        ui.info("差异正在后台预计算，请稍候…");
      }
      rows = await pollVersionCompareAdjacent(docId, versionIds);
    }
    versionPairRows.value = rows;
    syncActivePairRelation();
    if (!silent) {
      const failed = rows.filter((r) => r.status === "failed");
      if (failed.length) {
        ui.warning(failed[0].error_message || "部分版本差异预计算失败");
      }
    }
  } catch (e) {
    if (!silent) ui.warning(e.message);
    try {
      versionPairRows.value = await fetchVersionCompareAdjacent(docId, versionIds);
      syncActivePairRelation();
    } catch {
      /* ignore */
    }
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
    ui.warning("请等待当前版本对比完成");
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
  hydrateAllColumns().then(() => {
    if (compareMode.value === "version") {
      loadPrecomputedVersionTimeline();
    }
  });
}

async function loadVersionDiff({ silent = false } = {}) {
  if (compareMode.value !== "version") return;
  await loadPrecomputedVersionTimeline({ silent });
}

function openVersionSetup() {
  compareMode.value = "version";
  phase.value = "version-setup";
  versionBaseDoc.value = null;
  versionList.value = [];
  checkedVersionIds.value = [];
}

function openCrossSetup() {
  compareMode.value = "cross";
  phase.value = "cross-setup";
  crossDocs.value = [];
}

function goEntry() {
  phase.value = "entry";
  compareMode.value = null;
  resetWorkspaceState();
  versionBaseDoc.value = null;
  versionList.value = [];
  checkedVersionIds.value = [];
  crossDocs.value = [];
}

function goSetupFromWorkspace() {
  resetWorkspaceState();
  phase.value = compareMode.value === "version" ? "version-setup" : "cross-setup";
}

async function onVersionBaseSelected(row) {
  versionBaseDoc.value = row;
  checkedVersionIds.value = [];
  versionLoading.value = true;
  try {
    const doc = await fetchDocument(row.id);
    versionList.value = (doc.versions || []).filter((v) => v.uploaded);
    if (!versionList.value.length) {
      ui.warning("该文档暂无已上传的历史版本");
    } else if (versionList.value.length >= MIN_COMPARE_COLS) {
      checkedVersionIds.value = versionList.value.map((v) => v.id);
    }
  } catch (e) {
    ui.error(e.message);
    versionBaseDoc.value = null;
  } finally {
    versionLoading.value = false;
  }
}

function onVersionCheckUpdate(ids) {
  if (ids.length > MAX_VERSION_COLS) {
    checkedVersionIds.value = ids.slice(-MAX_VERSION_COLS);
    ui.info(`最多选择 ${MAX_VERSION_COLS} 个版本`);
    return;
  }
  checkedVersionIds.value = ids;
}

function startVersionCompare() {
  const count = checkedVersionIds.value.length;
  if (count < MIN_COMPARE_COLS || count > MAX_VERSION_COLS) {
    ui.warning(`请勾选 ${MIN_COMPARE_COLS}–${MAX_VERSION_COLS} 个版本`);
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

function startCrossCompare() {
  if (!canStartCrossCompare.value) {
    ui.warning(`请选择 ${MIN_COMPARE_COLS}–${MAX_CROSS_COLS} 份不同文档`);
    return;
  }
  compareMode.value = "cross";
  initColumnsFromDocs(crossDocs.value.map((d) => buildCompareDoc(d)));
  enterWorkspace();
}

function openPicker(columnIndex) {
  pickerColumnIndex.value = columnIndex;
  showPicker.value = true;
}

function onWorkspaceDocSelect(row) {
  const doc = buildCompareDoc(row);
  const idx = pickerColumnIndex.value;
  if (columns.value[idx]) {
    revokeBlobUrl(columns.value[idx].content?.preview_url);
    columns.value[idx].doc = doc;
    columns.value[idx].content = null;
    columns.value[idx].pdfBaseUrl = null;
    columns.value[idx].pdfPage = 1;
    hydrateColumn(idx);
  }
  if (compareMode.value !== "version") compareMode.value = "cross";
  showPicker.value = false;
  job.value = null;
  versionCompareRelation.value = null;
  searchHits.value = [];
  activeHitIndex.value = -1;
}

function onCrossDocAdd(row) {
  if (crossDocs.value.length >= MAX_CROSS_COLS) {
    ui.info(`最多添加 ${MAX_CROSS_COLS} 份文档`);
    return;
  }
  if (crossDocs.value.some((d) => d.id === row.id)) {
    ui.warning("已添加该文档");
    return;
  }
  crossDocs.value.push(row);
}

function removeCrossDoc(index) {
  crossDocs.value.splice(index, 1);
}

function setColumnScrollRef({ el, index }) {
  if (el) columnScrollRefs.value[index] = el;
}

async function openOriginalPdf(doc) {
  if (!doc?.id) return;
  try {
    if (doc.version_id) {
      const blob = await fetchDocumentFileBlob(doc.id, doc.version_id);
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank");
      window.setTimeout(() => URL.revokeObjectURL(url), 60000);
      return;
    }
    const data = await getCompareDocumentDownload(doc.id);
    if (data?.download_url) window.open(data.download_url, "_blank");
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
      syncKnowflow: syncKnowflow.value});
    job.value =
      created?.status === "pending" || created?.status === "running"
        ? await waitCompareJob(created.id)
        : created;
    if (job.value.status === "failed") {
      ui.error(job.value.error_message || "比对失败");
    } else {
      syncContentFromJob();
      ui.success(
        columns.value.length > 2
          ? `参照与「${docDisplayTitle(targetDoc.value)}」文本差异分析完成`
          : "文本差异分析完成"
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

  if (colHasPdf(col)) {
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
      syncKnowflow: syncKnowflow.value,
      fieldMatch: fieldMatch.value});
    if (!searchHits.value.length) {
      ui.info("未找到匹配内容，可换关键词或关闭字段匹配");
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
  const anchor = d?.anchor_json || {};
  const page =
    anchor.right?.page ||
    anchor.left?.page ||
    (anchor.right_blocks?.[0]?.page ?? anchor.left_blocks?.[0]?.page);
  if (page && targetColumn.value) {
    targetColumn.value.pdfPage = Number(page) || 1;
  }
  for (let i = 0; i < columns.value.length; i += 1) {
    const side = columnDiffSide(i);
    if (side === "none") continue;
    const blocks = diffAnchorBlocks(d, side);
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
          重新选择
        </n-button>
        <n-tag size="small" :bordered="false" type="info">
          {{ compareMode === "version" ? "版本对比" : "跨文档对比" }}
          · {{ columns.length }} 栏
        </n-tag>
        <n-select
          v-if="compareMode === 'cross' && columns.length > 2"
          v-model:value="activeTargetIndex"
          size="small"
          style="width: min(220px, 42vw)"
          :options="targetColumnOptions"
          placeholder="差异/检索目标栏"
        />
        <n-input
          v-model:value="searchQuery"
          size="small"
          placeholder="检索关键词（在目标栏）"
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
          检索
        </n-button>
        <n-checkbox v-model:checked="fieldMatch" size="small">字段匹配</n-checkbox>
        <n-checkbox v-model:checked="syncKnowflow" size="small">向量检索</n-checkbox>
        <n-button
          v-if="compareMode === 'cross'"
          size="small"
          secondary
          :disabled="!canCompare"
          :loading="comparing"
          @click="runCompare"
        >
          <template #icon>
            <n-icon :component="RefreshOutline" />
          </template>
          开始对比
        </n-button>
        <n-button
          v-if="compareMode === 'version'"
          size="small"
          secondary
          :loading="comparing"
          @click="loadPrecomputedVersionTimeline()"
        >
          <template #icon>
            <n-icon :component="RefreshOutline" />
          </template>
          刷新差异
        </n-button>
      </n-space>
    </template>

    <!-- 入口：选择对比模式 -->
    <div v-if="phase === 'entry'" class="compare-entry">
      <div class="compare-mode-grid">
        <n-card class="compare-mode-card" hoverable @click="openVersionSetup">
          <div class="compare-mode-icon compare-mode-icon--version">
            <n-icon :component="LayersOutline" :size="28" />
          </div>
          <n-text class="compare-mode-title">文档版本对比</n-text>
        </n-card>
        <n-card class="compare-mode-card" hoverable @click="openCrossSetup">
          <div class="compare-mode-icon compare-mode-icon--cross">
            <n-icon :component="DocumentsOutline" :size="28" />
          </div>
          <n-text class="compare-mode-title">不同文档对比</n-text>
        </n-card>
      </div>
    </div>

    <!-- 文档版本对比：选文档 + 勾选版本 -->
    <div v-else-if="phase === 'version-setup'" class="compare-setup">
      <n-button size="small" quaternary class="compare-setup-back" @click="goEntry">
        <template #icon>
          <n-icon :component="ArrowBackOutline" />
        </template>
        返回
      </n-button>
      <n-card title="文档版本对比" class="compare-setup-card">
        <n-space vertical :size="16">
          <div>
            <n-text depth="3" style="font-size: 12px; display: block; margin-bottom: 8px">
              1. 选择文档
            </n-text>
            <n-space align="center" :size="10" wrap>
              <n-text v-if="versionBaseDoc" class="compare-selected-doc">
                {{ versionBaseDoc.title }}
                <n-text depth="3">（{{ versionBaseDoc.file_name }}）</n-text>
              </n-text>
              <n-text v-else depth="3">尚未选择</n-text>
              <n-button size="small" secondary @click="showVersionDocPicker = true">
                <template #icon>
                  <n-icon :component="FolderOpenOutline" />
                </template>
                {{ versionBaseDoc ? "更换文档" : "从文档库选择" }}
              </n-button>
            </n-space>
          </div>

          <div v-if="versionBaseDoc">
            <n-text depth="3" style="font-size: 12px; display: block; margin-bottom: 8px">
              2. 选择版本（已选 {{ checkedVersionIds.length }} / {{ MAX_VERSION_COLS }}）
            </n-text>
            <n-spin :show="versionLoading">
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
              <n-empty v-else description="该文档暂无已上传版本" size="small" />
            </n-spin>
          </div>

          <n-space>
            <n-button
              type="primary"
              :disabled="!canStartVersionCompare"
              @click="startVersionCompare"
            >
              <template #icon>
                <n-icon :component="GitCompareOutline" />
              </template>
              查看版本变化
            </n-button>
          </n-space>
        </n-space>
      </n-card>
    </div>

    <!-- 不同文档对比：选参照 + 目标 -->
    <div v-else-if="phase === 'cross-setup'" class="compare-setup">
      <n-button size="small" quaternary class="compare-setup-back" @click="goEntry">
        <template #icon>
          <n-icon :component="ArrowBackOutline" />
        </template>
        返回
      </n-button>
      <n-card title="不同文档对比" class="compare-setup-card">
        <n-space vertical :size="16">
          <n-text depth="3" style="font-size: 12px">
            从文档库添加 2–4 份文档；第一栏为参照，其余栏从左到右排列。
          </n-text>
          <div v-if="crossDocs.length" class="compare-doc-list">
            <div
              v-for="(doc, index) in crossDocs"
              :key="doc.id"
              class="compare-doc-list-item"
            >
              <n-tag size="small" :bordered="false" :type="index === 0 ? 'info' : 'default'">
                {{ index === 0 ? "参照" : `对比 ${index}` }}
              </n-tag>
              <n-text class="compare-selected-doc">{{ doc.title }}</n-text>
              <n-text depth="3" style="font-size: 12px">{{ doc.file_name }}</n-text>
              <n-button
                size="tiny"
                quaternary
                circle
                :disabled="crossDocs.length <= MIN_COMPARE_COLS"
                @click="removeCrossDoc(index)"
              >
                <template #icon>
                  <n-icon :component="CloseOutline" />
                </template>
              </n-button>
            </div>
          </div>
          <n-empty v-else description="尚未添加文档" size="small" />
          <n-space>
            <n-button
              size="small"
              secondary
              :disabled="crossDocs.length >= MAX_CROSS_COLS"
              @click="showCrossAddPicker = true"
            >
              <template #icon>
                <n-icon :component="AddOutline" />
              </template>
              添加文档（{{ crossDocs.length }}/{{ MAX_CROSS_COLS }}）
            </n-button>
            <n-button type="primary" :disabled="!canStartCrossCompare" @click="startCrossCompare">
              <template #icon>
                <n-icon :component="GitCompareOutline" />
              </template>
              开始对比
            </n-button>
          </n-space>
        </n-space>
      </n-card>
    </div>

    <!-- 对比工作台 -->
    <div v-else class="compare-workspace">
      <n-card
        v-if="compareMode === 'version' && columns.length >= 2"
        size="small"
        class="version-timeline-card"
        title="版本时间线"
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
                    ? `${versionPairRows[i].diff_count || 0} 处`
                    : versionPairRows[i].status === "failed"
                      ? "失败"
                      : "…"
                }}
              </n-tag>
            </button>
          </template>
        </div>
      </n-card>

      <div class="compare-workspace-body">
      <div class="compare-columns" :class="`compare-columns--${columns.length}`">
        <CompareDocColumn
          v-for="(col, index) in columns"
          :key="docSideKey(col.doc)"
          :column-index="index"
          :doc="col.doc"
          :content="col.content"
          :loading="col.loading"
          :comparing="comparing"
          :pdf-src="colPdfSrc(col, index)"
          :role-label="columnRoleLabel(index)"
          :is-baseline="index === 0"
          :is-search-target="index === activeTargetIndex"
          :diff-side="columnDiffSide(index)"
          :paragraphs="colParagraphs(col)"
          :plain-preview="colPlainPreview(col)"
          :has-pdf="colHasPdf(col)"
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
          @prev-hit="goPrevHit"
          @next-hit="goNextHit"
        />
      </div>

      <aside
        v-if="searchHits.length || showDiffAside || versionCompareRunning"
        class="compare-aside"
      >
        <n-card
          v-if="compareMode === 'version' && activeVersionPair?.status === 'done'"
          size="small"
          title="变化摘要"
          class="aside-card version-summary-card"
        >
          <n-space vertical :size="10">
            <div v-if="activeVersionPair.to_change_description">
              <n-text depth="3" class="version-summary-label">新版本说明</n-text>
              <n-text class="version-summary-body">{{ activeVersionPair.to_change_description }}</n-text>
            </div>
            <div v-if="activeVersionPair.llm_summary">
              <n-text depth="3" class="version-summary-label">AI 差异总结</n-text>
              <n-text class="version-summary-body">{{ activeVersionPair.llm_summary }}</n-text>
            </div>
            <n-text
              v-if="!activeVersionPair.to_change_description && !activeVersionPair.llm_summary"
              depth="3"
            >
              该版本对暂无说明或总结
            </n-text>
          </n-space>
        </n-card>

        <n-card
          v-if="compareMode === 'version' && versionPairRows.length"
          size="small"
          title="时间线变化"
          class="aside-card"
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
                  {{ row.status === "done" ? `${row.diff_count || 0} 处` : row.status === "failed" ? "失败" : "对比中" }}
                </n-tag>
              </n-space>
              <n-text v-if="row.to_change_description" depth="3" class="version-pair-summary">
                版本说明：{{ row.to_change_description.slice(0, 120) }}{{ row.to_change_description.length > 120 ? "…" : "" }}
              </n-text>
              <n-text v-if="row.llm_summary" depth="3" class="version-pair-summary">
                {{ row.llm_summary.slice(0, 160) }}{{ row.llm_summary.length > 160 ? "…" : "" }}
              </n-text>
            </div>
          </div>
        </n-card>

        <n-card
          v-if="compareMode === 'version' && versionCompareRelation?.status === 'done'"
          size="small"
          title="差异问答"
          class="aside-card"
        >
          <n-space vertical :size="8">
            <n-input
              v-model:value="versionAskQuery"
              type="textarea"
              placeholder="例如：第二版相对第一版改了哪些关键数据？"
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
              提问
            </n-button>
            <n-text v-if="versionAskAnswer" class="version-ask-answer">{{ versionAskAnswer }}</n-text>
          </n-space>
        </n-card>

        <n-card
          v-if="versionCompareRunning"
          size="small"
          title="版本对比"
          class="aside-card"
        >
          <n-text depth="3">正在等待上传时预计算的版本差异…</n-text>
        </n-card>

        <n-card
          v-if="showDiffAside"
          size="small"
          title="差异列表"
          class="aside-card"
        >
          <n-text depth="3" class="aside-hint">
            <template v-if="compareMode === 'version' && versionCompareRelation">
              v{{ versionCompareRelation.from_version_no }} → v{{ versionCompareRelation.to_version_no }}：
              共 {{ diffItems.length }} 处差异
            </template>
            <template v-else>
              共 {{ diffItems.length }} 处差异（参照栏 vs {{ docDisplayTitle(targetDoc) }}）
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
              <n-tag size="small" :bordered="false">{{ diffTypeLabel[d.diff_type] || d.diff_type }}</n-tag>
              <n-text class="diff-snippet" depth="2">
                {{ (d.text_right || d.text_left || "").slice(0, 120) }}
              </n-text>
            </div>
            <n-text v-if="!diffItems.length" depth="3">未发现文本差异</n-text>
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
    </div>

    <CompareDocPicker
      v-model:show="showVersionDocPicker"
      title="选择要比对的文档"
      @select="onVersionBaseSelected"
    />
    <CompareDocPicker
      v-model:show="showCrossAddPicker"
      title="添加对比文档"
      :exclude-ids="crossDocs.map((d) => d.id)"
      @select="onCrossDocAdd"
    />
    <CompareDocPicker
      v-model:show="showPicker"
      title="更换文档"
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
  color: #2563eb;
}
.compare-mode-icon--cross {
  background: rgba(139, 92, 246, 0.15);
  color: #7c3aed;
}
.compare-mode-title {
  font-size: 16px;
  font-weight: 600;
}
.compare-mode-desc {
  font-size: 12px;
  line-height: 1.55;
}
.compare-setup {
  flex: 1;
  min-height: 0;
  padding: 8px 0 16px;
  max-width: 640px;
}
.compare-setup-back {
  margin-bottom: 10px;
}
.compare-setup-card {
  box-shadow: var(--platform-shadow);
}
.compare-selected-doc {
  font-size: 14px;
  font-weight: 500;
}
.compare-pick-row {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.compare-pick-label {
  font-size: 12px;
}
.compare-doc-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.compare-doc-list-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid var(--platform-border, rgba(15, 23, 42, 0.08));
  background: rgba(248, 250, 252, 0.6);
}
.compare-doc-list-item .compare-selected-doc {
  flex: 1;
  min-width: 0;
}
.compare-workspace {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow: hidden;
}
.compare-workspace-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: row;
  gap: 10px;
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
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  gap: 10px;
  overflow-x: auto;
  align-items: stretch;
  padding-bottom: 2px;
}
.compare-columns > :deep(.doc-panel) {
  flex: 1 1 0;
  min-width: min(300px, 78vw);
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
  white-space: pre-wrap;
}
.version-ask-answer {
  font-size: 13px;
  line-height: 1.55;
  white-space: pre-wrap;
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
  border-color: rgba(139, 92, 246, 0.75);
  background: rgba(139, 92, 246, 0.08);
}
.hit-snippet :deep(mark.hl-search) {
  background: rgba(139, 92, 246, 0.35);
  border-radius: 2px;
  padding: 0 1px;
}
@media (max-width: 900px) {
  .compare-mode-grid {
    grid-template-columns: 1fr;
    max-width: 360px;
  }
  .compare-workspace {
    flex-direction: column;
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
