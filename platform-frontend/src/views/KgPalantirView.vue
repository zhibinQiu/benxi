<script setup>
defineOptions({ name: "KgPalantirView" });
import { usePlatformUi } from "../composables/usePlatformUi";
import { computed, nextTick, onMounted, ref, watch } from "vue";
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
  NTabPane,
  NTabs,
  NTag,
} from "naive-ui";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import KgGraphCanvas from "../components/KgGraphCanvas.vue";
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
const browseTypeId = ref(null);
const browseTypeEntities = ref([]);
const browseTypeLoading = ref(false);

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

let searchTimer = null;

const selectedEntity = computed(() =>
  graph.value.nodes?.find((n) => n.id === selectedId.value) ||
  entityList.value.find((n) => n.id === selectedId.value) ||
  null
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
  entityList.value.map((n) => ({
    label: n.name,
    value: n.id,
  }))
);

const typeFilterOptions = computed(() => [
  { label: "全部类型", value: null },
  ...(meta.value?.entity_types || []).map((t) => ({
    label: `${t.label} (${t.entity_count})`,
    value: t.id,
  })),
]);

const browseTypeMeta = computed(() =>
  (meta.value?.entity_types || []).find((t) => t.id === browseTypeId.value) || null
);

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
      adj.get(e.to_entity_id).push(e.from_entity_id);
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
      positioned.some((n) => n.id === e.from_entity_id) &&
      positioned.some((n) => n.id === e.to_entity_id)
  );

  return { nodes: positioned, edges: edgeLines, width, height };
});

async function loadEntityList() {
  listLoading.value = true;
  try {
    entityList.value = await fetchKgEntities({
      typeId: filterTypeId.value || undefined,
      q: searchQ.value.trim() || undefined,
    });
  } catch (e) {
    ui.error(e.message);
  } finally {
    listLoading.value = false;
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
  if (filterTypeId.value && filterTypeId.value === browseTypeId.value) {
    filterTypeId.value = null;
  }
  browseTypeId.value = null;
  browseTypeEntities.value = [];
}

async function browseEntityType(typeId) {
  if (browseTypeId.value === typeId) {
    clearBrowseType();
    return;
  }
  await loadBrowseByType(typeId);
}

async function loadAll() {
  loading.value = true;
  try {
    meta.value = await fetchKgMeta();
    await loadEntityList();
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
    await nextTick();
    graphCanvasRef.value?.fitView?.();
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
      await nextTick();
      graphCanvasRef.value?.focusNode?.(selectedId.value);
    } else {
      entityDetail.value = null;
      await nextTick();
      graphCanvasRef.value?.fitView?.();
    }
    meta.value = await fetchKgMeta();
    await loadEntityList();
  } catch (e) {
    ui.error(e.message);
  }
}

function selectEntity(id) {
  if (selectedId.value === id) {
    nextTick(() => graphCanvasRef.value?.focusNode?.(id));
    return;
  }
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
    ui.warning("请选择终点实体");
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
        <n-select
          v-model:value="graphDepth"
          size="small"
          :options="[
            { label: '子图 1 跳', value: 1 },
            { label: '子图 2 跳', value: 2 },
          ]"
          class="kg-toolbar__depth"
        />
        <n-button size="small" type="primary" @click="openCreateEntity">新建实体</n-button>
        <n-button size="small" secondary @click="openCreateRelation">添加关系</n-button>
        <n-button size="small" quaternary @click="loadAll">刷新</n-button>
      </div>
    </template>

    <n-spin :show="loading" class="kg-spin">
      <div class="kg-page">
        <aside class="kg-panel kg-panel--left">
          <n-tabs v-model:value="leftTab" type="line" size="small" class="kg-tabs">
            <n-tab-pane name="entities" tab="实体查询">
              <div class="kg-search-block">
                <n-input
                  v-model:value="searchQ"
                  size="small"
                  placeholder="按名称或描述搜索…"
                  clearable
                />
                <n-select
                  v-model:value="filterTypeId"
                  size="small"
                  :options="typeFilterOptions"
                  class="kg-search-block__type"
                />
              </div>
              <div class="kg-list-meta">
                共 {{ meta?.entity_total || 0 }} 个实体
                <span v-if="searchQ.trim()"> · 当前 {{ entityList.length }} 条结果</span>
              </div>
              <n-spin :show="listLoading" class="kg-list-spin">
                <div v-if="entityList.length" class="kg-entity-list">
                  <button
                    v-for="item in entityList"
                    :key="item.id"
                    type="button"
                    class="kg-glass-item kg-entity-row"
                    :class="{ 'is-active': selectedId === item.id }"
                    @click="selectEntity(item.id)"
                  >
                    <span
                      class="kg-entity-row__dot"
                      :style="{ background: typeColor(item.type_color) }"
                    />
                    <span class="kg-entity-row__body">
                      <span class="kg-entity-row__name">{{ item.name }}</span>
                      <span class="kg-entity-row__type">{{ item.type_label }}</span>
                    </span>
                  </button>
                </div>
                <n-empty
                  v-else
                  size="small"
                  description="暂无匹配实体"
                  class="kg-list-empty"
                />
              </n-spin>
            </n-tab-pane>

            <n-tab-pane name="ontology" tab="本体设置">
              <div class="kg-ontology-section">
                <div class="kg-ontology-head">
                  <span>实体类型</span>
                  <n-button size="tiny" quaternary @click="openEntityTypeModal(null)">
                    新建
                  </n-button>
                </div>
                <div class="kg-ontology-list">
                  <button
                    v-for="t in meta?.entity_types || []"
                    :key="t.id"
                    type="button"
                    class="kg-glass-item kg-ontology-item"
                    :class="{ 'is-active': browseTypeId === t.id }"
                    @click="browseEntityType(t.id)"
                  >
                    <span class="kg-ontology-item__dot" :style="{ background: typeColor(t.color) }" />
                    <span class="kg-ontology-item__label">{{ t.label }}</span>
                    <span class="kg-ontology-item__count">{{ t.entity_count }}</span>
                    <n-button
                      size="tiny"
                      quaternary
                      class="kg-ontology-item__edit"
                      @click.stop="openEntityTypeModal(t)"
                    >
                      编辑
                    </n-button>
                  </button>
                </div>
              </div>
              <div class="kg-ontology-section">
                <div class="kg-ontology-head">
                  <span>关系类型</span>
                  <n-button size="tiny" quaternary @click="openRelationTypeModal(null)">
                    新建
                  </n-button>
                </div>
                <div class="kg-ontology-list">
                  <div
                    v-for="rt in meta?.relation_types || []"
                    :key="rt.id"
                    class="kg-ontology-item"
                  >
                    <span class="kg-ontology-item__label">{{ rt.label }}</span>
                    <span class="kg-ontology-item__count">{{ rt.relation_count }}</span>
                    <n-button size="tiny" quaternary @click="openRelationTypeModal(rt)">编辑</n-button>
                  </div>
                </div>
              </div>
              <p class="kg-ontology-tip">
                点击实体类型可在右侧底部浏览该类型下的全部实体；点选后按顶栏跳数展示关系子图。
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
            <n-empty description="暂无实体，点击「新建实体」开始构建图谱">
              <template #extra>
                <n-button size="small" type="primary" @click="openCreateEntity">
                  新建实体
                </n-button>
              </template>
            </n-empty>
          </div>
        </main>

        <aside class="kg-panel kg-panel--right">
          <div class="kg-detail-main">
            <template v-if="selectedEntity">
              <div class="kg-detail-head">
                <h3 class="kg-detail-title">{{ selectedEntity.name }}</h3>
                <n-tag size="small" :bordered="false">{{ selectedEntity.type_label }}</n-tag>
              </div>
              <p v-if="entityDetail?.description" class="kg-detail-desc">
                {{ entityDetail.description }}
              </p>
              <div class="kg-detail-actions">
                <n-button size="small" type="primary" @click="openEditEntity">编辑</n-button>
                <n-button size="small" @click="openCreateRelation">添加关系</n-button>
                <n-button
                  v-if="entityDetail?.properties?.document_id"
                  size="small"
                  quaternary
                  @click="openLinkedDocument"
                >
                  关联文档
                </n-button>
                <n-button size="small" type="error" quaternary @click="removeEntity">删除</n-button>
              </div>
              <div class="kg-detail-section">
                <div class="kg-detail-section__title">
                  关联关系
                  <span class="kg-detail-section__count">{{ relations.length }}</span>
                </div>
                <div v-for="rel in relations" :key="rel.id" class="kg-rel-item">
                  <n-tag size="small" :bordered="false">{{ rel.relation_type_label }}</n-tag>
                  <button
                    type="button"
                    class="kg-rel-item__link"
                    @click="
                      selectEntity(
                        rel.from_entity_id === selectedId ? rel.to_entity_id : rel.from_entity_id
                      )
                    "
                  >
                    {{ rel.from_entity_id === selectedId ? rel.to_name : rel.from_name }}
                  </button>
                  <n-button size="tiny" quaternary @click="removeRelation(rel.id)">删除</n-button>
                </div>
                <n-empty v-if="!relations.length" size="small" description="暂无关联关系" />
              </div>
            </template>
            <div v-else-if="browseTypeMeta" class="kg-detail-placeholder">
              <p class="kg-detail-browse-hint">
                已选类型「{{ browseTypeMeta.label }}」，请从下方列表点选实体，将展示
                {{ graphDepth === 2 ? "二" : "一" }}跳关系子图。
              </p>
            </div>
            <div v-else class="kg-detail-placeholder">
              <n-empty size="small" description="选择实体或在左侧点选类型浏览" />
            </div>
          </div>

          <div v-if="browseTypeId && browseTypeMeta" class="kg-type-browse">
            <div class="kg-type-browse__head">
              <div class="kg-type-browse__title">
                <span
                  class="kg-type-browse__dot"
                  :style="{ background: typeColor(browseTypeMeta.color) }"
                />
                {{ browseTypeMeta.label }}
                <span class="kg-type-browse__count">{{ browseTypeEntities.length }}</span>
              </div>
              <n-button size="tiny" quaternary @click="clearBrowseType">关闭</n-button>
            </div>
            <n-spin :show="browseTypeLoading" class="kg-type-browse__spin">
              <div v-if="browseTypeEntities.length" class="kg-type-browse__list">
                <button
                  v-for="item in browseTypeEntities"
                  :key="item.id"
                  type="button"
                  class="kg-glass-item kg-type-browse__item"
                  :class="{ 'is-active': selectedId === item.id }"
                  @click="selectEntity(item.id)"
                >
                  <span class="kg-type-browse__item-name">{{ item.name }}</span>
                  <span
                    v-if="item.properties?.document_id"
                    class="kg-type-browse__item-tag"
                  >
                    文档
                  </span>
                </button>
              </div>
              <n-empty v-else size="small" description="该类型下暂无实体" />
            </n-spin>
          </div>
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
          <n-select
            v-model:value="relationForm.from_entity_id"
            filterable
            :options="entityOptions"
          />
        </n-form-item>
        <n-form-item label="终点实体">
          <n-select
            v-model:value="relationForm.to_entity_id"
            filterable
            placeholder="选择关联实体"
            :options="entityOptions"
          />
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
        <n-button
          v-if="editingEntityTypeId"
          type="error"
          quaternary
          @click="removeEntityType(editingEntityTypeId)"
        >
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
        <n-button
          v-if="editingRelationTypeId"
          type="error"
          quaternary
          @click="removeRelationType(editingRelationTypeId)"
        >
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

.kg-panel {
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.kg-panel--left {
  width: min(300px, 34vw);
  min-width: 260px;
  border-right: 1px solid var(--platform-border);
  background: var(--platform-bg-secondary);
}

.kg-panel--center {
  flex: 1;
  min-width: 0;
}

.kg-panel--right {
  width: min(300px, 32vw);
  min-width: 260px;
  border-left: 1px solid var(--platform-border);
  background: var(--platform-bg-secondary);
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.kg-detail-main {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 16px;
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

.kg-entity-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
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

.kg-empty-wrap,
.kg-detail-placeholder {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
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
  gap: 6px;
  margin-bottom: 16px;
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

.kg-type-browse {
  flex-shrink: 0;
  max-height: min(42vh, 320px);
  min-height: 140px;
  display: flex;
  flex-direction: column;
  border-top: 1px solid var(--platform-border);
  background: color-mix(in srgb, var(--platform-bg) 70%, var(--platform-bg-secondary));
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
}

.kg-type-browse__spin :deep(.n-spin-content) {
  height: 100%;
  min-height: 0;
}

.kg-type-browse__list {
  max-height: calc(min(42vh, 320px) - 48px);
  overflow: auto;
  padding: 0 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
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
