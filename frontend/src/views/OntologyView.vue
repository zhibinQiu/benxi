<template>
  <div class="ontology-wrapper">
    <Teleport to="#header-page-tools">
      <n-dropdown trigger="click" :options="syncMenuOptions" @select="handleSyncSelect">
        <n-button quaternary size="tiny" class="header-icon-btn" aria-label="同步平台数据" :loading="syncing">
          <template #icon><n-icon :size="14"><CloudDownloadOutline /></n-icon></template>
        </n-button>
      </n-dropdown>
      <n-button quaternary size="tiny" class="header-icon-btn" aria-label="初始化默认本体" @click="handleSeedDefaults">
        <template #icon><n-icon :size="14"><FlashOutline /></n-icon></template>
      </n-button>
      <n-button quaternary size="tiny" class="header-icon-btn" aria-label="刷新" @click="refreshAll">
        <template #icon><n-icon :size="14"><RefreshOutline /></n-icon></template>
      </n-button>
    </Teleport>

    <div v-if="showSeed && !loading" class="ontology-empty">
      <div class="ontology-empty__icon">
        <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" width="48" height="48">
          <circle cx="16" cy="16" r="6" />
          <circle cx="36" cy="14" r="5" />
          <circle cx="30" cy="36" r="5" />
          <line x1="21" y1="14" x2="31" y2="14" />
          <line x1="18" y1="19" x2="27" y2="33" />
          <line x1="34" y1="19" x2="32" y2="32" />
        </svg>
      </div>
      <h2 class="ontology-empty__title">本体定义</h2>
      <p class="ontology-empty__desc">
        本体定义包含模式层（实体类型、关系类型、公理）与实例层（图谱实体、关系与探索）。
        可先初始化默认本体，再同步平台组织/智能体，或从文档抽取实例。
      </p>
      <div class="ontology-empty__actions">
        <n-button quaternary size="small" class="ontology-empty__btn" @click="refreshAll">
          <template #icon><n-icon :size="14"><RefreshOutline /></n-icon></template>
          刷新
        </n-button>
        <n-button quaternary size="small" class="ontology-empty__btn" @click="handleSeedDefaults">
          <template #icon><n-icon :size="14"><FlashOutline /></n-icon></template>
          初始化默认本体
        </n-button>
      </div>
    </div>

    <n-space v-if="filterLabel" class="filter-bar" justify="center">
      <n-tag closable type="info" @close="clearFilter">
        <template #icon><n-icon><FilterOutline /></n-icon></template>
        筛选: {{ filterLabel }}
      </n-tag>
    </n-space>

    <n-tabs
      v-show="!showSeed || loading"
      v-model:value="activeTab"
      type="line"
      animated
      @update:value="onTabChange"
    >
      <n-tab-pane name="architecture" tab="本体感知架构">
        <OntologyGraphMap
          :entity-types="entityTypes"
          :relation-types="relationTypes"
          :axioms="axioms"
          :loading="loading"
          @navigate="(tab) => activeTab = tab"
        />
      </n-tab-pane>
      <n-tab-pane name="entity-types" :tab="`实体类型 (${stats.entityTypeCount})`">
        <EntityTypesPanel
          ref="entityTypesRef"
          :entity-types="entityTypes"
          :loading="loading"
          @refresh="fetchEntityTypes"
        />
      </n-tab-pane>
      <n-tab-pane name="relation-types" :tab="`关系类型 (${stats.relationTypeCount})`">
        <RelationTypesPanel
          ref="relationTypesRef"
          :relation-types="relationTypes"
          :loading="loading"
          @refresh="fetchRelationTypes"
        />
      </n-tab-pane>
      <n-tab-pane name="axioms" :tab="`公理规则 (${stats.axiomCount})`">
        <AxiomsPanel
          ref="axiomsRef"
          :axioms="axioms"
          :loading="loading"
          @refresh="fetchAxioms"
        />
      </n-tab-pane>
      <n-tab-pane name="entities" :tab="`实体 (${stats.entityTotal})`">
        <KgEntityList
          ref="entityListRef"
          :entities="entities"
          :entity-types="entityTypes"
          :loading="loadingEntities"
          @refresh="fetchEntities"
        />
      </n-tab-pane>
      <n-tab-pane name="relations" :tab="`关系 (${stats.relationTotal})`">
        <KgRelationList
          ref="relationListRef"
          :relations="instanceRelations"
          :relation-types="relationTypes"
          :entities="entities"
          :loading="loadingRelations"
          @refresh="fetchInstanceRelations"
        />
      </n-tab-pane>
      <n-tab-pane name="graph" tab="图谱探索">
        <KgGraphExplore
          ref="graphExploreRef"
          :graph-data="graphData"
          :loading="loadingGraph"
          @refresh="fetchGraph"
          @focus-entity="onFocusEntity"
        />
      </n-tab-pane>
      <n-tab-pane name="extraction" tab="LLM 抽取">
        <KgExtractionPanel
          ref="extractionPanelRef"
          :entity-types="entityTypes"
          @extracted="onExtracted"
        />
      </n-tab-pane>
    </n-tabs>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed, h, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "../composables/useI18n";
import { useMessage } from "naive-ui";
import { usePlatformUi } from "../composables/usePlatformUi";
import {
  RefreshOutline,
  FlashOutline,
  CloudDownloadOutline,
  FilterOutline,
} from "@vicons/ionicons5";
import EntityTypesPanel from "../components/ontology/EntityTypesPanel.vue";
import RelationTypesPanel from "../components/ontology/RelationTypesPanel.vue";
import AxiomsPanel from "../components/ontology/AxiomsPanel.vue";
import OntologyGraphMap from "../components/ontology/OntologyGraphMap.vue";
import KgEntityList from "../components/kg/KgEntityList.vue";
import KgRelationList from "../components/kg/KgRelationList.vue";
import KgGraphExplore from "../components/kg/KgGraphExplore.vue";
import KgExtractionPanel from "../components/kg/KgExtractionPanel.vue";
import {
  fetchOntologyEntityTypes,
  fetchOntologyRelationTypes,
  fetchOntologyAxioms,
  fetchOntologyMeta,
  seedOntologyDefaults,
} from "../api/ontology.js";
import {
  fetchKgMeta,
  fetchKgEntities,
  fetchKgRelations,
  fetchKgGraph,
  syncKgOrg,
  syncKgAgents,
  syncKgMemory,
  syncKgAll,
  extractKgDocuments,
} from "../api/kg.js";

defineOptions({ name: "OntologyView" });

const VALID_TABS = new Set([
  "architecture",
  "entity-types",
  "relation-types",
  "axioms",
  "entities",
  "relations",
  "graph",
  "extraction",
]);

const { t } = useI18n();
const message = useMessage();
const ui = usePlatformUi();
const route = useRoute();
const router = useRouter();

const activeTab = ref("architecture");
const loading = ref(false);
const loadingEntities = ref(false);
const loadingRelations = ref(false);
const loadingGraph = ref(false);
const entityTypes = ref([]);
const relationTypes = ref([]);
const axioms = ref([]);
const entities = ref([]);
const instanceRelations = ref([]);
const graphData = ref({ nodes: [], edges: [] });
const stats = reactive({
  entityTypeCount: 0,
  relationTypeCount: 0,
  axiomCount: 0,
  entityTotal: 0,
  relationTotal: 0,
});
const showSeed = computed(() => entityTypes.value.length === 0);

const entityTypesRef = ref(null);
const relationTypesRef = ref(null);
const axiomsRef = ref(null);
const entityListRef = ref(null);
const relationListRef = ref(null);
const graphExploreRef = ref(null);
const extractionPanelRef = ref(null);

const filterEntityType = ref("");
const filterRelationType = ref("");

const filterLabel = computed(() => {
  if (filterEntityType.value) {
    const et = entityTypes.value.find((e) => e.code === filterEntityType.value);
    return `实体类型: ${et?.label || filterEntityType.value}`;
  }
  if (filterRelationType.value) {
    const rt = relationTypes.value.find((r) => r.code === filterRelationType.value);
    return `关系类型: ${rt?.label || filterRelationType.value}`;
  }
  return "";
});

function clearFilter() {
  filterEntityType.value = "";
  filterRelationType.value = "";
  const q = { ...route.query };
  delete q.entityType;
  delete q.relationType;
  router.replace({ query: q });
  fetchEntities();
  fetchInstanceRelations();
}

function onTabChange(tab) {
  const q = { ...route.query, tab };
  router.replace({ query: q });
  if (tab === "entities" || tab === "relations" || tab === "graph") {
    ensureInstanceData();
  }
}

const syncing = ref(false);

const syncMenuOptions = [
  {
    label: "组织（用户/部门）",
    key: "org",
    icon: () => h("span", { style: "font-size:16px" }, "🏢"),
  },
  {
    label: "智能体/工具/Skill",
    key: "agents",
    icon: () => h("span", { style: "font-size:16px" }, "🤖"),
  },
  {
    label: "智能体记忆",
    key: "memory",
    icon: () => h("span", { style: "font-size:16px" }, "🧠"),
  },
  {
    label: "文档内容抽取",
    key: "extract",
    icon: () => h("span", { style: "font-size:16px" }, "📄"),
  },
  { type: "divider", key: "d1" },
  {
    label: "一键全量同步",
    key: "all",
    icon: () => h("span", { style: "font-size:16px" }, "🔄"),
  },
];

const syncLabels = {
  org: "组织数据",
  agents: "智能体数据",
  memory: "记忆数据",
  extract: "文档内容",
  all: "全量数据",
};

async function handleSyncSelect(key) {
  if (syncing.value) return;
  syncing.value = true;
  try {
    const fn = {
      org: syncKgOrg,
      agents: syncKgAgents,
      memory: syncKgMemory,
      all: syncKgAll,
      extract: extractKgDocuments,
    }[key];
    if (!fn) return;
    const res = await fn();
    const data = res || {};
    const parts = [];
    if (data.departments) parts.push(`部门 ${data.departments}`);
    if (data.users) parts.push(`用户 ${data.users}`);
    if (data.agents) parts.push(`智能体 ${data.agents}`);
    if (data.tools) parts.push(`工具 ${data.tools}`);
    if (data.skills) parts.push(`技能 ${data.skills}`);
    if (data.relations) parts.push(`关系 ${data.relations}`);
    if (data.entities) parts.push(`实体 ${data.entities}`);
    if (data.entities_created) parts.push(`新增实体 ${data.entities_created}`);
    if (data.relations_created) parts.push(`新增关系 ${data.relations_created}`);
    if (data.processed) parts.push(`处理文档 ${data.processed}`);
    if (data.org_departments) parts.push(`部门 ${data.org_departments}`);
    if (data.org_users) parts.push(`用户 ${data.org_users}`);
    if (data.agent_agents) parts.push(`智能体 ${data.agent_agents}`);
    if (data.agent_tools) parts.push(`工具 ${data.agent_tools}`);
    if (data.agent_skills) parts.push(`技能 ${data.agent_skills}`);
    if (data.memory_entities) parts.push(`记忆条目 ${data.memory_entities}`);
    if (data.deleted) parts.push(`清除 ${data.deleted}`);
    if (data.org_deleted) parts.push(`清除组织 ${data.org_deleted}`);
    if (data.agent_deleted) parts.push(`清除智能体 ${data.agent_deleted}`);
    if (data.memory_deleted) parts.push(`清除记忆 ${data.memory_deleted}`);
    message.success(`${syncLabels[key]}同步完成: ` + (parts.join("、") || "无变更"));
    await refreshAll();
  } catch (err) {
    if (err?.code === "ROUTE_ABORT") return;
    message.error(`${syncLabels[key]}同步失败: ` + (err.message || ""));
  } finally {
    syncing.value = false;
  }
}

async function fetchSchemaMeta() {
  try {
    const metaRes = await fetchOntologyMeta();
    const meta = metaRes || {};
    stats.entityTypeCount = meta.entity_type_count || 0;
    stats.relationTypeCount = meta.relation_type_count || 0;
    stats.axiomCount = meta.axiom_count || 0;
  } catch {
    /* ignore */
  }
}

async function fetchInstanceMeta() {
  try {
    const res = await fetchKgMeta();
    const data = res || {};
    stats.entityTotal = data.entity_total || 0;
    stats.relationTotal = data.relation_total || 0;
  } catch {
    /* ignore */
  }
}

async function fetchEntityTypes() {
  try {
    const res = await fetchOntologyEntityTypes();
    entityTypes.value = res || [];
  } catch {
    /* ignore */
  }
}

async function fetchRelationTypes() {
  try {
    const res = await fetchOntologyRelationTypes();
    relationTypes.value = res || [];
  } catch {
    /* ignore */
  }
}

async function fetchAxioms() {
  try {
    const res = await fetchOntologyAxioms();
    axioms.value = res || [];
  } catch {
    /* ignore */
  }
}

async function fetchEntities() {
  loadingEntities.value = true;
  try {
    const res = await fetchKgEntities({
      limit: 200,
      typeCode: filterEntityType.value || undefined,
    });
    entities.value = res || [];
  } catch (err) {
    if (err?.code === "ROUTE_ABORT") return;
    message.error("加载实体失败: " + (err.message || ""));
  } finally {
    loadingEntities.value = false;
  }
}

async function fetchInstanceRelations() {
  loadingRelations.value = true;
  try {
    const res = await fetchKgRelations({
      typeCode: filterRelationType.value || undefined,
    });
    instanceRelations.value = res || [];
  } catch (err) {
    if (err?.code === "ROUTE_ABORT") return;
    message.error("加载关系失败: " + (err.message || ""));
  } finally {
    loadingRelations.value = false;
  }
}

async function fetchGraph(focusEntityId = null, depth = 2) {
  loadingGraph.value = true;
  try {
    const res = await fetchKgGraph({ focusEntityId, depth });
    graphData.value = res || { nodes: [], edges: [] };
  } catch (err) {
    if (err?.code === "ROUTE_ABORT") return;
    message.error("加载图谱失败: " + (err.message || ""));
  } finally {
    loadingGraph.value = false;
  }
}

function onFocusEntity(entityId) {
  activeTab.value = "graph";
  onTabChange("graph");
  fetchGraph(entityId, 2);
}

function onExtracted() {
  message.success("抽取完成");
  fetchInstanceMeta();
  fetchEntities();
}

async function ensureInstanceData() {
  await Promise.all([fetchInstanceMeta(), fetchEntities(), fetchInstanceRelations()]);
}

async function fetchAll() {
  loading.value = true;
  try {
    await fetchSchemaMeta();
    await Promise.all([fetchEntityTypes(), fetchRelationTypes(), fetchAxioms()]);
    await ensureInstanceData();
  } catch (err) {
    if (err?.code === "ROUTE_ABORT") return;
    message.error("加载本体数据失败: " + (err.message || ""));
  } finally {
    loading.value = false;
  }
}

function refreshAll() {
  fetchAll();
}

function handleSeedDefaults() {
  ui.confirmAction({
    title: "初始化默认本体",
    content:
      "将创建预定义的实体类型（组织、人员、文档等）和关系类型（包含、任职、约束等）。已有定义将跳过。",
    positiveText: "确认初始化",
    negativeText: "取消",
    onPositive: async () => {
      try {
        await seedOntologyDefaults();
        message.success("默认本体初始化完成");
        await fetchAll();
      } catch (err) {
        message.error("初始化失败: " + (err.message || ""));
      }
    },
  });
}

async function autoSeedDefaults() {
  try {
    await seedOntologyDefaults();
    message.success("默认本体初始化完成");
    await fetchAll();
  } catch (err) {
    message.warning("自动初始化默认本体失败: " + (err.message || ""));
  }
}

function applyRouteQuery() {
  const tab = String(route.query.tab || "");
  if (tab && VALID_TABS.has(tab)) {
    activeTab.value = tab;
  }
  const qFocus = route.query.focusEntityId;
  if (qFocus) {
    activeTab.value = "graph";
  }
  const qEntityType = route.query.entityType;
  const qRelationType = route.query.relationType;
  if (qEntityType && qEntityType !== filterEntityType.value) {
    filterEntityType.value = String(qEntityType);
    filterRelationType.value = "";
    activeTab.value = "entities";
  } else if (qRelationType && qRelationType !== filterRelationType.value) {
    filterRelationType.value = String(qRelationType);
    filterEntityType.value = "";
    activeTab.value = "relations";
  } else if (
    !qEntityType &&
    !qRelationType &&
    (filterEntityType.value || filterRelationType.value)
  ) {
    filterEntityType.value = "";
    filterRelationType.value = "";
  }
}

onMounted(async () => {
  applyRouteQuery();
  await fetchAll();

  if (entityTypes.value.length === 0 && !loading.value) {
    message.info("本体定义为空，正在初始化默认本体…");
    await autoSeedDefaults();
  }

  const focusId = route.query.focusEntityId
    ? String(route.query.focusEntityId)
    : "";
  if (focusId) {
    await fetchGraph(focusId);
  }

  if (
    !filterEntityType.value &&
    !filterRelationType.value &&
    !focusId &&
    stats.entityTotal === 0 &&
    entities.value.length === 0 &&
    instanceRelations.value.length === 0
  ) {
    message.info("图谱实例为空，正在自动同步平台数据…");
    await handleSyncSelect("all");
  }
});

watch(
  () => route.query,
  () => {
    applyRouteQuery();
    if (["entities", "relations", "graph", "extraction"].includes(activeTab.value)) {
      fetchEntities();
      fetchInstanceRelations();
    }
  }
);
</script>

<style scoped>
.ontology-wrapper {
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex: 1;
  height: 100%;
  overflow: hidden;
}
.ontology-wrapper :deep(.n-tabs) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.ontology-wrapper :deep(.n-tabs-nav) {
  background: var(--platform-bg);
}
.ontology-wrapper :deep(.n-tabs-tab--active) {
  color: var(--n-tab-text-color) !important;
}
.ontology-wrapper :deep(.n-tabs-tab):hover {
  color: var(--n-tab-text-color) !important;
}
.ontology-wrapper :deep(.n-tabs-bar) {
  display: none;
}
.ontology-wrapper :deep(.n-tabs .n-tabs-tab-panes) {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding-bottom: 4px;
}
.ontology-wrapper :deep(.n-tabs .n-tab-pane) {
  height: 100%;
  min-height: 0;
  overflow: visible;
}

.filter-bar {
  margin-bottom: 8px;
}

.ontology-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  gap: 16px;
  padding: 40px 24px;
}
.ontology-empty__icon {
  color: var(--platform-text-quaternary);
  opacity: 0.6;
}
.ontology-empty__title {
  margin: 0;
  font-size: var(--platform-font-size-lg);
  font-weight: var(--platform-font-weight-strong);
  color: var(--platform-text);
  letter-spacing: -0.01em;
}
.ontology-empty__desc {
  margin: 0;
  max-width: 420px;
  font-size: var(--platform-font-size-sm);
  line-height: 1.6;
  color: var(--platform-text-tertiary);
}
.ontology-empty__actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 8px;
}
</style>
