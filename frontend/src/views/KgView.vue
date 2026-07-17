<template>
  <div class="kg-wrapper">
    <!-- 按钮 teleport 到操作栏右侧 -->
    <Teleport to="#header-page-tools">
      <n-dropdown trigger="click" :options="syncMenuOptions" @select="handleSyncSelect">
        <n-button quaternary size="tiny" class="header-icon-btn" aria-label="同步平台数据" :loading="syncing">
          <template #icon><n-icon :size="14"><CloudDownloadOutline /></n-icon></template>
        </n-button>
      </n-dropdown>
      <n-button quaternary size="tiny" class="header-icon-btn" :aria-label="t('common.refresh')" @click="refreshAll">
        <template #icon><n-icon :size="14"><RefreshOutline /></n-icon></template>
      </n-button>
    </Teleport>

    <!-- 类型筛选提示 -->
    <n-space v-if="filterLabel" class="filter-bar" justify="center">
      <n-tag closable @close="clearFilter" type="info">
        <template #icon><n-icon><FilterOutline /></n-icon></template>
        筛选: {{ filterLabel }}
      </n-tag>
    </n-space>

    <n-tabs v-model:value="activeTab" type="line" animated>
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
          :relations="relations"
          :relation-types="relationTypes"
          :entities="entities"
          :loading="loadingRelations"
          @refresh="fetchRelations"
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
import { RefreshOutline, CloudDownloadOutline, FilterOutline } from "@vicons/ionicons5";
import KgEntityList from "../components/kg/KgEntityList.vue";
import KgRelationList from "../components/kg/KgRelationList.vue";
import KgGraphExplore from "../components/kg/KgGraphExplore.vue";
import KgExtractionPanel from "../components/kg/KgExtractionPanel.vue";
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
import { fetchOntologyEntityTypes, fetchOntologyRelationTypes } from "../api/ontology.js";

defineOptions({ name: "KgView" });

const { t } = useI18n();
const message = useMessage();
const route = useRoute();
const router = useRouter();

const activeTab = ref("entities");
const loadingEntities = ref(false);
const loadingRelations = ref(false);
const loadingGraph = ref(false);
const entities = ref([]);
const relations = ref([]);
const graphData = ref({ nodes: [], edges: [] });
const entityTypes = ref([]);
const relationTypes = ref([]);
const stats = reactive({
  entityTotal: 0,
  relationTotal: 0,
});

// 类型筛选：来自路由查询参数
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
  router.replace({ query: {} });
  refreshAll();
}

async function refreshAll() {
  await Promise.all([
    fetchMeta(),
    fetchEntityTypesData(),
    fetchRelationTypesData(),
    fetchEntities(),
    fetchRelations(),
  ]);
}

async function fetchRelationTypesData() {
  try {
    const res = await fetchOntologyRelationTypes();
    relationTypes.value = res || [];
  } catch { /* ignore */ }
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
    const fn = { org: syncKgOrg, agents: syncKgAgents, memory: syncKgMemory, all: syncKgAll, extract: extractKgDocuments }[key];
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
    // 兼容全量同步的 key 前缀
    if (data.org_departments) parts.push(`部门 ${data.org_departments}`);
    if (data.org_users) parts.push(`用户 ${data.org_users}`);
    if (data.agent_agents) parts.push(`智能体 ${data.agent_agents}`);
    if (data.agent_tools) parts.push(`工具 ${data.agent_tools}`);
    if (data.agent_skills) parts.push(`技能 ${data.agent_skills}`);
    if (data.memory_entities) parts.push(`记忆条目 ${data.memory_entities}`);
    message.success(`${syncLabels[key]}同步完成: ` + (parts.join("、") || "无变更"));
    await refreshAll();
  } catch (err) {
    if (err?.code === "ROUTE_ABORT") return;
    message.error(`${syncLabels[key]}同步失败: ` + (err.message || ""));
  } finally {
    syncing.value = false;
  }
}

async function fetchMeta() {
  try {
    const res = await fetchKgMeta();
    const data = res || {};
    stats.entityTotal = data.entity_total || 0;
    stats.relationTotal = data.relation_total || 0;
  } catch { /* ignore: kg service may be unavailable */ }
}

async function fetchEntityTypesData() {
  try {
    const res = await fetchOntologyEntityTypes();
    entityTypes.value = res || [];
  } catch { /* ignore: ontology service may be unavailable */ }
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

async function fetchRelations() {
  loadingRelations.value = true;
  try {
    const res = await fetchKgRelations({
      typeCode: filterRelationType.value || undefined,
    });
    relations.value = res || [];
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
  fetchGraph(entityId, 2);
}

function onExtracted() {
  message.success("抽取完成");
  fetchMeta();
  fetchEntities();
}

// 读取路由查询参数进行类型筛选
function applyRouteQuery() {
  const qEntityType = route.query.entityType;
  const qRelationType = route.query.relationType;
  if (qEntityType && qEntityType !== filterEntityType.value) {
    filterEntityType.value = qEntityType;
    filterRelationType.value = "";
    activeTab.value = "entities";
  } else if (qRelationType && qRelationType !== filterRelationType.value) {
    filterRelationType.value = qRelationType;
    filterEntityType.value = "";
    activeTab.value = "relations";
  } else if (!qEntityType && !qRelationType && (filterEntityType.value || filterRelationType.value)) {
    filterEntityType.value = "";
    filterRelationType.value = "";
  }
}

onMounted(async () => {
  applyRouteQuery();
  await refreshAll();

  // 自动同步：如果 KG 没有实体且没有关系，自动触发全量同步
  if (!filterEntityType.value && !filterRelationType.value
    && (stats.entityTotal === 0 && entities.value.length === 0 && relations.value.length === 0)) {
    message.info("图谱为空，正在自动同步平台数据…");
    await handleSyncSelect("all");
  }
});

watch(
  () => route.query,
  () => {
    applyRouteQuery();
    fetchEntities();
    fetchRelations();
  }
);
</script>

<style scoped>
.kg-wrapper {
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex: 1;
  height: 100%;
}
.kg-wrapper :deep(.n-tabs) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.kg-wrapper :deep(.n-tabs .n-tabs-tab-panes) {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.kg-wrapper :deep(.n-tabs .n-tab-pane) {
  height: auto;
  min-height: 100%;
}

.filter-bar {
  margin-bottom: 8px;
}
</style>
