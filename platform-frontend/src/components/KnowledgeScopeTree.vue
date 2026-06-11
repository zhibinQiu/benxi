<script setup>
import { computed, h, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { NEmpty, NIcon, NInput, NSpin, NTag, NTree } from "naive-ui";
import {
  BusinessOutline,
  DocumentTextOutline,
  FolderOpenOutline,
  PeopleOutline,
  PersonOutline } from "@vicons/ionicons5";
import { fetchKnowledgeScopeTree } from "../api/knowledge.js";
import {
  isDocumentIndexReady,
  knowledgeIndexTagProps,
  knowledgeScopeIndexSummary } from "../utils/knowledgeIndex.js";
import {
  readKnowledgeScopeTreeCache,
  writeKnowledgeScopeTreeCache } from "../utils/knowledgeScopeTreeCache.js";
import { navigateWithReturn } from "../utils/navigationReturn.js";

const CHECKED_KEYS_STORAGE = "platform:knowledge-search-checked-keys";

const QA_DOC_LIMIT = 20;

const emit = defineEmits(["selection-change"]);

const route = useRoute();
const router = useRouter();

const loading = ref(true);
const refreshing = ref(false);
const filter = ref("");
const treeData = ref([]);
const expandedKeys = ref([]);
const checkedKeys = ref([]);
const resolving = ref(false);

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

function renderScopeIndexTag(node) {
  const summary = knowledgeScopeIndexSummary(node);
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
    const tag = knowledgeIndexTagProps(option, { forSearch: true });
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
      h("span", { class: "knowledge-scope-tree__node-title", title: option.label }, option.label),
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
  await onCheckedKeysChange(saved);
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

function buildSelectionPayload(docNodes) {
  const totalSelected = docNodes.length;
  const readyNodes = docNodes.filter((n) => n.index_ready);
  const documentIds = readyNodes.map((n) => n.document_id).slice(0, QA_DOC_LIMIT);
  const labels = [...new Set(docNodes.map((n) => n.label).filter(Boolean))];

  let label = "";
  if (totalSelected === 1) {
    label = docNodes[0].label;
  } else if (totalSelected > 1) {
    label = `${totalSelected} 份文档`;
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
  treeData.value = data?.items || [];
  if (resetSelection) {
    expandedKeys.value = [];
    checkedKeys.value = [];
    emit("selection-change", null);
  }
}

async function fetchTree({ background = false, resetSelection = false } = {}) {
  if (background) {
    refreshing.value = true;
  } else {
    loading.value = true;
  }
  try {
    const data = await fetchKnowledgeScopeTree();
    applyTreeData(data, { resetSelection });
    writeKnowledgeScopeTreeCache(data);
  } catch {
    if (!background && !treeData.value.length) {
      applyTreeData({ items: [] }, { resetSelection: true });
    }
  } finally {
    loading.value = false;
    refreshing.value = false;
  }
}

async function loadTree() {
  const cached = readKnowledgeScopeTreeCache();
  if (cached?.items?.length) {
    applyTreeData(cached, { resetSelection: false });
    loading.value = false;
    await restoreCheckedSelection();
    await fetchTree({ background: true });
    return;
  }
  await fetchTree({ resetSelection: false });
  await restoreCheckedSelection();
}

async function reloadTree() {
  await fetchTree({ resetSelection: true });
}

async function onCheckedKeysChange(keys) {
  resolving.value = true;
  try {
    const nextKeys = Array.isArray(keys) ? keys : [];
    checkedKeys.value = nextKeys;
    saveCheckedKeys(nextKeys);
    const docNodes = collectDocumentNodesFromKeys(nextKeys);
    emit("selection-change", docNodes.length ? buildSelectionPayload(docNodes) : null);
  } finally {
    resolving.value = false;
  }
}

onMounted(loadTree);

defineExpose({ reload: reloadTree });
</script>

<template>
  <div class="knowledge-scope-tree">
    <div class="knowledge-scope-tree__head">
      <h2 class="knowledge-scope-tree__title">文档库</h2>
      <n-input
        v-model:value="filter"
        size="small"
        clearable
        placeholder="筛选文档或知识库"
        class="knowledge-scope-tree__filter"
      />
    </div>

    <n-spin :show="loading || resolving" class="knowledge-scope-tree__spin">
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
        description="暂无可检索的知识库，请先在文档中心同步文档"
      />
    </n-spin>

    <p v-if="refreshing" class="knowledge-scope-tree__hint">正在刷新文档树…</p>
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
  padding: 12px 12px 8px;
  border-bottom: 1px solid var(--platform-border);
}

.knowledge-scope-tree__title {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--platform-text);
}

.knowledge-scope-tree__filter {
  width: 100%;
}

.knowledge-scope-tree__spin {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 8px 6px 12px;
}

.knowledge-scope-tree__spin :deep(.n-spin-content) {
  min-height: 120px;
}

.knowledge-scope-tree__spin :deep(.n-tree-node-content__text) {
  min-width: 0;
}

.knowledge-scope-tree__node-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
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

.knowledge-scope-tree__hint {
  flex-shrink: 0;
  margin: 0;
  padding: 8px 12px 12px;
  font-size: 11px;
  line-height: 1.45;
  color: var(--platform-text-tertiary);
  border-top: 1px solid var(--platform-border);
}
</style>
