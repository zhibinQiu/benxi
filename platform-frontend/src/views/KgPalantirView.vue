<script setup>
defineOptions({ name: "KgPalantirView" });
import { usePlatformUi } from "../composables/usePlatformUi";
import { useI18n } from "../composables/useI18n";
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  NButton,
  NEmpty,
  NForm,
  NFormItem,
  NInput,
  NSelect,
  NSpace,
  NSpin,
  NTabPane,
  NTabs,
  NTag,
} from "naive-ui";
import AdminFormModal from "../components/AdminFormModal.vue";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import KgEntityListPanel from "../components/kg/KgEntityListPanel.vue";
import KgPalantirStats from "../components/kg/KgPalantirStats.vue";
import KgGraphCanvas from "../components/KgGraphCanvas.vue";
import ListRefreshButton from "../components/ListRefreshButton.vue";
import {
  createKgEntity,
  createKgEntityType,
  createKgRelation,
  createKgRelationType,
  batchDeleteKgEntities,
  clearKgGraph,
  deleteKgEntity,
  deleteKgEntityType,
  deleteKgRelation,
  deleteKgRelationType,
  fetchKgEntity,
  fetchKgEntities,
  fetchKgGraph,
  fetchKgMeta,
  fetchKgRelations,
  extractKgBatch,
  updateKgEntity,
  updateKgEntityType,
  updateKgRelationType,
} from "../api/kg.js";
import {
  clearKgPalantirCache,
  isKgEntityListCacheFresh,
  isKgGraphCacheFresh,
  isKgPalantirMetaCacheFresh,
  readKgEntityListCache,
  readKgGraphCache,
  readKgMetaCache,
  writeKgEntityListCache,
  writeKgGraphCache,
  writeKgMetaCache,
} from "../utils/kgPalantirCache.js";
import { LIST_PAGE_SIZE } from "../constants/listPage.js";

const ui = usePlatformUi();
const { t } = useI18n();
const route = useRoute();
const router = useRouter();

const ENTITY_PAGE_SIZE = LIST_PAGE_SIZE;

const TYPE_COLORS = {
  blue: "#0067ff",
  cyan: "#2AA8C8",
  green: "#1F8A65",
  teal: "#1F9E8F",
  purple: "#7B64B8",
  indigo: "#5B6FD6",
  orange: "#F0A040",
  pink: "#C85898",
  yellow: "#E8C030",
  gray: "#8888A8",
};

const loading = ref(true);
const listLoading = ref(false);
const meta = ref(null);
const graph = ref({ nodes: [], edges: [] });
const relations = ref([]);
const selectedId = ref(null);
const filterTypeId = ref(null);
const searchQ = ref("");
const graphDepth = ref(1);
const leftTab = ref("entities");
const entityList = ref([]);
const graphCanvasRef = ref(null);
const detailMainRef = ref(null);
const detailRelListRef = ref(null);
const browseTypeId = ref(null);
const browseTypeEntities = ref([]);
const browseTypeLoading = ref(false);
const browseRelationTypeId = ref(null);
const entityPage = ref(1);
const checkedEntityIds = ref([]);

const entityModal = ref(false);
const entityForm = ref({ type_id: null, name: "", description: "" });
const editingEntityId = ref(null);

const relationModal = ref(false);
const relationForm = ref({
  relation_type_id: null,
  from_entity_id: null,
  to_entity_id: null,
  description: "",
});

const entityTypeModal = ref(false);
const entityTypeForm = ref({ code: "", label: "", color: "blue", description: "" });
const editingEntityTypeId = ref(null);

const relationTypeModal = ref(false);
const relationTypeForm = ref({ code: "", label: "", description: "" });
const editingRelationTypeId = ref(null);

const entityDetail = ref(null);
const detailRefreshing = ref(false);
const extractingKnowledge = ref(false);
const extractingPlatform = ref(false);

let searchTimer = null;

function normalizeKgId(id) {
  if (id == null || id === "") return null;
  return String(id);
}

function idEq(a, b) {
  if (a == null || b == null) return false;
  return normalizeKgId(a) === normalizeKgId(b);
}

const selectedEntity = computed(() => {
  const sid = normalizeKgId(selectedId.value);
  if (!sid) return null;
  return (
    graph.value.nodes?.find((n) => idEq(n.id, sid)) ||
    entityList.value.find((n) => idEq(n.id, sid)) ||
    browseTypeEntities.value.find((n) => idEq(n.id, sid)) ||
    (entityDetail.value && idEq(entityDetail.value.id, sid) ? entityDetail.value : null) ||
    null
  );
});

const entityTypeOptions = computed(() =>
  (meta.value?.entity_types || []).map((t) => ({
    label: t.label,
    value: t.id,
  }))
);

const relationTypeOptions = computed(() =>
  (meta.value?.relation_types || []).map((t) => ({
    label: t.label,
    value: t.id,
  }))
);

const entityOptions = computed(() =>
  entityList.value.map((n) => ({
    label: n.name,
    value: n.id,
  }))
);

const typeFilterOptions = computed(() => [
  { label: t("kgPalantir.allTypes"), value: null },
  ...(meta.value?.entity_types || []).map((item) => ({
    label: `${item.label} (${item.entity_count})`,
    value: item.id,
  })),
]);

const graphDepthOptions = computed(() => [
  { label: t("kgPalantir.subgraph1Hop"), value: 1 },
  { label: t("kgPalantir.subgraph2Hop"), value: 2 },
]);

const browseTypeMeta = computed(() =>
  (meta.value?.entity_types || []).find((t) => idEq(t.id, browseTypeId.value)) || null
);

const browseRelationTypeMeta = computed(() =>
  (meta.value?.relation_types || []).find((t) => idEq(t.id, browseRelationTypeId.value)) || null
);

const entityPageCount = computed(() =>
  Math.max(1, Math.ceil(entityList.value.length / ENTITY_PAGE_SIZE))
);

const paginatedEntityList = computed(() => {
  const start = (entityPage.value - 1) * ENTITY_PAGE_SIZE;
  return entityList.value.slice(start, start + ENTITY_PAGE_SIZE);
});

const isTypeBrowseMode = computed(
  () => Boolean(browseTypeId.value && browseTypeMeta.value && !selectedEntity.value)
);

const hasAnyEntities = computed(
  () => (meta.value?.entity_total || 0) > 0 || entityList.value.length > 0
);

function clearGraph() {
  graph.value = { nodes: [], edges: [] };
}

const graphLayout = computed(() => {
  let nodes = graph.value.nodes || [];
  const edges = graph.value.edges || [];

  if (!nodes.length && selectedId.value) {
    const fallback = selectedEntity.value;
    if (fallback) {
      nodes = [
        {
          id: fallback.id,
          name: fallback.name,
          type_code: fallback.type_code || "unknown",
          type_label: fallback.type_label || t("kgPalantir.entity"),
          type_color: fallback.type_color || "gray",
        },
      ];
    }
  }

  if (!nodes.length) return { nodes: [], edges: [], width: 400, height: 200 };

  const idSet = new Set(nodes.map((n) => normalizeKgId(n.id)));
  const adj = new Map();
  for (const n of nodes) adj.set(normalizeKgId(n.id), []);
  for (const e of edges) {
    const from = normalizeKgId(e.from_entity_id);
    const to = normalizeKgId(e.to_entity_id);
    if (idSet.has(from) && idSet.has(to)) {
      adj.get(from).push(to);
      adj.get(to).push(from);
    }
  }

  const ranks = new Map();
  const start = normalizeKgId(selectedId.value) || normalizeKgId(nodes[0]?.id);
  if (start) {
    const queue = [{ id: start, rank: 0 }];
    const seen = new Set([start]);
    while (queue.length) {
      const { id, rank } = queue.shift();
      ranks.set(id, rank);
      for (const next of adj.get(id) || []) {
        if (!seen.has(next)) {
          seen.add(next);
          queue.push({ id: next, rank: rank + 1 });
        }
      }
    }
  }
  let maxRank = 0;
  for (const n of nodes) {
    const nid = normalizeKgId(n.id);
    const r = ranks.get(nid) ?? 0;
    maxRank = Math.max(maxRank, r);
    if (!ranks.has(nid)) ranks.set(nid, 0);
  }

  const byRank = new Map();
  for (const n of nodes) {
    const r = ranks.get(normalizeKgId(n.id)) ?? 0;
    if (!byRank.has(r)) byRank.set(r, []);
    byRank.get(r).push(n);
  }

  const nodeW = 148;
  const nodeH = 40;
  const rankGap = 88;
  const nodeGap = 28;
  const padding = 32;

  const positioned = [];
  for (let r = 0; r <= maxRank; r += 1) {
    const row = byRank.get(r) || [];
    row.sort((a, b) => a.name.localeCompare(b.name, "zh-CN"));
    let x = padding;
    const y = padding + r * (nodeH + rankGap);
    for (const n of row) {
      positioned.push({ ...n, x, y, w: nodeW, h: nodeH });
      x += nodeW + nodeGap;
    }
  }

  const width = Math.max(...positioned.map((n) => n.x + n.w), 360) + padding;
  const height = Math.max(...positioned.map((n) => n.y + n.h), 160) + padding;

  const edgeLines = edges.filter(
    (e) =>
      positioned.some((n) => idEq(n.id, e.from_entity_id)) &&
      positioned.some((n) => idEq(n.id, e.to_entity_id))
  );

  return { nodes: positioned, edges: edgeLines, width, height };
});

async function centerGraphOnSelection() {
  await nextTick();
  await new Promise((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(resolve));
  });
  graphCanvasRef.value?.centerOnSelection?.();
}

function scrollDetailPanelToTop() {
  nextTick(() => {
    detailMainRef.value?.scrollTo?.({ top: 0, behavior: "smooth" });
    detailRelListRef.value?.scrollTo?.({ top: 0, behavior: "smooth" });
  });
}

async function loadEntityList({ resetPage = true, background = false } = {}) {
  if (!background) listLoading.value = true;
  try {
    const data = await fetchKgEntities({
      typeId: filterTypeId.value || undefined,
      q: searchQ.value.trim() || undefined,
    });
    entityList.value = data;
    writeKgEntityListCache(filterTypeId.value, searchQ.value, data);
    if (resetPage) {
      entityPage.value = 1;
      checkedEntityIds.value = [];
    }
  } catch (e) {
    if (!background) ui.error(e.message);
  } finally {
    if (!background) listLoading.value = false;
  }
}

async function loadBrowseByType(typeId) {
  if (!typeId) {
    clearBrowseType();
    return;
  }
  browseTypeId.value = typeId;
  browseTypeLoading.value = true;
  try {
    browseTypeEntities.value = await fetchKgEntities({ typeId });
  } catch (e) {
    ui.error(e.message);
  } finally {
    browseTypeLoading.value = false;
  }
}

function clearBrowseType() {
  if (filterTypeId.value && idEq(filterTypeId.value, browseTypeId.value)) {
    filterTypeId.value = null;
  }
  browseTypeId.value = null;
  browseTypeEntities.value = [];
}

function clearBrowseRelationType() {
  browseRelationTypeId.value = null;
}

async function browseEntityType(typeId) {
  if (idEq(browseTypeId.value, typeId)) {
    clearBrowseType();
    return;
  }
  browseRelationTypeId.value = null;
  selectedId.value = null;
  entityDetail.value = null;
  relations.value = [];
  clearGraph();
  await loadBrowseByType(typeId);
}

function browseRelationType(typeId) {
  if (idEq(browseRelationTypeId.value, typeId)) {
    clearBrowseRelationType();
    return;
  }
  clearBrowseType();
  browseRelationTypeId.value = typeId;
  selectedId.value = null;
  entityDetail.value = null;
  relations.value = [];
  clearGraph();
  scrollDetailPanelToTop();
}

function hydrateFromCache() {
  let ready = false;
  const cachedMeta = readKgMetaCache({ allowStale: true });
  if (cachedMeta) {
    meta.value = cachedMeta;
    ready = true;
  }

  const cachedList = readKgEntityListCache(filterTypeId.value, searchQ.value, {
    allowStale: true,
  });
  if (cachedList !== null) {
    entityList.value = cachedList;
    ready = ready && true;
  } else {
    ready = false;
  }

  const sid = normalizeKgId(selectedId.value);
  if (sid) {
    const cachedGraph = readKgGraphCache(sid, graphDepth.value, { allowStale: true });
    if (cachedGraph?.graph) {
      graph.value = cachedGraph.graph;
      if (cachedGraph.relations) relations.value = cachedGraph.relations;
    }
  }

  return ready;
}

async function loadAll() {
  const hadCache = hydrateFromCache();
  if (hadCache) {
    loading.value = false;
    void centerGraphOnSelection();
    void refreshAll({ background: true });
    return;
  }
  await refreshAll({ fullPage: true, syncMeta: false });
}

async function loadSelectionGraph({ force = false, background = false } = {}) {
  const sid = normalizeKgId(selectedId.value);
  if (!sid) {
    clearGraph();
    relations.value = [];
    return;
  }

  if (!force) {
    const cached = readKgGraphCache(sid, graphDepth.value, { allowStale: true });
    if (cached?.graph) {
      graph.value = cached.graph;
      if (cached.relations) relations.value = cached.relations;
      await centerGraphOnSelection();
      if (!isKgGraphCacheFresh(sid, graphDepth.value)) {
        void loadSelectionGraph({ force: true, background: true });
      }
      return;
    }
  }

  if (!background) detailRefreshing.value = true;
  try {
    const [graphData, relData] = await Promise.all([
      fetchKgGraph({ focusEntityId: sid, depth: graphDepth.value }),
      fetchKgRelations({ entityId: sid }),
    ]);
    graph.value = graphData;
    relations.value = relData;
    writeKgGraphCache(sid, graphDepth.value, {
      graph: graphData,
      relations: relData,
    });

    if (!entityDetail.value || !idEq(entityDetail.value.id, sid)) {
      try {
        entityDetail.value = await fetchKgEntity(sid);
      } catch {
        const listItem = entityList.value.find((n) => idEq(n.id, sid))
          || browseTypeEntities.value.find((n) => idEq(n.id, sid));
        if (listItem) entityDetail.value = { ...listItem };
      }
    }

    await centerGraphOnSelection();
  } catch (e) {
    if (!background) ui.error(e.message);
  } finally {
    if (!background) detailRefreshing.value = false;
  }
}

async function refreshAll({
  toast = false,
  fullPage = false,
  syncMeta = false,
  background = false,
  force = false,
} = {}) {
  const sid = normalizeKgId(selectedId.value);
  const activeBrowseTypeId = browseTypeId.value;
  const prevEntityPage = entityPage.value;
  const hasShell =
    Boolean(meta.value) &&
    readKgEntityListCache(filterTypeId.value, searchQ.value, { allowStale: true }) !== null;

  if (fullPage && !background && !hasShell) loading.value = true;
  else if (!background && !hasShell) detailRefreshing.value = true;

  try {
    if (syncMeta) {
      meta.value = await fetchKgMeta({ syncSystem: true });
      writeKgMetaCache(meta.value);
    } else if (!meta.value || force || !isKgPalantirMetaCacheFresh()) {
      meta.value = await fetchKgMeta({ syncSystem: false });
      writeKgMetaCache(meta.value);
    }

    const cachedList = readKgEntityListCache(filterTypeId.value, searchQ.value, {
      allowStale: true,
    });
    if (force || cachedList === null) {
      await loadEntityList({ resetPage: false, background });
    } else if (!isKgEntityListCacheFresh(filterTypeId.value, searchQ.value)) {
      void loadEntityList({ resetPage: false, background: true });
    }
    entityPage.value = Math.min(prevEntityPage, entityPageCount.value);

    if (activeBrowseTypeId) {
      browseTypeLoading.value = true;
      try {
        browseTypeEntities.value = await fetchKgEntities({ typeId: activeBrowseTypeId });
      } finally {
        browseTypeLoading.value = false;
      }
    }

    if (sid) {
      await loadSelectionGraph({ force, background });
    } else {
      clearGraph();
      relations.value = [];
      entityDetail.value = null;
    }

    if (toast) ui.success(t("kgPalantir.messages.refreshed"));
  } catch (e) {
    if (!background) ui.error(e.message);
  } finally {
    detailRefreshing.value = false;
    if (fullPage) loading.value = false;
  }
}

async function refreshGraph() {
  await loadSelectionGraph({ force: true });
}

function selectEntity(id) {
  const nid = normalizeKgId(id);
  if (idEq(selectedId.value, nid)) {
    centerGraphOnSelection();
    scrollDetailPanelToTop();
    return;
  }
  browseRelationTypeId.value = null;
  const listItem = entityList.value.find((n) => idEq(n.id, nid))
    || browseTypeEntities.value.find((n) => idEq(n.id, nid));
  const graphNode = graph.value.nodes?.find((n) => idEq(n.id, nid));
  if (listItem) {
    entityDetail.value = { ...listItem };
  } else if (graphNode) {
    entityDetail.value = { ...graphNode };
  }
  selectedId.value = nid;
  scrollDetailPanelToTop();
  loadSelectionGraph();
}

function openCreateEntity() {
  editingEntityId.value = null;
  entityForm.value = {
    type_id: filterTypeId.value || entityTypeOptions.value[0]?.value || null,
    name: "",
    description: "",
  };
  entityModal.value = true;
}

async function openEditEntity() {
  if (!selectedId.value) return;
  try {
    const full = await fetchKgEntity(selectedId.value);
    editingEntityId.value = selectedId.value;
    entityForm.value = {
      type_id: full.type_id,
      name: full.name,
      description: full.description || "",
    };
    entityModal.value = true;
  } catch (e) {
    ui.error(e.message);
  }
}

async function saveEntity() {
  if (!entityForm.value.name?.trim()) {
    ui.warning(t("kgPalantir.messages.enterEntityName"));
    return;
  }
  try {
    if (editingEntityId.value) {
      await updateKgEntity(editingEntityId.value, {
        type_id: entityForm.value.type_id,
        name: entityForm.value.name.trim(),
        description: entityForm.value.description || "",
      });
      ui.success(t("kgPalantir.messages.entityUpdated"));
    } else {
      const created = await createKgEntity({
        type_id: entityForm.value.type_id,
        name: entityForm.value.name.trim(),
        description: entityForm.value.description || "",
      });
      selectedId.value = created.id;
      ui.success(t("kgPalantir.messages.entityCreated"));
    }
    entityModal.value = false;
    await refreshAfterMutation();
  } catch (e) {
    ui.error(e.message);
  }
}

async function refreshAfterMutation() {
  clearKgPalantirCache();
  await refreshAll();
}

async function forceRefreshAll({ toast = false } = {}) {
  clearKgPalantirCache();
  await refreshAll({ toast, syncMeta: true });
}

async function runBatchExtract(scope) {
  if (scope === "knowledge") {
    ui.confirmAction({
      title: t("kgPalantir.confirmExtractKnowledgeTitle"),
      content: t("kgPalantir.confirmExtractKnowledgeContent", {
        count: meta.value?.entity_total || 0,
      }),
      positiveText: t("kgPalantir.extractKnowledge"),
      onPositive: () => executeBatchExtract(scope),
    });
    return;
  }
  await executeBatchExtract(scope);
}

async function executeBatchExtract(scope) {
  const loadingRef = scope === "knowledge" ? extractingKnowledge : extractingPlatform;
  if (loadingRef.value) return;
  loadingRef.value = true;
  try {
    const result = await extractKgBatch({ scope, force: false });
    if (!result?.queued) {
      if (result?.reason === "all_extracted") {
        ui.info(
          t("kgPalantir.messages.extractAllDone", {
            count: result.already_extracted_count ?? 0,
          })
        );
        return;
      }
      ui.warning(t("kgPalantir.messages.extractNothingPending"));
      return;
    }
    const pending = result?.document_count ?? 0;
    const skipped = result?.already_extracted_count ?? 0;
    const key =
      scope === "knowledge"
        ? "kgPalantir.messages.extractKnowledgeQueued"
        : "kgPalantir.messages.extractPlatformQueued";
    ui.success(t(key, { count: pending, skipped }));
    checkedEntityIds.value = [];
    selectedId.value = null;
    await refreshAfterMutation();
  } catch (e) {
    ui.error(e.message);
  } finally {
    loadingRef.value = false;
  }
}

async function deleteCheckedEntities() {
  if (!checkedEntityIds.value.length) return;
  ui.confirmDelete({
    title: t("common.batchDelete"),
    content: t("kgPalantir.confirmDeleteSelected", { count: checkedEntityIds.value.length }),
    onPositive: async () => {
      const deleted = await batchDeleteKgEntities({ entityIds: checkedEntityIds.value });
      const count = deleted?.deleted_count ?? 0;
      checkedEntityIds.value = [];
      if (selectedId.value && !entityList.value.some((e) => idEq(e.id, selectedId.value))) {
        selectedId.value = null;
      }
      ui.success(t("kgPalantir.messages.batchDeleted", { count }));
      await refreshAfterMutation();
    },
  });
}

async function deleteSearchResultEntities() {
  if (!entityList.value.length) return;
  ui.confirmDelete({
    title: t("kgPalantir.deleteSearchResultsTitle"),
    content: t("kgPalantir.confirmDeleteSearchResults", { count: entityList.value.length }),
    onPositive: async () => {
      const deleted = await batchDeleteKgEntities({
        typeId: filterTypeId.value || undefined,
        q: searchQ.value.trim() || undefined,
      });
      const count = deleted?.deleted_count ?? 0;
      checkedEntityIds.value = [];
      selectedId.value = null;
      ui.success(t("kgPalantir.messages.batchDeleted", { count }));
      await refreshAfterMutation();
    },
  });
}

async function clearEntireGraph() {
  ui.confirmDelete({
    title: t("kgPalantir.clearGraphTitle"),
    content: t("kgPalantir.confirmClearGraph", {
      entities: meta.value?.entity_total || 0,
      relations: meta.value?.relation_total || 0,
    }),
    onPositive: async () => {
      const result = await clearKgGraph();
      checkedEntityIds.value = [];
      selectedId.value = null;
      entityDetail.value = null;
      clearGraph();
      ui.success(
        t("kgPalantir.messages.graphCleared", {
          entities: result?.deleted_entities ?? 0,
          relations: result?.deleted_relations ?? 0,
        })
      );
      await refreshAfterMutation();
    },
  });
}

async function removeEntity() {
  if (!selectedId.value) return;
  try {
    await deleteKgEntity(selectedId.value);
    selectedId.value = null;
    ui.success(t("kgPalantir.messages.entityDeleted"));
    await refreshAfterMutation();
  } catch (e) {
    ui.error(e.message);
  }
}

function openCreateRelation() {
  relationForm.value = {
    relation_type_id: relationTypeOptions.value[0]?.value || null,
    from_entity_id: selectedId.value || entityOptions.value[0]?.value || null,
    to_entity_id: null,
    description: "",
  };
  relationModal.value = true;
}

async function saveRelation() {
  if (!relationForm.value.to_entity_id) {
    ui.warning(t("kgPalantir.messages.selectToEntity"));
    return;
  }
  try {
    await createKgRelation({
      relation_type_id: relationForm.value.relation_type_id,
      from_entity_id: relationForm.value.from_entity_id,
      to_entity_id: relationForm.value.to_entity_id,
      description: relationForm.value.description || "",
    });
    relationModal.value = false;
    ui.success(t("kgPalantir.messages.relationCreated"));
    await refreshAfterMutation();
  } catch (e) {
    ui.error(e.message);
  }
}

async function removeRelation(relationId) {
  try {
    await deleteKgRelation(relationId);
    ui.success(t("kgPalantir.messages.relationDeleted"));
    await refreshAfterMutation();
  } catch (e) {
    ui.error(e.message);
  }
}

function openEntityTypeModal(row) {
  if (row) {
    editingEntityTypeId.value = row.id;
    entityTypeForm.value = {
      code: row.code,
      label: row.label,
      color: row.color,
      description: row.description || "",
    };
  } else {
    editingEntityTypeId.value = null;
    entityTypeForm.value = { code: "", label: "", color: "blue", description: "" };
  }
  entityTypeModal.value = true;
}

async function saveEntityType() {
  try {
    if (editingEntityTypeId.value) {
      await updateKgEntityType(editingEntityTypeId.value, {
        label: entityTypeForm.value.label,
        color: entityTypeForm.value.color,
        description: entityTypeForm.value.description,
      });
    } else {
      await createKgEntityType({
        code: entityTypeForm.value.code.trim(),
        label: entityTypeForm.value.label.trim(),
        color: entityTypeForm.value.color,
        description: entityTypeForm.value.description || "",
      });
    }
    entityTypeModal.value = false;
    ui.success(t("kgPalantir.messages.entityTypeSaved"));
    await refreshAfterMutation();
  } catch (e) {
    ui.error(e.message);
  }
}

async function removeEntityType(typeId) {
  try {
    await deleteKgEntityType(typeId);
    ui.success(t("kgPalantir.messages.entityTypeDeleted"));
    if (filterTypeId.value === typeId) filterTypeId.value = null;
    if (idEq(browseTypeId.value, typeId)) clearBrowseType();
    await refreshAfterMutation();
  } catch (e) {
    ui.error(e.message);
  }
}

function openRelationTypeModal(row) {
  if (row) {
    editingRelationTypeId.value = row.id;
    relationTypeForm.value = {
      code: row.code,
      label: row.label,
      description: row.description || "",
    };
  } else {
    editingRelationTypeId.value = null;
    relationTypeForm.value = { code: "", label: "", description: "" };
  }
  relationTypeModal.value = true;
}

async function saveRelationType() {
  try {
    if (editingRelationTypeId.value) {
      await updateKgRelationType(editingRelationTypeId.value, {
        label: relationTypeForm.value.label,
        description: relationTypeForm.value.description,
      });
    } else {
      await createKgRelationType({
        code: relationTypeForm.value.code.trim(),
        label: relationTypeForm.value.label.trim(),
        description: relationTypeForm.value.description || "",
      });
    }
    relationTypeModal.value = false;
    ui.success(t("kgPalantir.messages.relationTypeSaved"));
    await refreshAfterMutation();
  } catch (e) {
    ui.error(e.message);
  }
}

async function removeRelationType(typeId) {
  try {
    await deleteKgRelationType(typeId);
    ui.success(t("kgPalantir.messages.relationTypeDeleted"));
    if (idEq(browseRelationTypeId.value, typeId)) clearBrowseRelationType();
    await refreshAfterMutation();
  } catch (e) {
    ui.error(e.message);
  }
}

function typeColor(code) {
  return TYPE_COLORS[code] || TYPE_COLORS.gray;
}

function openLinkedDocument() {
  const docId = entityDetail.value?.properties?.document_id;
  if (!docId) return;
  router.push({ name: "document-detail", params: { id: docId } });
}

watch(entityPageCount, (count) => {
  if (entityPage.value > count) entityPage.value = count;
});

watch(graphDepth, () => {
  if (normalizeKgId(selectedId.value)) refreshGraph();
});

watch(filterTypeId, (id) => {
  loadEntityList();
  if (id) loadBrowseByType(id);
  else if (browseTypeId.value) clearBrowseType();
});

watch(searchQ, () => {
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = setTimeout(() => loadEntityList(), 280);
});

onMounted(() => {
  const focus = route.query.focusEntityId;
  if (typeof focus === "string" && focus.trim()) {
    selectedId.value = focus.trim();
  }
  loadAll();
});
</script>

<template>
  <FeatureSubsystemShell fill :show-intro="false">
    <template #extra>
      <div class="kg-toolbar">
        <div class="kg-toolbar__group">
          <span class="kg-toolbar__label">{{ t("kgPalantir.toolbarView") }}</span>
          <n-select
            v-model:value="graphDepth"
            size="small"
            :options="graphDepthOptions"
            class="kg-toolbar__depth"
          />
        </div>
        <div class="kg-toolbar__group kg-toolbar__group--actions">
          <n-button size="small" type="primary" @click="openCreateEntity">
            {{ t("kgPalantir.createEntity") }}
          </n-button>
          <n-button size="small" secondary @click="openCreateRelation">
            {{ t("kgPalantir.addRelation") }}
          </n-button>
          <n-button
            size="small"
            secondary
            :loading="extractingKnowledge"
            @click="runBatchExtract('knowledge')"
          >
            {{ t("kgPalantir.extractKnowledge") }}
          </n-button>
          <n-button
            size="small"
            quaternary
            :loading="extractingPlatform"
            @click="runBatchExtract('platform')"
          >
            {{ t("kgPalantir.extractPlatform") }}
          </n-button>
          <ListRefreshButton @click="forceRefreshAll({ toast: true })" />
        </div>
      </div>
    </template>

    <n-spin :show="loading" class="kg-spin" local>
      <div class="kg-page">
        <aside class="kg-panel kg-panel--left">
          <KgPalantirStats v-if="meta" :meta="meta" :type-color="typeColor" />
          <n-tabs v-model:value="leftTab" type="line" size="small" class="kg-tabs">
            <n-tab-pane name="entities" :tab="t('kgPalantir.tabEntities')">
              <KgEntityListPanel
                :meta="meta"
                :entity-list="entityList"
                :paginated-entity-list="paginatedEntityList"
                :list-loading="listLoading"
                v-model:search-q="searchQ"
                v-model:filter-type-id="filterTypeId"
                v-model:entity-page="entityPage"
                v-model:checked-ids="checkedEntityIds"
                :selected-id="selectedId"
                :entity-page-count="entityPageCount"
                :type-filter-options="typeFilterOptions"
                :type-color="typeColor"
                :id-eq="idEq"
                @select="selectEntity"
                @delete-checked="deleteCheckedEntities"
                @delete-search-results="deleteSearchResultEntities"
                @clear-graph="clearEntireGraph"
              />
            </n-tab-pane>

            <n-tab-pane name="ontology" :tab="t('kgPalantir.tabOntology')">
              <div class="kg-ontology-section">
                <div class="kg-ontology-head">
                  <span>{{ t("kgPalantir.entityTypes") }}</span>
                  <n-button size="tiny" quaternary @click="openEntityTypeModal(null)">
                    {{ t("common.create") }}
                  </n-button>
                </div>
                <div class="kg-ontology-list">
                  <button
                    v-for="entityType in meta?.entity_types || []"
                    :key="entityType.id"
                    type="button"
                    class="kg-glass-item kg-ontology-item"
                    :class="{ 'is-active': idEq(browseTypeId, entityType.id) }"
                    @click="browseEntityType(entityType.id)"
                  >
                    <span class="kg-ontology-item__dot" :style="{ background: typeColor(entityType.color) }" />
                    <span class="kg-ontology-item__label">{{ entityType.label }}</span>
                    <span class="kg-ontology-item__count">{{ entityType.entity_count }}</span>
                    <n-button
                      size="tiny"
                      quaternary
                      class="kg-ontology-item__edit"
                      @click.stop="openEntityTypeModal(entityType)"
                    >
                      {{ t("common.edit") }}
                    </n-button>
                  </button>
                </div>
              </div>
              <div class="kg-ontology-section">
                <div class="kg-ontology-head">
                  <span>{{ t("kgPalantir.relationTypes") }}</span>
                  <n-button size="tiny" quaternary @click="openRelationTypeModal(null)">
                    {{ t("common.create") }}
                  </n-button>
                </div>
                <div class="kg-ontology-list">
                  <button
                    v-for="rt in meta?.relation_types || []"
                    :key="rt.id"
                    type="button"
                    class="kg-glass-item kg-ontology-item"
                    :class="{ 'is-active': idEq(browseRelationTypeId, rt.id) }"
                    @click="browseRelationType(rt.id)"
                  >
                    <span class="kg-ontology-item__label">{{ rt.label }}</span>
                    <span class="kg-ontology-item__count">{{ rt.relation_count }}</span>
                    <n-button
                      size="tiny"
                      quaternary
                      class="kg-ontology-item__edit"
                      @click.stop="openRelationTypeModal(rt)"
                    >
                      {{ t("common.edit") }}
                    </n-button>
                  </button>
                </div>
              </div>
              <p class="kg-ontology-tip">
                {{ t("kgPalantir.ontologyTip") }}
              </p>
            </n-tab-pane>
          </n-tabs>
        </aside>

        <main class="kg-panel kg-panel--center">
          <KgGraphCanvas
            v-if="graphLayout.nodes.length"
            ref="graphCanvasRef"
            :layout="graphLayout"
            :selected-id="selectedId"
            :type-color="typeColor"
            @select="selectEntity"
          />
          <div v-else class="kg-empty-wrap">
            <n-empty
              :description="
                hasAnyEntities
                  ? t('kgPalantir.selectEntityForGraph')
                  : t('kgPalantir.noEntitiesYet')
              "
            >
              <template v-if="!hasAnyEntities" #extra>
                <n-button size="small" type="primary" @click="openCreateEntity">
                  {{ t("kgPalantir.createEntity") }}
                </n-button>
              </template>
            </n-empty>
          </div>
        </main>

        <aside class="kg-panel kg-panel--right">
          <div class="kg-right-stack" :class="{ 'kg-right-stack--browse': isTypeBrowseMode }">
            <div class="kg-detail-toolbar">
              <span class="kg-detail-toolbar__title">{{ t("kgPalantir.info") }}</span>
              <ListRefreshButton
                size="tiny"
                :loading="detailRefreshing"
                @click="forceRefreshAll({ toast: true })"
              />
            </div>
            <div
              ref="detailMainRef"
              class="kg-detail-main"
              :class="{
                'kg-detail-main--plain': !selectedEntity && !isTypeBrowseMode,
                'kg-detail-main--compact': isTypeBrowseMode,
              }"
            >
              <div v-if="selectedEntity" class="kg-detail-card kg-detail-card--entity">
                <div class="kg-detail-card__head">
                  <div class="kg-detail-head">
                    <h3 class="kg-detail-title">{{ selectedEntity.name }}</h3>
                    <n-tag size="small" :bordered="false">{{ selectedEntity.type_label }}</n-tag>
                  </div>
                  <p v-if="entityDetail?.description" class="kg-detail-desc">
                    {{ entityDetail.description }}
                  </p>
                  <p
                    v-if="entityDetail?.properties?.kg_extracted_at"
                    class="kg-detail-meta"
                  >
                    {{ t("kgPalantir.extractedAt") }}：{{ entityDetail.properties.kg_extracted_at }}
                  </p>
                  <div class="kg-detail-actions">
                    <n-button size="small" type="primary" @click="openEditEntity">{{ t("common.edit") }}</n-button>
                    <n-button size="small" @click="openCreateRelation">{{ t("kgPalantir.addRelation") }}</n-button>
                    <n-button
                      v-if="entityDetail?.properties?.document_id"
                      size="small"
                      quaternary
                      @click="openLinkedDocument"
                    >
                      {{ t("kgPalantir.linkedDocument") }}
                    </n-button>
                    <n-button size="small" type="error" quaternary @click="removeEntity">{{ t("common.delete") }}</n-button>
                  </div>
                  <div class="kg-detail-section__title">
                    {{ t("kgPalantir.relatedRelations") }}
                    <span class="kg-detail-section__count">{{ relations.length }}</span>
                  </div>
                </div>
                <div ref="detailRelListRef" class="kg-detail-card__scroll">
                  <div v-for="rel in relations" :key="rel.id" class="kg-rel-item">
                    <n-tag size="small" :bordered="false">{{ rel.relation_type_label }}</n-tag>
                    <button
                      type="button"
                      class="kg-rel-item__link"
                      @click="
                        selectEntity(
                          idEq(rel.from_entity_id, selectedId) ? rel.to_entity_id : rel.from_entity_id
                        )
                      "
                    >
                      {{ idEq(rel.from_entity_id, selectedId) ? rel.to_name : rel.from_name }}
                    </button>
                    <n-button size="tiny" quaternary @click="removeRelation(rel.id)">{{ t("common.delete") }}</n-button>
                  </div>
                  <n-empty v-if="!relations.length" size="small" :description="t('kgPalantir.noRelatedRelations')" />
                </div>
              </div>
              <div v-else-if="browseRelationTypeMeta" class="kg-detail-card">
                <div class="kg-detail-head">
                  <h3 class="kg-detail-title">{{ browseRelationTypeMeta.label }}</h3>
                  <n-tag size="small" :bordered="false">{{ t("kgPalantir.relationTypeTag") }}</n-tag>
                </div>
                <p class="kg-detail-meta">Code：{{ browseRelationTypeMeta.code }}</p>
                <p v-if="browseRelationTypeMeta.description" class="kg-detail-desc">
                  {{ browseRelationTypeMeta.description }}
                </p>
                <p class="kg-detail-meta">
                  {{ t("kgPalantir.relationInstances", { count: browseRelationTypeMeta.relation_count }) }}
                </p>
                <div class="kg-detail-actions">
                  <n-button
                    size="small"
                    type="primary"
                    @click="openRelationTypeModal(browseRelationTypeMeta)"
                  >
                    {{ t("common.edit") }}
                  </n-button>
                  <n-button size="small" quaternary @click="clearBrowseRelationType">{{ t("common.close") }}</n-button>
                </div>
              </div>
              <div v-else-if="browseTypeMeta" class="kg-detail-card kg-detail-card--hint">
                <p class="kg-detail-browse-hint">
                  {{
                    t("kgPalantir.browseTypeHint", {
                      label: browseTypeMeta.label,
                      hop: graphDepth,
                    })
                  }}
                </p>
                <div class="kg-detail-actions">
                  <n-button size="small" quaternary @click="clearBrowseType">{{ t("common.close") }}</n-button>
                </div>
              </div>
              <div v-else class="kg-detail-placeholder">
                <n-empty size="small" :description="t('kgPalantir.selectEntityOrType')" />
              </div>
            </div>

            <div v-if="browseTypeId && browseTypeMeta && !selectedEntity" class="kg-type-browse">
              <div class="kg-type-browse__head">
                <div class="kg-type-browse__title">
                  <span
                    class="kg-type-browse__dot"
                    :style="{ background: typeColor(browseTypeMeta.color) }"
                  />
                  {{ browseTypeMeta.label }}
                  <span class="kg-type-browse__count">{{ browseTypeEntities.length }}</span>
                </div>
                <n-button size="tiny" quaternary @click="clearBrowseType">{{ t("common.close") }}</n-button>
              </div>
              <n-spin :show="browseTypeLoading" class="kg-type-browse__spin" local>
                <div v-if="browseTypeEntities.length" class="kg-type-browse__body">
                  <div class="kg-type-browse__list">
                    <button
                      v-for="item in browseTypeEntities"
                      :key="item.id"
                      type="button"
                      class="kg-glass-item kg-type-browse__item"
                      :class="{ 'is-active': idEq(selectedId, item.id) }"
                      @click="selectEntity(item.id)"
                    >
                      <span class="kg-type-browse__item-name">{{ item.name }}</span>
                      <span
                        v-if="item.properties?.document_id"
                        class="kg-type-browse__item-tag"
                      >
                        {{ t("kgPalantir.document") }}
                      </span>
                    </button>
                  </div>
                </div>
                <n-empty v-else size="small" :description="t('kgPalantir.noEntitiesInType')" />
              </n-spin>
            </div>
          </div>
        </aside>
      </div>
    </n-spin>

    <AdminFormModal
      v-model:show="entityModal"
      :title="editingEntityId ? t('kgPalantir.editEntity') : t('kgPalantir.newEntity')"
      :width="420"
    >
      <n-form label-placement="top" class="kg-modal-form">
        <n-form-item :label="t('kgPalantir.type')">
          <n-select v-model:value="entityForm.type_id" :options="entityTypeOptions" />
        </n-form-item>
        <n-form-item :label="t('kgPalantir.name')">
          <n-input v-model:value="entityForm.name" :placeholder="t('kgPalantir.entityName')" />
        </n-form-item>
        <n-form-item :label="t('kgPalantir.description')">
          <n-input
            v-model:value="entityForm.description"
            type="textarea"
            :rows="3"
            :placeholder="t('kgPalantir.optional')"
          />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space :size="10">
          <n-button @click="entityModal = false">{{ t("common.cancel") }}</n-button>
          <n-button type="primary" @click="saveEntity">{{ t("common.save") }}</n-button>
        </n-space>
      </template>
    </AdminFormModal>

    <AdminFormModal v-model:show="relationModal" :title="t('kgPalantir.addRelationTitle')" :width="420">
      <n-form label-placement="top" class="kg-modal-form">
        <n-form-item :label="t('kgPalantir.relationType')">
          <n-select v-model:value="relationForm.relation_type_id" :options="relationTypeOptions" />
        </n-form-item>
        <n-form-item :label="t('kgPalantir.fromEntity')">
          <n-select
            v-model:value="relationForm.from_entity_id"
            filterable
            :options="entityOptions"
          />
        </n-form-item>
        <n-form-item :label="t('kgPalantir.toEntity')">
          <n-select
            v-model:value="relationForm.to_entity_id"
            filterable
            :placeholder="t('kgPalantir.selectRelatedEntity')"
            :options="entityOptions"
          />
        </n-form-item>
        <n-form-item :label="t('kgPalantir.note')">
          <n-input v-model:value="relationForm.description" type="textarea" :rows="2" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space :size="10">
          <n-button @click="relationModal = false">{{ t("common.cancel") }}</n-button>
          <n-button type="primary" @click="saveRelation">{{ t("common.save") }}</n-button>
        </n-space>
      </template>
    </AdminFormModal>

    <AdminFormModal
      v-model:show="entityTypeModal"
      :title="editingEntityTypeId ? t('kgPalantir.editEntityType') : t('kgPalantir.newEntityType')"
      :width="420"
    >
      <n-form label-placement="top" class="kg-modal-form">
        <n-form-item v-if="!editingEntityTypeId" label="Code">
          <n-input v-model:value="entityTypeForm.code" :placeholder="t('kgPalantir.codePlaceholderEntity')" />
        </n-form-item>
        <n-form-item :label="t('kgPalantir.displayName')">
          <n-input v-model:value="entityTypeForm.label" />
        </n-form-item>
        <n-form-item :label="t('kgPalantir.colorTag')">
          <n-select
            v-model:value="entityTypeForm.color"
            :options="Object.keys(TYPE_COLORS).map((k) => ({ label: k, value: k }))"
          />
        </n-form-item>
        <n-form-item :label="t('kgPalantir.description')">
          <n-input v-model:value="entityTypeForm.description" type="textarea" :rows="2" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="space-between" align="center" class="kg-modal-footer">
          <n-button
            v-if="editingEntityTypeId"
            type="error"
            quaternary
            @click="removeEntityType(editingEntityTypeId)"
          >
            {{ t("common.delete") }}
          </n-button>
          <span v-else />
          <n-space :size="10">
            <n-button @click="entityTypeModal = false">{{ t("common.cancel") }}</n-button>
            <n-button type="primary" @click="saveEntityType">{{ t("common.save") }}</n-button>
          </n-space>
        </n-space>
      </template>
    </AdminFormModal>

    <AdminFormModal
      v-model:show="relationTypeModal"
      :title="editingRelationTypeId ? t('kgPalantir.editRelationType') : t('kgPalantir.newRelationType')"
      :width="420"
    >
      <n-form label-placement="top" class="kg-modal-form">
        <n-form-item v-if="!editingRelationTypeId" label="Code">
          <n-input v-model:value="relationTypeForm.code" :placeholder="t('kgPalantir.codePlaceholderRelation')" />
        </n-form-item>
        <n-form-item :label="t('kgPalantir.displayName')">
          <n-input v-model:value="relationTypeForm.label" />
        </n-form-item>
        <n-form-item :label="t('kgPalantir.description')">
          <n-input v-model:value="relationTypeForm.description" type="textarea" :rows="2" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="space-between" align="center" class="kg-modal-footer">
          <n-button
            v-if="editingRelationTypeId"
            type="error"
            quaternary
            @click="removeRelationType(editingRelationTypeId)"
          >
            {{ t("common.delete") }}
          </n-button>
          <span v-else />
          <n-space :size="10">
            <n-button @click="relationTypeModal = false">{{ t("common.cancel") }}</n-button>
            <n-button type="primary" @click="saveRelationType">{{ t("common.save") }}</n-button>
          </n-space>
        </n-space>
      </template>
    </AdminFormModal>
  </FeatureSubsystemShell>
</template>

<style scoped>
.kg-spin {
  flex: 1;
  min-height: 0;
  display: flex;
}

.kg-spin :deep(.n-spin-content) {
  flex: 1;
  min-height: 0;
  display: flex;
}

.kg-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px 16px;
  width: 100%;
  min-width: 0;
}

.kg-toolbar__group {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.kg-toolbar__group--actions {
  margin-left: auto;
}

.kg-toolbar__label {
  font-size: 12px;
  color: var(--platform-text-tertiary);
  white-space: nowrap;
}

.kg-toolbar__depth {
  width: 120px;
}

.kg-page {
  display: flex;
  flex: 1;
  min-height: 0;
  max-height: 100%;
  height: 100%;
  border: 1px solid var(--platform-border);
  border-radius: 14px;
  overflow: hidden;
  background: var(--platform-bg-elevated);
  box-shadow: 0 1px 0 color-mix(in srgb, var(--platform-text-primary) 4%, transparent);
}

.kg-panel {
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.kg-panel--left {
  width: min(320px, 36vw);
  min-width: 280px;
  border-right: 1px solid var(--platform-border);
  background: var(--platform-bg-secondary);
  display: flex;
  flex-direction: column;
}

.kg-tabs {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.kg-tabs :deep(.n-tabs-pane-wrapper) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.kg-tabs :deep(.n-tab-pane) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.kg-panel--center {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: radial-gradient(
    120% 80% at 50% 0%,
    color-mix(in srgb, var(--platform-primary) 6%, var(--platform-bg-elevated)),
    var(--platform-bg-elevated) 55%
  );
}

.kg-panel--right {
  width: min(300px, 32vw);
  min-width: 260px;
  border-left: 1px solid var(--platform-border);
  background: var(--platform-bg-secondary);
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.kg-right-stack {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.kg-detail-toolbar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 12px 8px;
  border-bottom: 1px solid var(--platform-border);
}

.kg-detail-toolbar__title {
  font-size: 13px;
  font-weight: 600;
  color: var(--platform-text-secondary);
}

.kg-detail-main {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.kg-detail-main--plain {
  overflow-y: auto;
  padding: 16px;
}

.kg-detail-main--compact {
  flex: 0 0 auto;
  overflow: hidden;
  padding: 12px 16px 8px;
}

.kg-detail-card {
  width: 100%;
}

.kg-detail-card--entity {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.kg-detail-card__head {
  flex-shrink: 0;
  padding: 16px 16px 10px;
}

.kg-detail-card__scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 0 16px 16px;
  -webkit-overflow-scrolling: touch;
}

.kg-detail-card__head .kg-detail-section__title {
  margin-bottom: 0;
  padding-top: 4px;
}

.kg-detail-placeholder {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  min-height: 0;
}

.kg-detail-card--hint {
  text-align: center;
}

.kg-detail-meta {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--platform-text-tertiary);
}

.kg-tabs {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 8px 10px 10px;
}

.kg-tabs :deep(.n-tabs-pane-wrapper) {
  flex: 1;
  min-height: 0;
}

.kg-tabs :deep(.n-tab-pane) {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.kg-search-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 8px;
}

.kg-list-meta {
  font-size: 12px;
  color: var(--platform-text-tertiary);
  margin-bottom: 8px;
}

.kg-list-spin {
  flex: 1;
  min-height: 0;
}

.kg-list-spin :deep(.n-spin-content) {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.kg-entity-list-wrap {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.kg-entity-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.kg-list-pagination {
  flex-shrink: 0;
  display: flex;
  justify-content: center;
  padding: 4px 0 2px;
}

/* 可选列表行：玻璃底完整覆盖文字区（与侧栏菜单同源 token） */
.kg-glass-item {
  position: relative;
  isolation: isolate;
  box-sizing: border-box;
  width: 100%;
  margin: 0;
  overflow: hidden;
  border: none;
  border-radius: var(--platform-radius-sm);
  background: transparent;
  cursor: pointer;
  font: inherit;
  text-align: left;
  transition: color 0.15s ease;
}

.kg-glass-item::before {
  content: "";
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  border-radius: inherit;
  border: 1px solid transparent;
  opacity: 0;
  background: var(--platform-glass-fill-hover);
  box-shadow: var(--platform-glass-rim-edge);
  transition:
    opacity 0.18s var(--platform-ease-smooth),
    background 0.18s var(--platform-ease-smooth),
    border-color 0.18s var(--platform-ease-smooth);
}

.kg-glass-item > * {
  position: relative;
  z-index: 1;
}

.kg-glass-item:hover::before {
  opacity: var(--menu-glass-hover-opacity, 0.52);
}

.kg-glass-item.is-active {
  color: var(--platform-accent);
  font-weight: 600;
}

.kg-glass-item.is-active::before {
  opacity: 1;
  background: var(--platform-glass-fill-active);
  border-color: color-mix(in srgb, var(--platform-accent) 24%, transparent);
  box-shadow: var(--platform-glass-rim-edge);
}

.kg-glass-item.is-active .kg-entity-row__name,
.kg-glass-item.is-active .kg-entity-row__type,
.kg-glass-item.is-active .kg-ontology-item__label,
.kg-glass-item.is-active .kg-ontology-item__count,
.kg-glass-item.is-active .kg-type-browse__item-name {
  color: inherit;
}

.kg-entity-row {
  display: flex;
  align-items: stretch;
  gap: 10px;
  padding: 10px 12px;
  min-height: 44px;
}

.kg-entity-row__dot {
  width: 10px;
  height: 10px;
  border-radius: 3px;
  flex-shrink: 0;
  align-self: center;
}

.kg-entity-row__body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
}

.kg-entity-row__name {
  font-size: 13px;
  font-weight: 500;
  color: var(--platform-text-primary);
  line-height: 1.35;
  word-break: break-word;
}

.kg-entity-row__type {
  font-size: 11px;
  color: var(--platform-text-tertiary);
}

.kg-list-empty {
  padding: 24px 0;
}

.kg-ontology-section + .kg-ontology-section {
  margin-top: 16px;
}

.kg-ontology-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--platform-text-secondary);
}

.kg-ontology-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.kg-ontology-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  min-height: 40px;
  font-size: 12px;
  color: var(--platform-text-primary);
}

.kg-ontology-item__edit {
  flex-shrink: 0;
  margin-left: auto;
}

.kg-ontology-item :deep(.n-button) {
  position: relative;
  z-index: 1;
}

.kg-ontology-item__dot {
  width: 8px;
  height: 8px;
  border-radius: 2px;
  flex-shrink: 0;
}

.kg-ontology-item__label {
  flex: 1;
  min-width: 0;
}

.kg-ontology-item__count {
  color: var(--platform-text-tertiary);
}

.kg-ontology-tip {
  margin: 16px 0 0;
  font-size: 11px;
  line-height: 1.5;
  color: var(--platform-text-tertiary);
}

.kg-empty-wrap {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  min-height: 0;
}

.kg-detail-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.kg-detail-title {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  line-height: 1.3;
  word-break: break-word;
}

.kg-detail-desc {
  margin: 0 0 12px;
  font-size: 13px;
  line-height: 1.55;
  color: var(--platform-text-secondary);
}

.kg-detail-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.kg-modal-form :deep(.n-form-item:last-child) {
  margin-bottom: 0;
}

.kg-modal-footer {
  width: 100%;
}

.kg-detail-section__title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--platform-text-secondary);
  margin-bottom: 10px;
}

.kg-detail-section__count {
  font-weight: 400;
  color: var(--platform-text-tertiary);
}

.kg-rel-item {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  font-size: 12px;
}

.kg-rel-item__link {
  flex: 1;
  min-width: 0;
  border: none;
  background: none;
  color: var(--platform-accent);
  cursor: pointer;
  text-align: left;
  padding: 0;
  word-break: break-word;
}

.kg-detail-browse-hint {
  margin: 0;
  font-size: 13px;
  line-height: 1.55;
  color: var(--platform-text-secondary);
}

.kg-right-stack--browse .kg-type-browse {
  flex: 1;
  min-height: 0;
}

.kg-type-browse {
  display: flex;
  flex-direction: column;
  border-top: 1px solid var(--platform-border);
  background: color-mix(in srgb, var(--platform-bg) 70%, var(--platform-bg-secondary));
  overflow: hidden;
}

.kg-type-browse__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 12px 8px;
}

.kg-type-browse__title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--platform-text-primary);
}

.kg-type-browse__dot {
  width: 10px;
  height: 10px;
  border-radius: 3px;
  flex-shrink: 0;
}

.kg-type-browse__count {
  font-size: 12px;
  font-weight: 400;
  color: var(--platform-text-tertiary);
}

.kg-type-browse__spin {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.kg-type-browse__spin :deep(.n-spin-content) {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.kg-type-browse__body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow: hidden;
}

.kg-type-browse__list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 0 8px 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  -webkit-overflow-scrolling: touch;
}

.kg-type-browse__item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  min-height: 40px;
}

.kg-type-browse__item-name {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  color: var(--platform-text-primary);
  word-break: break-word;
}

.kg-type-browse__item-tag {
  flex-shrink: 0;
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 999px;
  color: var(--platform-accent-pressed);
  background: var(--platform-accent-muted);
}

@media (max-width: 960px) {
  .kg-page {
    flex-direction: column;
  }

  .kg-panel--left,
  .kg-panel--right {
    width: 100%;
    max-height: 34vh;
    border: none;
    border-bottom: 1px solid var(--platform-border);
  }

  .kg-panel--right {
    border-left: none;
  }

  .kg-panel--center {
    min-height: 42vh;
  }
}
</style>
