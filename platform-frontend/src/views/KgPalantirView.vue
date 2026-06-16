<script setup>
defineOptions({ name: "KgPalantirView" });
import { usePlatformUi } from "../composables/usePlatformUi";
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  NButton,
  NEmpty,
  NForm,
  NFormItem,
  NInput,
  NModal,
  NSelect,
  NSpin,
  NTag,
} from "naive-ui";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import {
  createKgEntity,
  createKgEntityType,
  createKgRelation,
  createKgRelationType,
  deleteKgEntity,
  deleteKgEntityType,
  deleteKgRelation,
  deleteKgRelationType,
  fetchKgEntity,
  fetchKgEntities,
  fetchKgGraph,
  fetchKgMeta,
  fetchKgRelations,
  updateKgEntity,
  updateKgEntityType,
  updateKgRelationType,
} from "../api/kg.js";

const ui = usePlatformUi();
const route = useRoute();
const router = useRouter();

const TYPE_COLORS = {
  blue: "#2E79B5",
  green: "#1F8A65",
  purple: "#7B64B8",
  orange: "#F0A040",
  pink: "#C85898",
  yellow: "#E8C030",
  gray: "#8888A8",
};

const loading = ref(true);
const meta = ref(null);
const graph = ref({ nodes: [], edges: [] });
const relations = ref([]);
const selectedId = ref(null);
const filterTypeId = ref(null);
const searchQ = ref("");
const graphDepth = ref(1);

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
const allEntities = ref([]);

const selectedEntity = computed(() =>
  graph.value.nodes?.find((n) => n.id === selectedId.value) || null
);

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
  (allEntities.value.length ? allEntities.value : graph.value.nodes || []).map((n) => ({
    label: n.name,
    value: n.id,
  }))
);

const filteredNodes = computed(() => {
  let nodes = graph.value.nodes || [];
  if (filterTypeId.value) {
    const type = meta.value?.entity_types?.find((t) => t.id === filterTypeId.value);
    if (type) nodes = nodes.filter((n) => n.type_code === type.code);
  }
  const q = searchQ.value.trim().toLowerCase();
  if (q) nodes = nodes.filter((n) => n.name.toLowerCase().includes(q));
  return nodes;
});

const graphLayout = computed(() => {
  const nodes = graph.value.nodes || [];
  const edges = graph.value.edges || [];
  if (!nodes.length) return { nodes: [], edges: [], width: 400, height: 200 };

  const idSet = new Set(nodes.map((n) => n.id));
  const adj = new Map();
  for (const n of nodes) adj.set(n.id, []);
  for (const e of edges) {
    if (idSet.has(e.from_entity_id) && idSet.has(e.to_entity_id)) {
      adj.get(e.from_entity_id).push(e.to_entity_id);
    }
  }

  const ranks = new Map();
  const start = selectedId.value || nodes[0]?.id;
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
    const r = ranks.get(n.id) ?? 0;
    maxRank = Math.max(maxRank, r);
    if (!ranks.has(n.id)) ranks.set(n.id, 0);
  }

  const byRank = new Map();
  for (const n of nodes) {
    const r = ranks.get(n.id) ?? 0;
    if (!byRank.has(r)) byRank.set(r, []);
    byRank.get(r).push(n);
  }

  const nodeW = 132;
  const nodeH = 36;
  const rankGap = 72;
  const nodeGap = 20;
  const padding = 24;

  const positioned = [];
  for (let r = 0; r <= maxRank; r += 1) {
    const row = byRank.get(r) || [];
    const rowW = row.length * nodeW + (row.length - 1) * nodeGap;
    let x = padding;
    const y = padding + r * (nodeH + rankGap);
    for (const n of row) {
      positioned.push({ ...n, x, y, w: nodeW, h: nodeH });
      x += nodeW + nodeGap;
    }
  }

  const width = Math.max(
    ...positioned.map((n) => n.x + n.w),
    320
  ) + padding;
  const height = Math.max(
    ...positioned.map((n) => n.y + n.h),
    120
  ) + padding;

  const posMap = Object.fromEntries(positioned.map((n) => [n.id, n]));
  const edgeLines = edges
    .filter((e) => posMap[e.from_entity_id] && posMap[e.to_entity_id])
    .map((e) => {
      const from = posMap[e.from_entity_id];
      const to = posMap[e.to_entity_id];
      return {
        ...e,
        x1: from.x + from.w,
        y1: from.y + from.h / 2,
        x2: to.x,
        y2: to.y + to.h / 2,
        mx: (from.x + from.w + to.x) / 2,
        my: (from.y + from.h / 2 + to.y + to.h / 2) / 2 - 8,
      };
    });

  return { nodes: positioned, edges: edgeLines, width, height };
});

async function loadEntityOptions() {
  try {
    allEntities.value = await fetchKgEntities();
  } catch {
    allEntities.value = graph.value.nodes || [];
  }
}

async function loadAll() {
  loading.value = true;
  try {
    meta.value = await fetchKgMeta();
    await loadEntityOptions();
    graph.value = await fetchKgGraph({
      focusEntityId: selectedId.value || undefined,
      depth: graphDepth.value,
    });
    if (selectedId.value) {
      relations.value = await fetchKgRelations({ entityId: selectedId.value });
      entityDetail.value = await fetchKgEntity(selectedId.value);
    } else {
      relations.value = [];
      entityDetail.value = null;
    }
  } catch (e) {
    ui.error(e.message);
  } finally {
    loading.value = false;
  }
}

async function refreshGraph() {
  try {
    graph.value = await fetchKgGraph({
      focusEntityId: selectedId.value || undefined,
      depth: graphDepth.value,
    });
    if (selectedId.value) {
      relations.value = await fetchKgRelations({ entityId: selectedId.value });
      entityDetail.value = await fetchKgEntity(selectedId.value);
    } else {
      entityDetail.value = null;
    }
    await loadEntityOptions();
    meta.value = await fetchKgMeta();
  } catch (e) {
    ui.error(e.message);
  }
}

function selectEntity(id) {
  selectedId.value = id;
  refreshGraph();
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
    ui.warning("请填写实体名称");
    return;
  }
  try {
    if (editingEntityId.value) {
      await updateKgEntity(editingEntityId.value, {
        type_id: entityForm.value.type_id,
        name: entityForm.value.name.trim(),
        description: entityForm.value.description || "",
      });
      ui.success("实体已更新");
    } else {
      const created = await createKgEntity({
        type_id: entityForm.value.type_id,
        name: entityForm.value.name.trim(),
        description: entityForm.value.description || "",
      });
      selectedId.value = created.id;
      ui.success("实体已创建");
    }
    entityModal.value = false;
    await loadAll();
  } catch (e) {
    ui.error(e.message);
  }
}

async function removeEntity() {
  if (!selectedId.value) return;
  try {
    await deleteKgEntity(selectedId.value);
    selectedId.value = null;
    ui.success("实体已删除");
    await loadAll();
  } catch (e) {
    ui.error(e.message);
  }
}

function openCreateRelation() {
  loadEntityOptions();
  relationForm.value = {
    relation_type_id: relationTypeOptions.value[0]?.value || null,
    from_entity_id: selectedId.value || entityOptions.value[0]?.value || null,
    to_entity_id: null,
    description: "",
  };
  relationModal.value = true;
}

async function saveRelation() {
  try {
    await createKgRelation({
      relation_type_id: relationForm.value.relation_type_id,
      from_entity_id: relationForm.value.from_entity_id,
      to_entity_id: relationForm.value.to_entity_id,
      description: relationForm.value.description || "",
    });
    relationModal.value = false;
    ui.success("关系已创建");
    await refreshGraph();
  } catch (e) {
    ui.error(e.message);
  }
}

async function removeRelation(relationId) {
  try {
    await deleteKgRelation(relationId);
    ui.success("关系已删除");
    await refreshGraph();
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
    ui.success("实体类型已保存");
    await loadAll();
  } catch (e) {
    ui.error(e.message);
  }
}

async function removeEntityType(typeId) {
  try {
    await deleteKgEntityType(typeId);
    ui.success("实体类型已删除");
    if (filterTypeId.value === typeId) filterTypeId.value = null;
    await loadAll();
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
    ui.success("关系类型已保存");
    await loadAll();
  } catch (e) {
    ui.error(e.message);
  }
}

async function removeRelationType(typeId) {
  try {
    await deleteKgRelationType(typeId);
    ui.success("关系类型已删除");
    await loadAll();
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

watch(graphDepth, () => refreshGraph());

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
        <n-input
          v-model:value="searchQ"
          size="small"
          placeholder="搜索实体…"
          clearable
          class="kg-toolbar__search"
        />
        <n-select
          v-model:value="graphDepth"
          size="small"
          :options="[
            { label: '1 跳邻居', value: 1 },
            { label: '2 跳邻居', value: 2 },
          ]"
          class="kg-toolbar__depth"
        />
        <n-button size="small" type="primary" @click="openCreateEntity">新建实体</n-button>
        <n-button size="small" quaternary @click="loadAll">刷新</n-button>
      </div>
    </template>

    <n-spin :show="loading" class="kg-spin">
      <div class="kg-page">
        <aside class="kg-sider">
          <div class="kg-sider__head">
            <span class="kg-sider__title">本体浏览器</span>
            <n-button size="tiny" quaternary @click="openEntityTypeModal(null)">+ 类型</n-button>
          </div>
          <div class="kg-type-list">
            <button
              type="button"
              class="kg-type-item"
              :class="{ active: !filterTypeId }"
              @click="filterTypeId = null"
            >
              <span>全部实体</span>
              <span class="kg-type-item__count">{{ meta?.entity_total || 0 }}</span>
            </button>
            <button
              v-for="t in meta?.entity_types || []"
              :key="t.id"
              type="button"
              class="kg-type-item"
              :class="{ active: filterTypeId === t.id }"
              @click="filterTypeId = t.id"
            >
              <span
                class="kg-type-dot"
                :style="{ background: typeColor(t.color) }"
              />
              <span class="kg-type-item__label">{{ t.label }}</span>
              <span class="kg-type-item__count">{{ t.entity_count }}</span>
              <n-button
                size="tiny"
                quaternary
                class="kg-type-item__edit"
                @click.stop="openEntityTypeModal(t)"
              >
                编辑
              </n-button>
            </button>
          </div>

          <div class="kg-sider__head kg-sider__head--sub">
            <span class="kg-sider__title">关系类型</span>
            <n-button size="tiny" quaternary @click="openRelationTypeModal(null)">+ 类型</n-button>
          </div>
          <div class="kg-rel-type-list">
            <div v-for="rt in meta?.relation_types || []" :key="rt.id" class="kg-rel-type">
              <span>{{ rt.label }}</span>
              <span class="kg-rel-type__count">{{ rt.relation_count }}</span>
              <n-button size="tiny" quaternary @click="openRelationTypeModal(rt)">编辑</n-button>
              <n-button size="tiny" quaternary @click="removeRelationType(rt.id)">删</n-button>
            </div>
          </div>
        </aside>

        <main class="kg-main">
          <div v-if="graphLayout.nodes.length" class="kg-graph-wrap">
            <svg
              class="kg-graph"
              :viewBox="`0 0 ${graphLayout.width} ${graphLayout.height}`"
              preserveAspectRatio="xMidYMid meet"
            >
              <g v-for="edge in graphLayout.edges" :key="edge.id">
                <line
                  :x1="edge.x1"
                  :y1="edge.y1"
                  :x2="edge.x2"
                  :y2="edge.y2"
                  class="kg-graph__edge"
                  :class="{ active: selectedId === edge.from_entity_id || selectedId === edge.to_entity_id }"
                />
                <text :x="edge.mx" :y="edge.my" class="kg-graph__edge-label">
                  {{ edge.relation_type_label }}
                </text>
              </g>
              <g
                v-for="node in graphLayout.nodes"
                :key="node.id"
                class="kg-graph__node"
                :class="{ active: selectedId === node.id }"
                :transform="`translate(${node.x}, ${node.y})`"
                @click="selectEntity(node.id)"
              >
                <rect
                  :width="node.w"
                  :height="node.h"
                  rx="6"
                  class="kg-graph__node-box"
                />
                <circle
                  cx="10"
                  cy="18"
                  r="4"
                  :fill="typeColor(node.type_color)"
                />
                <text x="20" y="22" class="kg-graph__node-label">
                  {{ node.name.length > 11 ? `${node.name.slice(0, 10)}…` : node.name }}
                </text>
              </g>
            </svg>
          </div>
          <n-empty v-else description="暂无实体，点击「新建实体」开始" class="kg-empty" />

          <div class="kg-entity-list">
            <div
              v-for="n in filteredNodes"
              :key="n.id"
              class="kg-entity-chip"
              :class="{ active: selectedId === n.id }"
              @click="selectEntity(n.id)"
            >
              <n-tag size="small" :bordered="false">{{ n.type_label }}</n-tag>
              {{ n.name }}
            </div>
          </div>
        </main>

        <aside class="kg-inspector">
          <template v-if="selectedEntity">
            <h3 class="kg-inspector__title">{{ selectedEntity.name }}</h3>
            <n-tag size="small" type="info">{{ selectedEntity.type_label }}</n-tag>
            <div class="kg-inspector__actions">
              <n-button size="small" @click="openEditEntity">编辑</n-button>
              <n-button size="small" @click="openCreateRelation">添加关系</n-button>
              <n-button
                v-if="entityDetail?.properties?.document_id"
                size="small"
                quaternary
                @click="openLinkedDocument"
              >
                打开关联文档
              </n-button>
              <n-button size="small" type="error" quaternary @click="removeEntity">删除</n-button>
            </div>
            <p
              v-if="entityDetail?.description"
              class="kg-inspector__desc"
            >
              {{ entityDetail.description }}
            </p>
            <div class="kg-inspector__section">
              <div class="kg-inspector__section-title">关联关系 ({{ relations.length }})</div>
              <div v-for="rel in relations" :key="rel.id" class="kg-rel-row">
                <n-tag size="small">{{ rel.relation_type_label }}</n-tag>
                <span class="kg-rel-row__dir">
                  {{ rel.from_entity_id === selectedId ? "出" : "入" }}
                </span>
                <button
                  type="button"
                  class="kg-rel-row__link"
                  @click="selectEntity(
                    rel.from_entity_id === selectedId ? rel.to_entity_id : rel.from_entity_id
                  )"
                >
                  {{
                    rel.from_entity_id === selectedId ? rel.to_name : rel.from_name
                  }}
                </button>
                <n-button size="tiny" quaternary @click="removeRelation(rel.id)">删</n-button>
              </div>
            </div>
          </template>
          <n-empty v-else description="选择实体查看详情" />
        </aside>
      </div>
    </n-spin>

    <n-modal
      v-model:show="entityModal"
      preset="card"
      :title="editingEntityId ? '编辑实体' : '新建实体'"
      style="width: 420px"
    >
      <n-form label-placement="top">
        <n-form-item label="类型">
          <n-select v-model:value="entityForm.type_id" :options="entityTypeOptions" />
        </n-form-item>
        <n-form-item label="名称">
          <n-input v-model:value="entityForm.name" placeholder="实体名称" />
        </n-form-item>
        <n-form-item label="描述">
          <n-input
            v-model:value="entityForm.description"
            type="textarea"
            :rows="3"
            placeholder="可选"
          />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-button @click="entityModal = false">取消</n-button>
        <n-button type="primary" @click="saveEntity">保存</n-button>
      </template>
    </n-modal>

    <n-modal
      v-model:show="relationModal"
      preset="card"
      title="添加关系"
      style="width: 420px"
    >
      <n-form label-placement="top">
        <n-form-item label="关系类型">
          <n-select v-model:value="relationForm.relation_type_id" :options="relationTypeOptions" />
        </n-form-item>
        <n-form-item label="起点实体">
          <n-select v-model:value="relationForm.from_entity_id" :options="entityOptions" />
        </n-form-item>
        <n-form-item label="终点实体">
          <n-select v-model:value="relationForm.to_entity_id" :options="entityOptions" />
        </n-form-item>
        <n-form-item label="说明">
          <n-input v-model:value="relationForm.description" type="textarea" :rows="2" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-button @click="relationModal = false">取消</n-button>
        <n-button type="primary" @click="saveRelation">保存</n-button>
      </template>
    </n-modal>

    <n-modal
      v-model:show="entityTypeModal"
      preset="card"
      :title="editingEntityTypeId ? '编辑实体类型' : '新建实体类型'"
      style="width: 420px"
    >
      <n-form label-placement="top">
        <n-form-item v-if="!editingEntityTypeId" label="Code">
          <n-input v-model:value="entityTypeForm.code" placeholder="如 event" />
        </n-form-item>
        <n-form-item label="显示名">
          <n-input v-model:value="entityTypeForm.label" />
        </n-form-item>
        <n-form-item label="颜色标识">
          <n-select
            v-model:value="entityTypeForm.color"
            :options="Object.keys(TYPE_COLORS).map((k) => ({ label: k, value: k }))"
          />
        </n-form-item>
        <n-form-item label="描述">
          <n-input v-model:value="entityTypeForm.description" type="textarea" :rows="2" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-button v-if="editingEntityTypeId" type="error" quaternary @click="removeEntityType(editingEntityTypeId)">
          删除
        </n-button>
        <n-button @click="entityTypeModal = false">取消</n-button>
        <n-button type="primary" @click="saveEntityType">保存</n-button>
      </template>
    </n-modal>

    <n-modal
      v-model:show="relationTypeModal"
      preset="card"
      :title="editingRelationTypeId ? '编辑关系类型' : '新建关系类型'"
      style="width: 420px"
    >
      <n-form label-placement="top">
        <n-form-item v-if="!editingRelationTypeId" label="Code">
          <n-input v-model:value="relationTypeForm.code" placeholder="如 relates_to" />
        </n-form-item>
        <n-form-item label="显示名">
          <n-input v-model:value="relationTypeForm.label" />
        </n-form-item>
        <n-form-item label="描述">
          <n-input v-model:value="relationTypeForm.description" type="textarea" :rows="2" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-button v-if="editingRelationTypeId" type="error" quaternary @click="removeRelationType(editingRelationTypeId)">
          删除
        </n-button>
        <n-button @click="relationTypeModal = false">取消</n-button>
        <n-button type="primary" @click="saveRelationType">保存</n-button>
      </template>
    </n-modal>
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
  gap: 8px;
  width: 100%;
  min-width: 0;
}

.kg-toolbar__search {
  width: 200px;
}

.kg-toolbar__depth {
  width: 120px;
}

.kg-page {
  display: flex;
  flex: 1;
  min-height: 0;
  height: 100%;
  border: 1px solid var(--platform-border);
  border-radius: var(--platform-radius);
  overflow: hidden;
  background: var(--platform-bg-elevated);
}

.kg-sider {
  width: min(260px, 32vw);
  min-width: 220px;
  border-right: 1px solid var(--platform-border);
  background: var(--platform-bg-secondary);
  padding: 12px;
  overflow: auto;
}

.kg-sider__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.kg-sider__head--sub {
  margin-top: 16px;
}

.kg-sider__title {
  font-size: 13px;
  font-weight: 600;
  color: var(--platform-text-secondary);
}

.kg-type-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.kg-type-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-radius: var(--platform-radius-sm);
  border: 1px solid transparent;
  background: transparent;
  cursor: pointer;
  font-size: 13px;
  color: var(--platform-text-primary);
  text-align: left;
}

.kg-type-item.active {
  background: var(--platform-bg-glass-strong);
  border-color: var(--platform-border);
}

.kg-type-dot {
  width: 8px;
  height: 8px;
  border-radius: 2px;
  flex-shrink: 0;
}

.kg-type-item__label {
  flex: 1;
  min-width: 0;
}

.kg-type-item__count {
  font-size: 12px;
  color: var(--platform-text-tertiary);
}

.kg-type-item__edit {
  flex-shrink: 0;
}

.kg-rel-type-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.kg-rel-type {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--platform-text-secondary);
}

.kg-rel-type__count {
  color: var(--platform-text-tertiary);
}

.kg-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.kg-graph-wrap {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 12px;
}

.kg-graph {
  width: 100%;
  min-height: 240px;
  display: block;
}

.kg-graph__edge {
  stroke: var(--platform-border-strong, #ccc);
  stroke-width: 1;
}

.kg-graph__edge.active {
  stroke: var(--platform-accent);
  stroke-width: 2;
}

.kg-graph__edge-label {
  font-size: 10px;
  fill: var(--platform-text-tertiary);
  text-anchor: middle;
}

.kg-graph__node {
  cursor: pointer;
}

.kg-graph__node-box {
  fill: var(--platform-bg-elevated);
  stroke: var(--platform-border);
}

.kg-graph__node.active .kg-graph__node-box {
  stroke: var(--platform-accent);
  stroke-width: 2;
}

.kg-graph__node-label {
  font-size: 12px;
  fill: var(--platform-text-primary);
}

.kg-entity-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px 12px;
  border-top: 1px solid var(--platform-border);
  max-height: 120px;
  overflow: auto;
}

.kg-entity-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: var(--platform-radius-sm);
  border: 1px solid var(--platform-border);
  font-size: 12px;
  cursor: pointer;
}

.kg-entity-chip.active {
  border-color: var(--platform-accent);
  background: var(--platform-bg-glass-subtle);
}

.kg-inspector {
  width: min(280px, 30vw);
  min-width: 240px;
  border-left: 1px solid var(--platform-border);
  padding: 12px;
  overflow: auto;
}

.kg-inspector__title {
  margin: 0 0 8px;
  font-size: 16px;
}

.kg-inspector__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 12px 0;
}

.kg-inspector__desc {
  margin: 0 0 12px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--platform-text-secondary);
}

.kg-inspector__section-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--platform-text-secondary);
  margin-bottom: 8px;
}

.kg-rel-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  font-size: 12px;
}

.kg-rel-row__dir {
  color: var(--platform-text-tertiary);
}

.kg-rel-row__link {
  flex: 1;
  min-width: 0;
  border: none;
  background: none;
  color: var(--platform-accent);
  cursor: pointer;
  text-align: left;
  padding: 0;
}

.kg-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

@media (max-width: 900px) {
  .kg-page {
    flex-direction: column;
  }

  .kg-sider,
  .kg-inspector {
    width: 100%;
    max-height: 30vh;
    border: none;
    border-bottom: 1px solid var(--platform-border);
  }

  .kg-inspector {
    border-left: none;
  }
}
</style>
