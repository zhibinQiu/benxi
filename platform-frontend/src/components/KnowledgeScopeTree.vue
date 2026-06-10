<script setup>
import { computed, h, onMounted, ref, watch } from "vue";
import { NEmpty, NIcon, NInput, NSpin, NTree } from "naive-ui";
import {
  BusinessOutline,
  DocumentTextOutline,
  FolderOpenOutline,
  PeopleOutline,
  PersonOutline,
} from "@vicons/ionicons5";
import { fetchKnowledgeScopeTree, fetchLibraryDocuments } from "../api/knowledge.js";
import { SCOPE_LABELS } from "../constants/documentScope.js";

const props = defineProps({
  selectedKey: { type: String, default: "" },
});

const emit = defineEmits(["update:selectedKey", "selection-change"]);

const loading = ref(true);
const filter = ref("");
const treeData = ref([]);
const expandedKeys = ref([]);
const knowflowEnabled = ref(false);

const scopeIcons = {
  company: BusinessOutline,
  department: PeopleOutline,
  team: PeopleOutline,
  personal: PersonOutline,
  library: FolderOpenOutline,
  document: DocumentTextOutline,
};

function nodeIcon(node) {
  if (node.type === "document") return DocumentTextOutline;
  if (node.type === "library") return FolderOpenOutline;
  if (node.scope && scopeIcons[node.scope]) return scopeIcons[node.scope];
  return FolderOpenOutline;
}

function renderPrefix({ option }) {
  return h(NIcon, { size: 15, component: nodeIcon(option) });
}

function cloneFilterTree(nodes, kw) {
  const out = [];
  for (const node of nodes || []) {
    const label = String(node.label || "").toLowerCase();
    const childMatches = cloneFilterTree(node.children || [], kw);
    if (label.includes(kw) || childMatches.length) {
      out.push({
        ...node,
        children: childMatches.length ? childMatches : node.children,
      });
    }
  }
  return out;
}

const displayTree = computed(() => {
  const kw = filter.value.trim().toLowerCase();
  if (!kw) return treeData.value;
  return cloneFilterTree(treeData.value, kw);
});

function findNode(nodes, key) {
  for (const node of nodes || []) {
    if (node.key === key) return node;
    const found = findNode(node.children, key);
    if (found) return found;
  }
  return null;
}

async function ensureLibraryDocuments(node) {
  const datasetId = node.dataset_id;
  if (!datasetId) return node;
  if (node.children?.some((c) => c.type === "document")) return node;
  const data = await fetchLibraryDocuments(datasetId, { pageSize: 100 });
  const docs = (data.items || []).map((doc) => ({
    key: `doc:${doc.document_id}`,
    label: doc.title || doc.file_name || "未命名文档",
    type: "document",
    document_id: doc.document_id,
    dataset_id: datasetId,
    scope: doc.scope,
    isLeaf: true,
  }));
  node.children = docs;
  node.isLeaf = docs.length === 0;
  treeData.value = [...treeData.value];
  return node;
}

async function loadTree() {
  loading.value = true;
  try {
    const data = await fetchKnowledgeScopeTree();
    treeData.value = data.items || [];
    knowflowEnabled.value = Boolean(data.knowflow_enabled);
    expandedKeys.value = treeData.value.map((n) => n.key);
  } catch {
    treeData.value = [];
  } finally {
    loading.value = false;
  }
}

async function handleLoad(node) {
  const source = findNode(treeData.value, node.key);
  if (source?.type === "library") {
    await ensureLibraryDocuments(source);
  }
}

async function resolveSelection(key) {
  if (!key) {
    emit("update:selectedKey", "");
    emit("selection-change", null);
    return;
  }
  emit("update:selectedKey", key);
  const option = findNode(treeData.value, key);
  if (!option) return;

  if (option.type === "document") {
    emit("selection-change", {
      type: "document",
      label: option.label,
      documentIds: [option.document_id],
      datasetId: option.dataset_id,
      scope: option.scope,
    });
    return;
  }

  if (option.type === "library") {
    await ensureLibraryDocuments(option);
    const docIds = (option.children || [])
      .filter((c) => c.type === "document")
      .map((c) => c.document_id)
      .filter(Boolean);
    emit("selection-change", {
      type: "library",
      label: option.label,
      documentIds: docIds.slice(0, 20),
      datasetId: option.dataset_id,
      scope: option.scope,
    });
    return;
  }

  if (option.type === "scope") {
    const docIds = [];
    for (const lib of option.children || []) {
      await ensureLibraryDocuments(lib);
      for (const doc of lib.children || []) {
        if (doc.document_id) docIds.push(doc.document_id);
      }
    }
    emit("selection-change", {
      type: "scope",
      label: option.label || SCOPE_LABELS[option.scope] || option.scope,
      documentIds: docIds.slice(0, 20),
      scope: option.scope,
    });
  }
}

function onSelect(keys) {
  resolveSelection(Array.isArray(keys) ? keys[0] : keys);
}

onMounted(loadTree);

watch(
  () => props.selectedKey,
  (key) => {
    if (key && !expandedKeys.value.includes(key)) {
      expandedKeys.value = [...expandedKeys.value, key];
    }
  }
);

defineExpose({ reload: loadTree });
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

    <n-spin :show="loading" class="knowledge-scope-tree__spin">
      <n-tree
        v-if="displayTree.length"
        block-line
        selectable
        :selected-keys="selectedKey ? [selectedKey] : []"
        :expanded-keys="expandedKeys"
        :data="displayTree"
        :render-prefix="renderPrefix"
        :on-load="handleLoad"
        @update:selected-keys="onSelect"
        @update:expanded-keys="expandedKeys = $event"
      />
      <n-empty
        v-else-if="!loading"
        size="small"
        description="暂无可检索的知识库，请先在文档中心同步文档"
      />
    </n-spin>

    <p v-if="!knowflowEnabled && !loading" class="knowledge-scope-tree__hint">
      知识服务未就绪，问答将使用本地关键词检索。
    </p>
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
