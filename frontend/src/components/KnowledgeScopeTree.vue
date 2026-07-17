<script setup>
import { computed, h, onActivated, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { NEmpty, NIcon, NInput, NTag, NTree } from "naive-ui";
import PlatformSpin from "./PlatformSpin.vue";
import {
  BusinessOutline,
  DocumentTextOutline,
  FolderOpenOutline,
  PeopleOutline,
  PersonOutline,
  RefreshOutline } from "@vicons/ionicons5";
import IconAction from "./IconAction.vue";
import { useKnowledgeScopeTree } from "../composables/useKnowledgeScopeTree.js";
import { useI18n } from "../composables/useI18n.js";
import { usePlatformUi } from "../composables/usePlatformUi.js";
import {
  isDocumentIndexReady,
  knowledgeIndexTagProps,
  knowledgeScopeIndexSummary } from "../utils/knowledgeIndex.js";
import {
  hasKnowledgeScopeTreeItems,
  isKnowledgeScopeTreeCacheFresh,
  readKnowledgeScopeTreeCache,
} from "../utils/knowledgeScopeTreeCache.js";
import {
  clearKnowledgeScopeSelection,
  writeKnowledgeScopeSelection,
} from "../utils/knowledgeScopeSelectionCache.js";
import { navigateWithReturn } from "../utils/navigationReturn.js";
import { isRouteAbortError } from "../api/client.js";
import { KNOWLEDGE_INDEX_UPDATED_EVENT } from "../constants/platformEvents.js";

const CHECKED_KEYS_STORAGE = "platform:knowledge-search-checked-keys:v2";

const QA_DOC_LIMIT = 20;

const emit = defineEmits(["selection-change"]);

const route = useRoute();
const router = useRouter();
const { t, scopeLabel } = useI18n();
const ui = usePlatformUi();
const { treePayload, loading, loadKnowledgeScopeTree } = useKnowledgeScopeTree();

const refreshing = ref(false);
const filter = ref("");
const treeData = computed(() => treePayload.value?.items || []);
const expandedKeys = ref([]);
const checkedKeys = ref([]);

const scopeIcons = {
  company: BusinessOutline,
  department: PeopleOutline,
  team: PeopleOutline,
  personal: PersonOutline,
  library: FolderOpenOutline,
  folder: FolderOpenOutline,
  document: DocumentTextOutline};

function nodeIcon(node) {
  if (node.type === "document") return DocumentTextOutline;
  if (node.type === "folder" || node.type === "library") return FolderOpenOutline;
  if (node.scope && scopeIcons[node.scope]) return scopeIcons[node.scope];
  return FolderOpenOutline;
}

function renderPrefix({ option }) {
  return h(NIcon, { size: 15, component: nodeIcon(option) });
}

function openDocumentDetail(documentId, event) {
  event?.stopPropagation?.();
  event?.preventDefault?.();
  if (!documentId) return;
  navigateWithReturn(
    router,
    { name: "document-detail", params: { id: documentId } },
    route
  );
}

function displayNodeLabel(option) {
  if (option.virtual_folder_id === "__uncategorized__") {
    return t("knowledgeSearch.tree.uncategorized");
  }
  if (option.virtual_folder_id === "__shared__") {
    return t("scope.shared");
  }
  if (option.type === "scope" && option.scope) {
    return scopeLabel(option.scope);
  }
  return option.label;
}

function renderScopeIndexTag(node) {
  const summary = knowledgeScopeIndexSummary(node, t);
  if (!summary) return null;
  return h(
    NTag,
    {
      size: "tiny",
      type: summary.type,
      bordered: false,
      class: "knowledge-scope-tree__node-tag",
    },
    { default: () => summary.label }
  );
}

function renderLabel({ option }) {
  if (option.type === "document") {
    const tag = knowledgeIndexTagProps(option, { forSearch: true, t });
    const title = option.label;
    return h("span", { class: "knowledge-scope-tree__node-label" }, [
      h(
        "span",
        {
          class: "knowledge-scope-tree__node-title knowledge-scope-tree__node-title--link",
          title: tag.hint ? `${title}（${tag.hint}）` : title,
          onClick: (event) => openDocumentDetail(option.document_id, event),
        },
        title
      ),
      h(
        NTag,
        {
          size: "tiny",
          type: tag.type,
          bordered: false,
          class: "knowledge-scope-tree__node-tag",
          title: tag.hint || tag.label,
        },
        { default: () => tag.label }
      ),
    ]);
  }

  if (option.type === "folder" || option.type === "library" || option.type === "scope") {
    return h("span", { class: "knowledge-scope-tree__node-label" }, [
      h(
        "span",
        {
          class: "knowledge-scope-tree__node-title",
          title: displayNodeLabel(option),
        },
        displayNodeLabel(option)
      ),
      renderScopeIndexTag(option),
    ]);
  }

  return option.label;
}

function cloneFilterTree(nodes, kw) {
  const out = [];
  for (const node of nodes || []) {
    const label = String(node.label || "").toLowerCase();
    const childMatches = cloneFilterTree(node.children || [], kw);
    if (label.includes(kw) || childMatches.length) {
      out.push({
        ...node,
        children: childMatches.length ? childMatches : node.children});
    }
  }
  return out;
}

function collectExpandableAncestorKeys(nodes, kw, ancestors = []) {
  const keys = [];
  for (const node of nodes || []) {
    const label = String(node.label || "").toLowerCase();
    const childKeys = collectExpandableAncestorKeys(
      node.children || [],
      kw,
      [...ancestors, node.key]
    );
    const childMatched = childKeys.length > 0;
    if (childMatched || label.includes(kw)) {
      keys.push(...ancestors, node.key, ...childKeys);
    }
  }
  return [...new Set(keys)];
}

const displayTree = computed(() => {
  const kw = filter.value.trim().toLowerCase();
  if (!kw) return treeData.value;
  return cloneFilterTree(treeData.value, kw);
});

watch(
  () => filter.value.trim().toLowerCase(),
  (kw) => {
    if (!kw) return;
    expandedKeys.value = collectExpandableAncestorKeys(treeData.value, kw);
  }
);

function saveCheckedKeys(keys) {
  try {
    sessionStorage.setItem(CHECKED_KEYS_STORAGE, JSON.stringify(keys || []));
  } catch {
    /* ignore */
  }
}

function loadSavedCheckedKeys() {
  try {
    const raw = sessionStorage.getItem(CHECKED_KEYS_STORAGE);
    if (!raw) return null;
    const keys = JSON.parse(raw);
    return Array.isArray(keys) ? keys : null;
  } catch {
    return null;
  }
}

async function restoreCheckedSelection() {
  const saved = loadSavedCheckedKeys();
  if (!saved?.length) return;
  const pruned = pruneCheckedKeys(saved);
  checkedKeys.value = pruned;
  saveCheckedKeys(pruned);
  emitSelectionForKeys(pruned);
}

/** KeepAlive 在知识检索 ↔ 报告生成间切换时，从 session 同步另一页的勾选 */
function syncCheckedKeysFromStorage() {
  if (!treeData.value.length) return false;
  const saved = loadSavedCheckedKeys();
  if (!saved?.length) {
    if (!checkedKeys.value.length) return false;
    checkedKeys.value = [];
    clearKnowledgeScopeSelection();
    emit("selection-change", null);
    return true;
  }
  const pruned = pruneCheckedKeys(saved);
  const prev = JSON.stringify(checkedKeys.value);
  const next = JSON.stringify(pruned);
  if (prev === next) return false;
  checkedKeys.value = pruned;
  saveCheckedKeys(pruned);
  emitSelectionForKeys(pruned);
  return true;
}

function findNode(nodes, key) {
  for (const node of nodes || []) {
    if (node.key === key) return node;
    const found = findNode(node.children, key);
    if (found) return found;
  }
  return null;
}

function normalizeDocumentNode(node) {
  if (!node || node.type !== "document") return node;
  return {
    ...node,
    index_ready: node.index_ready ?? isDocumentIndexReady(node)};
}

function collectDocumentNodesFromKeys(keys) {
  const seen = new Set();
  const nodes = [];

  function walk(node) {
    if (!node) return;
    if (node.type === "document") {
      const docId = node.document_id;
      if (!docId || seen.has(docId)) return;
      seen.add(docId);
      nodes.push(normalizeDocumentNode(node));
      return;
    }
    for (const child of node.children || []) {
      walk(child);
    }
  }

  for (const key of keys || []) {
    walk(findNode(treeData.value, key));
  }
  return nodes;
}

/** 已选文档的统计摘要 */
const selectionSummary = computed(() => {
  const docNodes = collectDocumentNodesFromKeys(checkedKeys.value);
  const total = docNodes.length;
  if (!total) return null;
  const ready = docNodes.filter((n) => n.index_ready);
  return {
    total,
    indexReady: ready.length,
    indexPending: total - ready.length,
  };
});

function pruneCheckedKeys(keys) {
  const next = (keys || []).filter((key) => Boolean(findNode(treeData.value, key)));
  return [...new Set(next)];
}

function emitSelectionForKeys(keys) {
  const docNodes = collectDocumentNodesFromKeys(keys);
  const payload = docNodes.length ? buildSelectionPayload(docNodes) : null;
  writeKnowledgeScopeSelection(payload);
  emit("selection-change", payload);
}

function syncSelectionAfterTreeUpdate() {
  if (!checkedKeys.value.length) {
    if (loadSavedCheckedKeys()?.length) {
      return;
    }
    clearKnowledgeScopeSelection();
    emit("selection-change", null);
    return;
  }
  const pruned = pruneCheckedKeys(checkedKeys.value);
  if (pruned.length !== checkedKeys.value.length) {
    checkedKeys.value = pruned;
    saveCheckedKeys(pruned);
  }
  emitSelectionForKeys(checkedKeys.value);
}

function buildSelectionPayload(docNodes) {
  const totalSelected = docNodes.length;
  const readyNodes = docNodes.filter((n) => n.index_ready);
  const documentIds = docNodes.map((n) => n.document_id).filter(Boolean).slice(0, QA_DOC_LIMIT);
  const labels = [...new Set(docNodes.map((n) => n.label).filter(Boolean))];

  let label = "";
  if (totalSelected === 1) {
    label = docNodes[0].label;
  } else if (totalSelected > 1) {
    label = t("knowledgeSearch.selectedMulti", { count: totalSelected });
  }

  return {
    type: totalSelected === 1 ? "document" : "multi",
    label,
    labels,
    totalSelected,
    indexReadyCount: readyNodes.length,
    documentIds};
}

function applyTreeData(data, { resetSelection = false } = {}) {
  treePayload.value = data;
  if (resetSelection) {
    expandedKeys.value = [];
    checkedKeys.value = [];
    clearKnowledgeScopeSelection();
    emit("selection-change", null);
  }
}

async function fetchTree({
  background = false,
  resetSelection = false,
  refresh = false,
} = {}) {
  const hadTree = treeData.value.length > 0;
  if (background || refresh) {
    refreshing.value = true;
  }
  try {
    const data = await loadKnowledgeScopeTree({
      force: refresh,
      background: background && hadTree,
      refresh,
    });
    applyTreeData(data, { resetSelection });
    if (!resetSelection) {
      syncSelectionAfterTreeUpdate();
    }
  } catch (e) {
    if (isRouteAbortError(e)) {
      return;
    }
    if (!background && !treeData.value.length) {
      applyTreeData({ items: [] }, { resetSelection: true });
    }
    if (!background) {
      ui.error(e?.message || t("knowledgeSearch.tree.loadFailed"));
    }
  } finally {
    refreshing.value = false;
  }
}

async function loadTree() {
  const cached = readKnowledgeScopeTreeCache({ allowStale: true });
  if (cached) {
    applyTreeData(cached, { resetSelection: false });
    await restoreCheckedSelection();
    if (!isKnowledgeScopeTreeCacheFresh()) {
      void loadKnowledgeScopeTree({ force: true, background: true }).catch(() => {});
    }
    return;
  }
  if (hasKnowledgeScopeTreeItems(treePayload.value)) {
    await restoreCheckedSelection();
    return;
  }
  await fetchTree({ resetSelection: false });
  await restoreCheckedSelection();
}

/** 后台预取完成时 composable 已有数据，但 fetchTree 未跑过 — 补同步勾选 */
watch(
  () => treeData.value.length,
  (len, prevLen) => {
    if (len > 0 && !prevLen) {
      syncSelectionAfterTreeUpdate();
    }
  }
);

async function reloadTree() {
  await fetchTree({ resetSelection: true, refresh: true });
}

async function refreshTree() {
  if (loading.value || refreshing.value) return;
  const hadTree = treeData.value.length > 0;
  await fetchTree({ background: hadTree, refresh: true });
}

function onKnowledgeIndexUpdated() {
  if (refreshing.value) return;
  fetchTree({ background: true, refresh: true });
}

function onCheckedKeysChange(keys) {
  const nextKeys = Array.isArray(keys) ? [...keys] : [];
  checkedKeys.value = nextKeys;
  saveCheckedKeys(nextKeys);
  emitSelectionForKeys(nextKeys);
}

onMounted(() => {
  loadTree();
  window.addEventListener(KNOWLEDGE_INDEX_UPDATED_EVENT, onKnowledgeIndexUpdated);
});

onActivated(() => {
  const cached = readKnowledgeScopeTreeCache({ allowStale: true });
  if (cached && !hasKnowledgeScopeTreeItems(treePayload.value)) {
    applyTreeData(cached, { resetSelection: false });
  }
  if (hasKnowledgeScopeTreeItems(treePayload.value)) {
    syncSelectionAfterTreeUpdate();
    if (syncCheckedKeysFromStorage()) return;
    if (checkedKeys.value.length) emitSelectionForKeys(checkedKeys.value);
    if (!isKnowledgeScopeTreeCacheFresh()) {
      void loadKnowledgeScopeTree({ force: true, background: true }).catch(() => {});
    }
    return;
  }
  if (syncCheckedKeysFromStorage()) return;
  if (loading.value || refreshing.value) {
    if (checkedKeys.value.length) emitSelectionForKeys(checkedKeys.value);
    return;
  }
  void fetchTree({ resetSelection: false });
});

onUnmounted(() => {
  window.removeEventListener(KNOWLEDGE_INDEX_UPDATED_EVENT, onKnowledgeIndexUpdated);
});

defineExpose({ reload: reloadTree });
</script>

<template>
  <div class="knowledge-scope-tree">
    <div class="knowledge-scope-tree__head">
      <div class="knowledge-scope-tree__title-row">
        <h2 class="knowledge-scope-tree__title">{{ t("knowledgeSearch.tree.title") }}</h2>
        <IconAction
          :label="t('knowledgeSearch.tree.refresh')"
          :tooltip="t('knowledgeSearch.tree.refreshTooltip')"
          :icon="RefreshOutline"
          :disabled="loading || refreshing"
          :loading="refreshing"
          @click="refreshTree"
        />
      </div>
      <n-input
        v-model:value="filter"
        size="small"
        clearable
        :placeholder="t('knowledgeSearch.tree.filterPlaceholder')"
        class="knowledge-scope-tree__filter"
      />
    </div>

    <PlatformSpin
      :show="loading && !displayTree.length"
      class="knowledge-scope-tree__spin"
      local
    >
      <n-tree
        v-if="displayTree.length"
        block-line
        checkable
        cascade
        :checked-keys="checkedKeys"
        :expanded-keys="expandedKeys"
        :data="displayTree"
        :render-prefix="renderPrefix"
        :render-label="renderLabel"
        @update:checked-keys="onCheckedKeysChange"
        @update:expanded-keys="expandedKeys = $event"
      />
      <n-empty
        v-else-if="!loading"
        size="small"
        :description="t('knowledgeSearch.tree.empty')"
      />
    </PlatformSpin>
    <div
      v-if="selectionSummary"
      class="knowledge-scope-tree__footer"
    >
      <template v-if="selectionSummary.indexPending > 0">
        {{ t("reportGeneration.selectedDocsIndexPendingHint", {
          total: selectionSummary.total,
          ready: selectionSummary.indexReady,
        }) }}
      </template>
      <template v-else>
        {{ t("reportGeneration.selectedDocsHint", {
          count: selectionSummary.total,
        }) }}
      </template>
    </div>
  </div>
</template>

<style scoped>
.knowledge-scope-tree {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  box-sizing: border-box;
}

.knowledge-scope-tree__head {
  flex-shrink: 0;
  padding: 14px 14px 10px;
  border-bottom: 1px solid var(--platform-border);
}

.knowledge-scope-tree__title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.knowledge-scope-tree__title {
  margin: 0;
  font-size: 15px;
  font-weight: 400;
  color: var(--platform-text);
}

.knowledge-scope-tree__filter {
  width: 100%;
}

.knowledge-scope-tree__spin {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 10px 7px 14px;
  display: flex;
  flex-direction: column;
}

.knowledge-scope-tree__spin :deep(.n-spin-container) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.knowledge-scope-tree__spin :deep(.n-spin-content) {
  flex: 1;
  min-height: 0;
}

.knowledge-scope-tree__spin :deep(.n-tree-node-content__text) {
  min-width: 0;
}

.knowledge-scope-tree__node-label {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
  max-width: 100%;
}

.knowledge-scope-tree__node-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.knowledge-scope-tree__node-title--link {
  color: var(--platform-accent);
  cursor: pointer;
}

.knowledge-scope-tree__node-title--link:hover {
  text-decoration: underline;
}

.knowledge-scope-tree__node-tag {
  flex-shrink: 0;
}

.knowledge-scope-tree__footer {
  flex-shrink: 0;
  padding: 4px 14px 8px;
  font-size: 10px;
  line-height: 1.45;
  color: var(--platform-text-tertiary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
