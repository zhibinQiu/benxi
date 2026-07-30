<template>
  <div class="kg-workbench">
    <aside class="kg-workbench__left">
      <n-tabs
        v-model:value="listKind"
        type="line"
        size="small"
        class="kg-workbench__tabs"
      >
        <n-tab-pane name="entity" :tab="entityTabLabel" display-directive="if">
          <div class="kg-workbench__pane">
            <n-select
              v-model:value="filterType"
              size="small"
              clearable
              filterable
              placeholder="按类型筛选"
              :options="typeFilterOptions"
            />
            <n-input v-model:value="keyword" size="small" clearable placeholder="搜索实体…" />
            <n-button block size="small" secondary @click="startCreateEntity">+ 新建实体</n-button>
            <div class="kg-workbench__list">
              <button
                v-for="ent in filteredEntities"
                :key="ent.id"
                type="button"
                class="kg-workbench__item"
                :class="{ 'is-active': listKind === 'entity' && selectedId === ent.id }"
                :data-entity-id="ent.id"
                @click="selectEntity(ent)"
              >
                <span class="kg-workbench__dot" :style="{ background: colorOf(ent.type_color) }" />
                <span class="kg-workbench__item-main">
                  <span class="kg-workbench__item-label">{{ ent.name }}</span>
                  <span class="kg-workbench__item-code">{{ ent.type_label || ent.type_code }}</span>
                </span>
              </button>
              <div v-if="!filteredEntities.length" class="kg-workbench__empty">
                {{ loading ? "加载中…" : "暂无实体" }}
              </div>
            </div>
          </div>
        </n-tab-pane>

        <n-tab-pane name="relation" :tab="relationTabLabel" display-directive="if">
          <div class="kg-workbench__pane">
            <n-select
              v-model:value="filterRelType"
              size="small"
              clearable
              filterable
              placeholder="按关系类型筛选"
              :options="relationTypeOptions"
            />
            <n-input v-model:value="keyword" size="small" clearable placeholder="搜索关系…" />
            <n-button block size="small" secondary @click="startCreateRelation">+ 添加关系</n-button>
            <div class="kg-workbench__list">
              <button
                v-for="rel in filteredRelations"
                :key="rel.id"
                type="button"
                class="kg-workbench__item"
                :class="{ 'is-active': listKind === 'relation' && selectedRelId === rel.id }"
                @click="selectRelation(rel)"
              >
                <span class="kg-workbench__item-main">
                  <span class="kg-workbench__item-label">{{ rel.type_label || rel.type_code }}</span>
                  <span class="kg-workbench__item-code">{{ relationSummary(rel) }}</span>
                </span>
              </button>
              <div v-if="!filteredRelations.length" class="kg-workbench__empty">
                {{ loadingRelations ? "加载中…" : "暂无关系" }}
              </div>
            </div>
          </div>
        </n-tab-pane>
      </n-tabs>
    </aside>

    <main class="kg-workbench__center">
      <KgGraphExplore
        ref="graphRef"
        hide-detail-panel
        :graph-data="graphData"
        :loading="loadingGraph"
        :selected-id="selectedId"
        @refresh="(id, depth) => emit('refresh-graph', id, depth)"
        @select-entity="onSelectFromGraph"
        @trace-concept="(p) => emit('trace-concept', p)"
        @focus-entity="(id) => emit('focus-entity', id)"
      />
    </main>

    <aside class="kg-workbench__right">
      <div class="kg-workbench__right-hd">
        <div>
          <strong>{{ rightTitle }}</strong>
          <n-text depth="3" style="font-size: 12px; display: block">
            {{ listKind === "entity" ? "实体实例" : "关系实例" }}
          </n-text>
        </div>
        <n-button text size="tiny" @click="showExtract = true">LLM 抽取</n-button>
      </div>

      <div v-if="!editing" class="kg-workbench__placeholder">
        从左侧选择实体或关系，或点击「新建 / 添加」
      </div>

      <!-- 实体编辑 / 新建 -->
      <template v-else-if="listKind === 'entity'">
        <n-form :model="form" label-placement="top" size="small" class="kg-workbench__form">
          <n-form-item label="实体类型" required>
            <n-select
              v-model:value="form.type_code"
              :options="typeOptions"
              :disabled="!isCreate"
              filterable
            />
          </n-form-item>
          <n-form-item label="名称" required>
            <n-input v-model:value="form.name" />
          </n-form-item>
          <n-form-item label="描述">
            <n-input v-model:value="form.description" type="textarea" :rows="3" />
          </n-form-item>
          <n-space justify="space-between">
            <n-button v-if="!isCreate" type="error" secondary size="small" @click="handleDeleteEntity">
              删除
            </n-button>
            <span v-else />
            <n-space>
              <n-button size="small" @click="editing = false">取消</n-button>
              <n-button type="primary" size="small" :loading="saving" @click="handleSaveEntity">
                保存
              </n-button>
            </n-space>
          </n-space>
        </n-form>

        <template v-if="!isCreate && selectedId">
          <n-divider style="margin: 16px 0 10px">关联关系</n-divider>
          <n-space vertical :size="8">
            <div v-for="rel in entityRelations" :key="rel.id" class="kg-workbench__rel">
              <div>
                <strong>{{ rel.type_label || rel.type_code }}</strong>
                <n-text depth="3" style="font-size:11px;display:block">
                  {{ relDir(rel) }}
                </n-text>
              </div>
              <n-button text type="error" size="tiny" @click="removeRelation(rel.id)">删</n-button>
            </div>
            <n-button size="small" dashed block @click="showAddRel = !showAddRel">
              + 添加关系
            </n-button>
            <div v-if="showAddRel" class="kg-workbench__add-rel">
              <n-select
                v-model:value="newRel.type_code"
                size="small"
                filterable
                placeholder="关系类型"
                :options="relationTypeOptions"
              />
              <n-select
                v-model:value="newRel.to_entity_id"
                size="small"
                filterable
                placeholder="目标实体"
                :options="entityOptions"
              />
              <n-button size="small" type="primary" :loading="savingRel" @click="addRelationFromEntity">
                添加
              </n-button>
            </div>
          </n-space>
          <n-button
            block
            secondary
            size="small"
            style="margin-top: 14px"
            @click="emit('trace-concept', { code: form.type_code })"
          >
            追溯所属概念 →
          </n-button>
        </template>
      </template>

      <!-- 关系详情 / 新建 -->
      <template v-else>
        <n-form :model="relForm" label-placement="top" size="small" class="kg-workbench__form">
          <n-form-item label="关系类型" required>
            <n-select
              v-model:value="relForm.type_code"
              :options="relationTypeOptions"
              :disabled="!isCreate"
              filterable
            />
          </n-form-item>
          <n-form-item label="起点实体" required>
            <n-select
              v-model:value="relForm.from_entity_id"
              :options="allEntityOptions"
              :disabled="!isCreate"
              filterable
            />
          </n-form-item>
          <n-form-item label="终点实体" required>
            <n-select
              v-model:value="relForm.to_entity_id"
              :options="allEntityOptions"
              :disabled="!isCreate"
              filterable
            />
          </n-form-item>
          <n-space justify="space-between">
            <n-button
              v-if="!isCreate && selectedRelId"
              type="error"
              secondary
              size="small"
              @click="handleDeleteRelation"
            >
              删除
            </n-button>
            <span v-else />
            <n-space>
              <n-button size="small" @click="editing = false">取消</n-button>
              <n-button
                v-if="isCreate"
                type="primary"
                size="small"
                :loading="savingRel"
                @click="handleSaveRelation"
              >
                保存
              </n-button>
            </n-space>
          </n-space>
        </n-form>
      </template>
    </aside>

    <n-drawer v-model:show="showExtract" :width="480" placement="right">
      <n-drawer-content title="LLM 抽取" closable>
        <KgExtractionPanel :entity-types="entityTypes" @extracted="onExtracted" />
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { usePlatformUi } from "../../composables/usePlatformUi";
import KgGraphExplore from "../kg/KgGraphExplore.vue";
import KgExtractionPanel from "../kg/KgExtractionPanel.vue";
import {
  createKgEntity,
  updateKgEntity,
  deleteKgEntity,
  createKgRelation,
  deleteKgRelation,
  fetchKgRelations,
} from "../../api/kg.js";

const props = defineProps({
  entities: { type: Array, default: () => [] },
  entityTypes: { type: Array, default: () => [] },
  relationTypes: { type: Array, default: () => [] },
  graphData: { type: Object, default: () => ({ nodes: [], edges: [] }) },
  loading: Boolean,
  loadingGraph: Boolean,
});

const emit = defineEmits([
  "refresh",
  "refresh-graph",
  "trace-concept",
  "focus-entity",
  "extracted",
]);

const ui = usePlatformUi();
const graphRef = ref(null);
const listKind = ref("entity");
const filterType = ref(null);
const filterRelType = ref(null);
const keyword = ref("");
const selectedId = ref("");
const selectedRelId = ref("");
const editing = ref(false);
const isCreate = ref(false);
const saving = ref(false);
const savingRel = ref(false);
const showAddRel = ref(false);
const showExtract = ref(false);
const entityRelations = ref([]);
const allRelations = ref([]);
const loadingRelations = ref(false);

const form = reactive({
  type_code: "",
  name: "",
  description: "",
});

const newRel = reactive({
  type_code: null,
  to_entity_id: null,
});

const relForm = reactive({
  type_code: null,
  from_entity_id: null,
  to_entity_id: null,
});

const COLOR_MAP = {
  blue: "#3b82f6",
  green: "#22c55e",
  purple: "#a855f7",
  orange: "#f97316",
  pink: "#ec4899",
  yellow: "#eab308",
  teal: "#14b8a6",
  indigo: "#6366f1",
  cyan: "#06b6d4",
  gray: "#94a3b8",
};

function colorOf(c) {
  if (!c) return COLOR_MAP.gray;
  if (String(c).startsWith("#")) return c;
  return COLOR_MAP[c] || COLOR_MAP.gray;
}

const typeOptions = computed(() =>
  props.entityTypes.map((et) => ({ label: `${et.label} (${et.code})`, value: et.code }))
);
const typeFilterOptions = computed(() => typeOptions.value);
const relationTypeOptions = computed(() =>
  props.relationTypes.map((rt) => ({ label: `${rt.label} (${rt.code})`, value: rt.code }))
);
const entityOptions = computed(() =>
  props.entities
    .filter((e) => e.id !== selectedId.value)
    .map((e) => ({ label: `${e.name} (${e.type_code})`, value: e.id }))
);
const allEntityOptions = computed(() =>
  props.entities.map((e) => ({ label: `${e.name} (${e.type_code})`, value: e.id }))
);

const filteredEntities = computed(() => {
  const q = keyword.value.trim().toLowerCase();
  return props.entities.filter((e) => {
    if (filterType.value && e.type_code !== filterType.value) return false;
    if (!q) return true;
    return (
      String(e.name || "").toLowerCase().includes(q) ||
      String(e.type_code || "").toLowerCase().includes(q) ||
      String(e.type_label || "").toLowerCase().includes(q)
    );
  });
});

const filteredRelations = computed(() => {
  const q = keyword.value.trim().toLowerCase();
  return allRelations.value.filter((r) => {
    if (filterRelType.value && r.type_code !== filterRelType.value) return false;
    if (!q) return true;
    const summary = relationSummary(r).toLowerCase();
    return (
      String(r.type_code || "").toLowerCase().includes(q) ||
      String(r.type_label || "").toLowerCase().includes(q) ||
      summary.includes(q)
    );
  });
});

const entityTabLabel = computed(() => `实体 ${props.entities.length}`);
const relationTabLabel = computed(() => `关系 ${allRelations.value.length}`);

const rightTitle = computed(() => {
  if (!editing.value) return "属性";
  if (listKind.value === "entity") return isCreate.value ? "新建实体" : "编辑实体";
  return isCreate.value ? "添加关系" : "关系详情";
});

function entityName(id) {
  return props.entities.find((e) => e.id === id)?.name || id || "—";
}

function relationSummary(rel) {
  return `${entityName(rel.from_entity_id)} → ${entityName(rel.to_entity_id)}`;
}

function relDir(rel) {
  const fromName = entityName(rel.from_entity_id);
  const toName = entityName(rel.to_entity_id);
  if (rel.from_entity_id === selectedId.value) return `→ ${toName}`;
  if (rel.to_entity_id === selectedId.value) return `← ${fromName}`;
  return `${fromName} → ${toName}`;
}

async function loadAllRelations() {
  loadingRelations.value = true;
  try {
    const res = await fetchKgRelations({});
    allRelations.value = Array.isArray(res) ? res : res?.items || [];
  } catch (err) {
    if (err?.code === "ROUTE_ABORT") return;
    allRelations.value = [];
  } finally {
    loadingRelations.value = false;
  }
}

async function loadEntityRelations(entityId) {
  if (!entityId) {
    entityRelations.value = [];
    return;
  }
  try {
    const res = await fetchKgRelations({ entityId });
    entityRelations.value = Array.isArray(res) ? res : res?.items || [];
  } catch {
    entityRelations.value = [];
  }
}

watch(listKind, () => {
  // 切换 Tab 时清空编辑态与搜索；选中态由 select* 在 nextTick 中恢复
  keyword.value = "";
  showAddRel.value = false;
  selectedId.value = "";
  selectedRelId.value = "";
  editing.value = false;
  isCreate.value = false;
});

function scrollEntityIntoView(id) {
  if (!id) return;
  nextTick(() => {
    const el = document.querySelector(
      `.kg-workbench__list [data-entity-id="${CSS.escape(String(id))}"]`
    );
    el?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  });
}

/** 确保目标实体出现在左侧列表（清筛选后滚动） */
function revealEntityInList(ent) {
  if (!ent?.id) return;
  if (filterType.value && ent.type_code !== filterType.value) {
    filterType.value = null;
  }
  const q = keyword.value.trim().toLowerCase();
  if (q) {
    const hay = `${ent.name || ""} ${ent.type_code || ""} ${ent.type_label || ""}`.toLowerCase();
    if (!hay.includes(q)) keyword.value = "";
  }
  scrollEntityIntoView(ent.id);
}

function selectEntity(ent, { fromGraph = false } = {}) {
  const switchTab = listKind.value !== "entity";
  if (switchTab) listKind.value = "entity";
  const apply = () => {
    selectedId.value = ent.id;
    selectedRelId.value = "";
    isCreate.value = false;
    editing.value = true;
    showAddRel.value = false;
    form.type_code = ent.type_code;
    form.name = ent.name || "";
    form.description = ent.description || "";
    loadEntityRelations(ent.id);
    if (fromGraph) revealEntityInList(ent);
    else scrollEntityIntoView(ent.id);
    graphRef.value?.setFocus?.(ent.id);
    emit("refresh-graph", ent.id, 1);
  };
  if (switchTab) nextTick(apply);
  else apply();
}

function selectRelation(rel) {
  const switchTab = listKind.value !== "relation";
  if (switchTab) listKind.value = "relation";
  const apply = () => {
    selectedRelId.value = rel.id;
    selectedId.value = rel.from_entity_id || "";
    isCreate.value = false;
    editing.value = true;
    relForm.type_code = rel.type_code;
    relForm.from_entity_id = rel.from_entity_id;
    relForm.to_entity_id = rel.to_entity_id;
    if (rel.from_entity_id) {
      graphRef.value?.setFocus?.(rel.from_entity_id);
      emit("refresh-graph", rel.from_entity_id, 1);
    }
  };
  if (switchTab) nextTick(apply);
  else apply();
}

function onSelectFromGraph(node) {
  const found = props.entities.find((e) => e.id === node.id);
  if (found) {
    selectEntity(found, { fromGraph: true });
    return;
  }
  // 列表未加载到该实体时，仍用图节点填充右侧并聚焦子图
  const switchTab = listKind.value !== "entity";
  if (switchTab) listKind.value = "entity";
  const apply = () => {
    selectedId.value = node.id;
    selectedRelId.value = "";
    isCreate.value = false;
    editing.value = true;
    form.type_code = node.type_code;
    form.name = node.name || "";
    form.description = "";
    loadEntityRelations(node.id);
    graphRef.value?.setFocus?.(node.id);
    emit("refresh-graph", node.id, 1);
  };
  if (switchTab) nextTick(apply);
  else apply();
}

function startCreateEntity() {
  const switchTab = listKind.value !== "entity";
  if (switchTab) listKind.value = "entity";
  const apply = () => {
    selectedId.value = "";
    selectedRelId.value = "";
    isCreate.value = true;
    editing.value = true;
    entityRelations.value = [];
    form.type_code = props.entityTypes[0]?.code || "";
    form.name = "";
    form.description = "";
  };
  if (switchTab) nextTick(apply);
  else apply();
}

function startCreateRelation() {
  const switchTab = listKind.value !== "relation";
  if (switchTab) listKind.value = "relation";
  const apply = () => {
    selectedRelId.value = "";
    selectedId.value = "";
    isCreate.value = true;
    editing.value = true;
    relForm.type_code = props.relationTypes[0]?.code || null;
    relForm.from_entity_id = null;
    relForm.to_entity_id = null;
  };
  if (switchTab) nextTick(apply);
  else apply();
}

async function handleSaveEntity() {
  if (!form.type_code || !form.name.trim()) {
    ui.warning("请填写类型与名称");
    return;
  }
  saving.value = true;
  try {
    if (isCreate.value) {
      const created = await createKgEntity({
        type_code: form.type_code,
        name: form.name.trim(),
        description: form.description || "",
        source_type: "manual",
      });
      ui.success("已创建");
      selectedId.value = created?.id || "";
      isCreate.value = false;
    } else {
      await updateKgEntity(selectedId.value, {
        name: form.name.trim(),
        description: form.description || "",
      });
      ui.success("已保存");
    }
    emit("refresh");
    emit("refresh-graph", selectedId.value || "__clear__");
  } catch (err) {
    if (err?.code === "ROUTE_ABORT") return;
    ui.error("保存失败: " + (err.message || ""));
  } finally {
    saving.value = false;
  }
}

function handleDeleteEntity() {
  const id = selectedId.value;
  ui.confirmDelete({
    title: "确认删除",
    content: `删除实体「${form.name}」？`,
    onPositive: async () => {
      await deleteKgEntity(id);
      ui.success("已删除");
      editing.value = false;
      selectedId.value = "";
      emit("refresh");
      await loadAllRelations();
      emit("refresh-graph", "__clear__");
    },
  });
}

async function addRelationFromEntity() {
  if (!newRel.type_code || !newRel.to_entity_id) {
    ui.warning("请选择关系类型与目标实体");
    return;
  }
  savingRel.value = true;
  try {
    await createKgRelation({
      type_code: newRel.type_code,
      from_entity_id: selectedId.value,
      to_entity_id: newRel.to_entity_id,
    });
    ui.success("关系已添加");
    newRel.type_code = null;
    newRel.to_entity_id = null;
    showAddRel.value = false;
    await Promise.all([loadEntityRelations(selectedId.value), loadAllRelations()]);
    emit("refresh-graph", selectedId.value);
  } catch (err) {
    if (err?.code === "ROUTE_ABORT") return;
    ui.error("添加失败: " + (err.message || ""));
  } finally {
    savingRel.value = false;
  }
}

async function handleSaveRelation() {
  if (!relForm.type_code || !relForm.from_entity_id || !relForm.to_entity_id) {
    ui.warning("请填写关系类型与两端实体");
    return;
  }
  if (relForm.from_entity_id === relForm.to_entity_id) {
    ui.warning("起点与终点不能相同");
    return;
  }
  savingRel.value = true;
  try {
    const created = await createKgRelation({
      type_code: relForm.type_code,
      from_entity_id: relForm.from_entity_id,
      to_entity_id: relForm.to_entity_id,
    });
    ui.success("关系已添加");
    isCreate.value = false;
    selectedRelId.value = created?.id || "";
    selectedId.value = relForm.from_entity_id;
    await loadAllRelations();
    emit("refresh-graph", relForm.from_entity_id, 1);
  } catch (err) {
    if (err?.code === "ROUTE_ABORT") return;
    ui.error("添加失败: " + (err.message || ""));
  } finally {
    savingRel.value = false;
  }
}

function handleDeleteRelation() {
  const id = selectedRelId.value;
  ui.confirmDelete({
    title: "删除关系",
    content: "确认删除该关系？",
    onPositive: async () => {
      await deleteKgRelation(id);
      ui.success("已删除");
      editing.value = false;
      selectedRelId.value = "";
      await loadAllRelations();
      emit("refresh-graph", selectedId.value || "__clear__");
    },
  });
}

function removeRelation(relationId) {
  ui.confirmDelete({
    title: "删除关系",
    content: "确认删除该关系？",
    onPositive: async () => {
      await deleteKgRelation(relationId);
      ui.success("已删除");
      await Promise.all([loadEntityRelations(selectedId.value), loadAllRelations()]);
      emit("refresh-graph", selectedId.value);
    },
  });
}

function onExtracted() {
  showExtract.value = false;
  emit("extracted");
  loadAllRelations();
}

onBeforeUnmount(() => {
  showExtract.value = false;
});

watch(
  () => props.entities,
  (rows) => {
    if (!selectedId.value || listKind.value !== "entity") return;
    const cur = rows.find((e) => e.id === selectedId.value);
    if (cur && editing.value && !isCreate.value) {
      form.name = cur.name || form.name;
      form.description = cur.description || form.description;
      form.type_code = cur.type_code || form.type_code;
    }
  }
);

onMounted(() => {
  loadAllRelations();
});

defineExpose({
  resize: () => graphRef.value?.resize?.(),
  selectEntityById(id) {
    const ent = props.entities.find((e) => e.id === id);
    if (ent) selectEntity(ent);
  },
  setTypeFilter(code) {
    listKind.value = "entity";
    filterType.value = code || null;
  },
  reloadRelations: loadAllRelations,
});
</script>

<style scoped>
.kg-workbench {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr) 320px;
  gap: 12px;
  height: 100%;
  min-height: 0;
}
.kg-workbench__left,
.kg-workbench__right {
  min-height: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--platform-border, #e5e7eb);
  border-radius: var(--platform-radius, 8px);
  background: var(--platform-bg-base, #fff);
  padding: 10px;
  overflow: hidden;
}
.kg-workbench__tabs {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.kg-workbench__tabs :deep(.n-tabs-nav) {
  flex-shrink: 0;
}
.kg-workbench__tabs :deep(.n-tabs-pane-wrapper) {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.kg-workbench__tabs :deep(.n-tab-pane) {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.kg-workbench__tabs :deep(.n-tabs-content) {
  flex: 1;
  min-height: 0;
}
.kg-workbench__pane {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 8px;
}
.kg-workbench__center {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  isolation: isolate;
}
.kg-workbench__center :deep(.kg-explore) {
  min-height: 0;
  height: 100%;
}
.kg-workbench__list {
  flex: 1;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-height: 0;
}
.kg-workbench__item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  text-align: left;
  border: 1px solid transparent;
  background: transparent;
  border-radius: 8px;
  padding: 8px;
  cursor: pointer;
  color: var(--platform-text);
}
.kg-workbench__item:hover {
  background: color-mix(in srgb, var(--platform-text) 5%, transparent);
}
.kg-workbench__item.is-active {
  border-color: color-mix(in srgb, var(--platform-primary, #3b82f6) 45%, transparent);
  background: color-mix(in srgb, var(--platform-primary, #3b82f6) 8%, transparent);
}
.kg-workbench__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.kg-workbench__item-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.kg-workbench__item-label {
  font-size: 13px;
  font-weight: 560;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.kg-workbench__item-code {
  font-size: 11px;
  color: var(--platform-text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.kg-workbench__empty,
.kg-workbench__placeholder {
  color: var(--platform-text-tertiary);
  font-size: 13px;
  padding: 16px 4px;
}
.kg-workbench__right-hd {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
}
.kg-workbench__form {
  overflow: auto;
}
.kg-workbench__rel {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 8px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--platform-text) 4%, transparent);
  font-size: 12px;
}
.kg-workbench__add-rel {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
@media (max-width: 1100px) {
  .kg-workbench {
    grid-template-columns: 200px minmax(0, 1fr);
  }
  .kg-workbench__right {
    grid-column: 1 / -1;
    max-height: 360px;
  }
}
</style>
