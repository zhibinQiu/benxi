<template>
  <div class="ontology-wrapper">
    <Teleport
      v-if="headerTeleportReady && headerExtensionActive"
      to="#header-title-adjacent"
    >
      <n-radio-group
        class="ontology-header-mode"
        size="small"
        :value="activeMode"
        @update:value="onModeChange"
      >
        <n-radio-button value="ontology">
          本体模型
          <span class="ontology-header-mode__count">{{ stats.entityTypeCount }}</span>
          <span class="ontology-header-mode__count">· 关系 {{ stats.relationTypeCount }}</span>
        </n-radio-button>
        <n-radio-button value="kg">
          知识图谱
          <span class="ontology-header-mode__count">{{ stats.entityTotal }}</span>
          <span class="ontology-header-mode__count">· 关系 {{ stats.relationTotal }}</span>
        </n-radio-button>
      </n-radio-group>
    </Teleport>

    <Teleport
      v-if="headerTeleportReady && headerExtensionActive"
      to="#header-page-tools"
    >
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

    <div v-if="schemaLoadError && !loading" class="ontology-empty">
      <h2 class="ontology-empty__title">本体加载失败</h2>
      <p class="ontology-empty__desc">{{ schemaLoadError }}</p>
      <div class="ontology-empty__actions">
        <n-button quaternary size="small" class="ontology-empty__btn" @click="refreshAll">
          重试
        </n-button>
      </div>
    </div>

    <div v-else-if="showSeed && !loading" class="ontology-empty">
      <h2 class="ontology-empty__title">本体定义</h2>
      <p class="ontology-empty__desc">
        尚无语义模型。可初始化默认概念与关系类型，再同步或抽取知识图谱实例。
      </p>
      <div class="ontology-empty__actions">
        <n-button quaternary size="small" class="ontology-empty__btn" @click="refreshAll">刷新</n-button>
        <n-button quaternary size="small" class="ontology-empty__btn" @click="handleSeedDefaults">
          初始化默认本体
        </n-button>
      </div>
    </div>

    <div v-else class="ontology-body">
      <OntologyModelWorkbench
        v-if="activeMode === 'ontology'"
        ref="ontoWorkbenchRef"
        :entity-types="entityTypes"
        :relation-types="relationTypes"
        :loading="loading"
        @refresh="onOntologyRefresh"
        @explore-concept="onExploreConcept"
      />
      <KgInstanceWorkbench
        v-else
        ref="kgWorkbenchRef"
        :entities="entities"
        :entity-types="entityTypes"
        :relation-types="relationTypes"
        :graph-data="graphData"
        :loading="loadingEntities"
        :loading-graph="loadingGraph"
        @refresh="onKgRefresh"
        @refresh-graph="onRefreshGraph"
        @trace-concept="onTraceConcept"
        @extracted="onExtracted"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onActivated, watch, nextTick, h } from "vue";
import { useRoute, useRouter } from "vue-router";
import { usePlatformUi } from "../composables/usePlatformUi";
import { usePageHeaderExtension } from "../composables/usePageHeaderExtension";
import {
  RefreshOutline,
  FlashOutline,
  CloudDownloadOutline,
} from "@vicons/ionicons5";
import OntologyModelWorkbench from "../components/ontology/OntologyModelWorkbench.vue";
import KgInstanceWorkbench from "../components/kg/KgInstanceWorkbench.vue";
import {
  fetchOntologyEntityTypes,
  fetchOntologyRelationTypes,
  fetchOntologyMeta,
  seedOntologyDefaults,
} from "../api/ontology.js";
import {
  fetchKgMeta,
  fetchKgEntities,
  fetchKgGraph,
  syncKgOrg,
  syncKgAgents,
  syncKgMemory,
  syncKgAll,
  extractKgDocuments,
} from "../api/kg.js";
import { PLATFORM_JOBS_REFRESH_EVENT } from "../constants/platformEvents.js";
import { cleanupBlockingUiArtifacts } from "../utils/blockingUiCleanup.js";

defineOptions({ name: "OntologyView" });

const ONTOLOGY_TABS = new Set([
  "ontology",
  "architecture",
  "entity-types",
  "relation-types",
  "axioms",
]);
const KG_TABS = new Set(["kg", "entities", "relations", "graph", "extraction"]);

function normalizeMode(tab) {
  const t = String(tab || "");
  if (KG_TABS.has(t)) return "kg";
  if (ONTOLOGY_TABS.has(t) || t === "ontology") return "ontology";
  return "ontology";
}

const ui = usePlatformUi();
const route = useRoute();
const router = useRouter();

const activeMode = ref("ontology");
const loading = ref(false);
const loadingEntities = ref(false);
const loadingGraph = ref(false);
const schemaLoadError = ref("");
const entityTypes = ref([]);
const relationTypes = ref([]);
const entities = ref([]);
const graphData = ref({ nodes: [], edges: [] });
const stats = reactive({
  entityTypeCount: 0,
  relationTypeCount: 0,
  entityTotal: 0,
  relationTotal: 0,
});
const ontoWorkbenchRef = ref(null);
const kgWorkbenchRef = ref(null);
const syncing = ref(false);
const bootstrapped = ref(false);
const hasLoadedSchema = ref(false);
const { headerExtensionActive } = usePageHeaderExtension();
const headerTeleportReady = ref(false);

function markHeaderTeleportReady() {
  headerTeleportReady.value = !!(
    document.getElementById("header-title-adjacent") &&
    document.getElementById("header-page-tools")
  );
}

function ensureHeaderTeleportReady() {
  const tryMark = (left) => {
    markHeaderTeleportReady();
    if (!headerTeleportReady.value && left > 0) {
      requestAnimationFrame(() => tryMark(left - 1));
    }
  };
  nextTick(() => tryMark(8));
}

const showSeed = computed(
  () =>
    !schemaLoadError.value &&
    !loading.value &&
    entityTypes.value.length === 0 &&
    !hasLoadedSchema.value
);

const syncMenuOptions = [
  { label: "组织（用户/部门）", key: "org", icon: () => h("span", { style: "font-size:16px" }, "🏢") },
  { label: "智能体/工具/Skill", key: "agents", icon: () => h("span", { style: "font-size:16px" }, "🤖") },
  { label: "智能体记忆", key: "memory", icon: () => h("span", { style: "font-size:16px" }, "🧠") },
  { label: "文档内容抽取", key: "extract", icon: () => h("span", { style: "font-size:16px" }, "📄") },
  { type: "divider", key: "d1" },
  { label: "一键全量同步", key: "all", icon: () => h("span", { style: "font-size:16px" }, "🔄") },
];

const syncLabels = {
  org: "组织数据",
  agents: "智能体数据",
  memory: "记忆数据",
  extract: "文档内容",
  all: "全量数据",
};

function onModeChange(mode) {
  activeMode.value = mode;
  const q = { ...route.query, tab: mode };
  // 顶栏切换到知识图谱时拉全量列表；概念筛选仅由「查看实例」带入 entityType
  if (mode === "kg") {
    delete q.entityType;
  }
  router.replace({ query: q });
  nextTick(() => {
    // 工作台 v-if 切换可能残留 drawer 遮罩，额外清一次
    cleanupBlockingUiArtifacts({ aggressive: true });
    if (mode === "ontology") ontoWorkbenchRef.value?.resize?.();
    else {
      clearGraph();
      ensureInstanceData().then(() => {
        kgWorkbenchRef.value?.reloadRelations?.();
        kgWorkbenchRef.value?.resize?.();
      });
    }
  });
}

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
    if (data.queued || data.job_id) {
      ui.success(
        data.message ||
          `${syncLabels[key]}已加入后台任务，可在右上角「后台任务」查看进度`
      );
      window.dispatchEvent(new CustomEvent(PLATFORM_JOBS_REFRESH_EVENT));
      return;
    }
    ui.success(`${syncLabels[key]}同步完成`);
    await refreshAll();
  } catch (err) {
    if (err?.code === "ROUTE_ABORT") return;
    ui.error(`${syncLabels[key]}同步失败: ` + (err.message || ""));
  } finally {
    syncing.value = false;
  }
}

async function fetchSchemaMeta() {
  try {
    const metaRes = await fetchOntologyMeta();
    const meta = metaRes || {};
    if (typeof meta.entity_type_count === "number") {
      stats.entityTypeCount = meta.entity_type_count;
    }
    if (typeof meta.relation_type_count === "number") {
      stats.relationTypeCount = meta.relation_type_count;
    }
  } catch (err) {
    if (err?.code === "ROUTE_ABORT") return;
    throw err;
  }
}

function applyTypeCounts(entityCounts, relationCounts) {
  if (entityCounts && typeof entityCounts === "object") {
    entityTypes.value = entityTypes.value.map((et) => ({
      ...et,
      entity_count: entityCounts[et.code] ?? et.entity_count ?? 0,
    }));
  }
  if (relationCounts && typeof relationCounts === "object") {
    relationTypes.value = relationTypes.value.map((rt) => ({
      ...rt,
      relation_count: relationCounts[rt.code] ?? rt.relation_count ?? 0,
    }));
  }
}

async function fetchEntityTypes() {
  const res = await fetchOntologyEntityTypes();
  // 失败或空响应时保留旧数据，避免页面被误判为「空」
  if (!Array.isArray(res)) return;
  entityTypes.value = res;
  stats.entityTypeCount = res.length;
}

async function fetchRelationTypes() {
  const res = await fetchOntologyRelationTypes();
  if (!Array.isArray(res)) return;
  relationTypes.value = res;
  stats.relationTypeCount = res.length;
}

async function fetchEntities(typeCode = null) {
  loadingEntities.value = true;
  try {
    const res = await fetchKgEntities({
      limit: 500,
      typeCode: typeCode || undefined,
    });
    const rows = Array.isArray(res) ? res : res?.items;
    if (Array.isArray(rows)) {
      entities.value = rows;
      // meta 失败时至少用列表长度兜底，避免顶栏长期显示 0
      if (stats.entityTotal < rows.length) {
        stats.entityTotal = rows.length;
      }
    }
  } catch (err) {
    if (err?.code === "ROUTE_ABORT") return;
    ui.error("加载实体失败: " + (err.message || ""));
  } finally {
    loadingEntities.value = false;
  }
}

async function fetchGraph(focusEntityId = null, depth = 2) {
  loadingGraph.value = true;
  try {
    const res = await fetchKgGraph({
      focusEntityId: focusEntityId || undefined,
      depth,
      limit: focusEntityId ? undefined : 300,
    });
    graphData.value = res || { nodes: [], edges: [] };
  } catch (err) {
    if (err?.code === "ROUTE_ABORT") return;
    ui.error("加载图谱失败: " + (err.message || ""));
  } finally {
    loadingGraph.value = false;
  }
}

function clearGraph() {
  graphData.value = { nodes: [], edges: [] };
}

function onRefreshGraph(focusEntityId = null, depth = 2) {
  if (focusEntityId === "__clear__") {
    clearGraph();
    return;
  }
  return fetchGraph(focusEntityId || null, depth || 2);
}

/** 实例列表 + meta；默认不拉图，节约内存。
 * entityType 只做客户端筛选，避免服务端筛空后 Tab 显示 0。
 */
async function ensureInstanceData({ withGraph = false } = {}) {
  const typeCode =
    typeof route.query.entityType === "string" ? route.query.entityType : null;
  await Promise.all([fetchInstanceMeta(), fetchEntities()]);
  if (typeCode) {
    await nextTick();
    kgWorkbenchRef.value?.setTypeFilter?.(typeCode);
  } else {
    kgWorkbenchRef.value?.setTypeFilter?.(null);
  }
  if (withGraph) {
    await fetchGraph();
  }
  kgWorkbenchRef.value?.reloadRelations?.();
}

async function fetchAll() {
  loading.value = true;
  schemaLoadError.value = "";
  try {
    const results = await Promise.allSettled([
      fetchSchemaMeta(),
      fetchEntityTypes(),
      fetchRelationTypes(),
      fetchInstanceMetaRaw(),
    ]);
    const metaRes = results[3].status === "fulfilled" ? results[3].value : null;
    if (metaRes) {
      applyTypeCounts(metaRes.entity_type_counts || {}, metaRes.relation_type_counts || {});
    }
    const schemaFailed = results[0].status === "rejected"
      || results[1].status === "rejected"
      || results[2].status === "rejected";
    if (schemaFailed && entityTypes.value.length === 0) {
      const err = [results[0], results[1], results[2]].find((r) => r.status === "rejected");
      throw (err && err.status === "rejected" ? err.reason : new Error("无法加载本体定义"));
    }
    hasLoadedSchema.value = true;
    if (activeMode.value === "kg") {
      await ensureInstanceData();
    }
  } catch (err) {
    if (err?.code === "ROUTE_ABORT") return;
    if (entityTypes.value.length === 0) {
      schemaLoadError.value = err.message || "无法加载本体定义";
    }
    ui.error("加载本体数据失败: " + (err.message || ""));
  } finally {
    loading.value = false;
  }
}

/** 拉取 kg meta，更新顶栏总数并返回原始计数对象 */
async function fetchInstanceMetaRaw() {
  try {
    const res = await fetchKgMeta();
    const data = res || {};
    if (typeof data.entity_total === "number") stats.entityTotal = data.entity_total;
    if (typeof data.relation_total === "number") stats.relationTotal = data.relation_total;
    return data;
  } catch {
    return null;
  }
}

async function fetchInstanceMeta() {
  const data = await fetchInstanceMetaRaw();
  if (data) {
    applyTypeCounts(data.entity_type_counts || {}, data.relation_type_counts || {});
  }
}

function refreshAll() {
  return fetchAll().then(() => {
    nextTick(() => {
      ontoWorkbenchRef.value?.reloadViz?.();
      ontoWorkbenchRef.value?.resize?.();
      kgWorkbenchRef.value?.resize?.();
    });
  });
}

async function onOntologyRefresh() {
  await Promise.all([fetchEntityTypes(), fetchRelationTypes(), fetchSchemaMeta()]);
  await fetchInstanceMeta();
  ontoWorkbenchRef.value?.reloadViz?.();
}

async function onKgRefresh() {
  await Promise.all([fetchEntities(), fetchInstanceMeta()]);
  kgWorkbenchRef.value?.reloadRelations?.();
}

function onExtracted() {
  onKgRefresh();
  // 抽取后不自动拉全图，由用户点刷新
  onOntologyRefresh();
}

function onExploreConcept(payload) {
  activeMode.value = "kg";
  router.replace({
    query: { ...route.query, tab: "kg", entityType: payload.code },
  });
  clearGraph();
  ensureInstanceData().then(() => {
    nextTick(() => {
      kgWorkbenchRef.value?.setTypeFilter?.(payload.code);
      kgWorkbenchRef.value?.resize?.();
    });
  });
}

function onTraceConcept(payload) {
  activeMode.value = "ontology";
  router.replace({
    query: { ...route.query, tab: "ontology", entityType: payload.code },
  });
  nextTick(() => ontoWorkbenchRef.value?.resize?.());
  ui.info(`已切换到本体模型：${payload.label || payload.code || ""}`);
}

function handleSeedDefaults() {
  ui.confirmAction({
    title: "初始化默认本体",
    content: "将创建预定义实体类型与关系类型。已有定义将跳过。",
    positiveText: "确认初始化",
    negativeText: "取消",
    onPositive: async () => {
      await seedOntologyDefaults();
      ui.success("默认本体初始化完成");
      await fetchAll();
      ontoWorkbenchRef.value?.reloadViz?.();
    },
  });
}

async function autoSeedDefaults() {
  try {
    await seedOntologyDefaults();
    ui.success("默认本体初始化完成");
    await fetchAll();
  } catch (err) {
    ui.warning("自动初始化默认本体失败: " + (err.message || ""));
  }
}

function applyRouteQuery() {
  activeMode.value = normalizeMode(route.query.tab);
}

async function bootstrap() {
  applyRouteQuery();
  await fetchAll();
  if (!schemaLoadError.value) {
    // 概念或关系类型缺失时补种默认 TBox（已有项会跳过）
    if (entityTypes.value.length === 0 || relationTypes.value.length === 0) {
      ui.info(
        entityTypes.value.length === 0
          ? "本体定义为空，正在初始化默认本体…"
          : "关系类型为空，正在补种默认关系…"
      );
      await autoSeedDefaults();
    }
  }
  bootstrapped.value = true;
  await nextTick();
  ontoWorkbenchRef.value?.resize?.();
  if (activeMode.value === "kg") kgWorkbenchRef.value?.resize?.();
}

onMounted(() => {
  ensureHeaderTeleportReady();
  bootstrap();
});

onActivated(async () => {
  // 从知识页等切回时，顶栏节点可能同帧才重建，需等 DOM 就绪再 Teleport
  headerTeleportReady.value = false;
  ensureHeaderTeleportReady();
  applyRouteQuery();
  if (!bootstrapped.value) return;
  // 返回本页：只做软刷新；失败不覆盖已有列表，避免「数据被清空」
  try {
    if (activeMode.value === "ontology") {
      await Promise.allSettled([
        fetchEntityTypes(),
        fetchRelationTypes(),
        fetchSchemaMeta(),
      ]);
      ontoWorkbenchRef.value?.reloadViz?.();
    } else {
      await ensureInstanceData();
    }
  } catch {
    /* ignore soft refresh errors */
  }
  await nextTick();
  requestAnimationFrame(() => {
    ontoWorkbenchRef.value?.resize?.();
    kgWorkbenchRef.value?.resize?.();
  });
});

watch(
  () => route.query.tab,
  (tab) => {
    const mode = normalizeMode(tab);
    if (mode !== activeMode.value) {
      activeMode.value = mode;
      if (mode === "kg") {
        clearGraph();
        ensureInstanceData();
      }
      nextTick(() => {
        ontoWorkbenchRef.value?.resize?.();
        kgWorkbenchRef.value?.resize?.();
      });
    }
  }
);

watch(
  () => route.query.entityType,
  (code) => {
    if (activeMode.value === "kg" && typeof code === "string") {
      nextTick(() => kgWorkbenchRef.value?.setTypeFilter?.(code));
    }
  }
);
</script>

<style scoped>
.ontology-wrapper {
  padding: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex: 1;
  height: 100%;
  overflow: hidden;
}
.ontology-body {
  flex: 1;
  min-height: 0;
  padding: 12px 16px 16px;
  box-sizing: border-box;
}
.ontology-body > * {
  height: 100%;
}
.ontology-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  gap: 12px;
  padding: 40px 20px;
}
.ontology-empty__title {
  margin: 0;
  font-size: 20px;
  font-weight: 650;
}
.ontology-empty__desc {
  margin: 0;
  max-width: 480px;
  color: var(--platform-text-tertiary);
  line-height: 1.6;
  font-size: 14px;
}
.ontology-empty__actions {
  display: flex;
  gap: 8px;
}
.ontology-empty__btn {
  border: 1px solid var(--platform-border, #e5e7eb);
}
</style>

<style>
/* Teleport 到顶栏中部的模式切换 */
.ontology-header-mode {
  white-space: nowrap;
}
.ontology-header-mode .n-radio-button {
  --n-button-border-radius: 8px;
}
.ontology-header-mode__count {
  margin-left: 4px;
  font-size: 11px;
  opacity: 0.55;
  font-weight: 500;
}
</style>
