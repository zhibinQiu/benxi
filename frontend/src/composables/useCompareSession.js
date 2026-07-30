import {
  computed,
  onActivated,
  onBeforeUnmount,
  onDeactivated,
  ref,
  watch,
} from "vue";
import { fetchCompareJob } from "../api/compare.js";
import {
  MIN_COMPARE_COLS,
  docDisplayTitle,
} from "../utils/compareDocument.js";
import {
  clearCompareViewSession,
  loadCompareViewSession,
  saveCompareViewSession,
} from "../utils/compareViewPersist.js";

/**
 * 文档对比页：列状态、sessionStorage 持久化与路由/缓存恢复。
 */
export function useCompareSession({
  route,
  router,
  t,
  phase,
  compareMode,
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
  hydrateAllColumns,
  loadPrecomputedVersionTimeline,
  syncActivePairRelation,
  syncContentFromJob,
  prepareVersionCompare,
  revokeColumnBlobUrls,
}) {
  /** @type {import('vue').Ref<Array<{ doc: object, content: object|null, loading: boolean, pdfBaseUrl: string|null, pdfPage: number }>>} */
  const columns = ref([]);
  const activeTargetIndex = ref(1);
  const columnScrollRefs = ref({});

  let skipComparePersist = false;
  let comparePersistTimer = null;

  const baselineColumn = computed(() => columns.value[0] || null);
  const targetColumn = computed(() => columns.value[activeTargetIndex.value] || null);
  const baselineDoc = computed(() => baselineColumn.value?.doc || null);
  const targetDoc = computed(() => targetColumn.value?.doc || null);

  const targetColumnOptions = computed(() =>
    columns.value.slice(1).map((col, i) => ({
      label: `${columnRoleLabel(i + 1)} · ${docDisplayTitle(col.doc)}`,
      value: i + 1,
    }))
  );

  function columnRoleLabel(index) {
    if (compareMode.value === "version") {
      const no = columns.value[index]?.doc?.version_no;
      return no != null ? `v${no}` : t("compare.roleVersion", { index: index + 1 });
    }
    if (compareMode.value === "cross") {
      const doc = columns.value[index]?.doc;
      if (doc?.version_no != null && columns.value.length === 2) {
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

  function initColumnsFromDocs(docs) {
    columns.value = docs.map((doc) => ({
      doc,
      content: null,
      loading: false,
      pdfBaseUrl: null,
      pdfPage: 1,
    }));
    activeTargetIndex.value = docs.length > 1 ? 1 : 0;
    columnScrollRefs.value = {};
  }

  function resetWorkspaceState() {
    revokeColumnBlobUrls(columns.value);
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

  function setColumnScrollRef({ el, index }) {
    if (el) columnScrollRefs.value[index] = el;
  }

  function setColumnPdfPage(index, page) {
    const col = columns.value[index];
    if (!col) return;
    col.pdfPage = Math.max(1, Number(page) || 1);
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

  function clearCompareSession() {
    clearCompareViewSession();
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

  watch(
    () => [route.query.mode, route.query.documentId],
    () => {
      void initCompareViewFromRouteOrSession();
    }
  );

  onDeactivated(() => {
    flushComparePersist();
  });

  onActivated(() => {
    scheduleComparePersist();
  });

  onBeforeUnmount(() => {
    revokeColumnBlobUrls(columns.value);
    flushComparePersist();
  });

  return {
    columns,
    activeTargetIndex,
    columnScrollRefs,
    baselineColumn,
    targetColumn,
    baselineDoc,
    targetDoc,
    targetColumnOptions,
    columnRoleLabel,
    initColumnsFromDocs,
    resetWorkspaceState,
    setColumnScrollRef,
    setColumnPdfPage,
    initCompareViewFromRouteOrSession,
    clearCompareSession,
    flushComparePersist,
    scheduleComparePersist,
  };
}
