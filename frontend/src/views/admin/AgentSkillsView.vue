<script setup>
import { computed, defineAsyncComponent, nextTick, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { SearchOutline, RefreshOutline, DownloadOutline } from "@vicons/ionicons5";
import IconAction from "../../components/IconAction.vue";
import FeatureSubsystemShell from "../../components/FeatureSubsystemShell.vue";
import { resolveAgentSkillsTab } from "../../constants/agentSkillsTabs.js";
import { useI18n } from "../../composables/useI18n";
import { readPanelLoading } from "../../utils/panelExpose.js";
import { writeRoutingCatalogCache } from "../../utils/agentSkillsRoutingCatalogCache.js";

const AgentsTabPanel = defineAsyncComponent(
  () => import("../../components/aip/AgentsTabPanel.vue")
);
const SkillsTabPanel = defineAsyncComponent(
  () => import("../../components/aip/SkillsTabPanel.vue")
);
const ToolsTabPanel = defineAsyncComponent(
  () => import("../../components/aip/ToolsTabPanel.vue")
);
const MemoryTabPanel = defineAsyncComponent(
  () => import("../../components/aip/MemoryTabPanel.vue")
);
const StyleTabPanel = defineAsyncComponent(
  () => import("../../components/aip/StyleTabPanel.vue")
);
const AipKeysPanel = defineAsyncComponent(
  () => import("../../components/aip/AipKeysPanel.vue")
);
const RoutingCatalogDrawer = defineAsyncComponent(
  () => import("../../components/aip/RoutingCatalogDrawer.vue")
);

const { t } = useI18n();
const route = useRoute();

const activeTab = ref(resolveAgentSkillsTab(route.query.tab));
const mountedTabs = reactive({ [activeTab.value]: true });
let prevTab = activeTab.value;

const agentsPanelRef = ref(null);
const skillsPanelRef = ref(null);
const toolsPanelRef = ref(null);
const memoryPanelRef = ref(null);
const stylePanelRef = ref(null);
const aipKeysPanelRef = ref(null);
const routingCatalogRef = ref(null);
const routingCatalogReady = ref(false);

const panelRefByTab = {
  agents: agentsPanelRef,
  skills: skillsPanelRef,
  tools: toolsPanelRef,
  memory: memoryPanelRef,
  styles: stylePanelRef,
  "aip-keys": aipKeysPanelRef,
};

const refreshing = computed(() =>
  readPanelLoading(panelRefByTab[activeTab.value]?.value)
);

const routingCatalogLoading = computed(() =>
  routingCatalogReady.value ? readPanelLoading(routingCatalogRef.value) : false
);
const routingCatalogType = computed(() =>
  routingCatalogReady.value ? routingCatalogRef.value?.catalogType?.value ?? "" : ""
);

const SEARCHABLE_TABS = new Set(["agents", "skills", "tools"]);
const searchOpen = reactive({});

function toggleSearchForTab(tabKey) {
  searchOpen[tabKey] = !searchOpen[tabKey];
  const panel = panelRefByTab[tabKey]?.value;
  panel?.toggleSearch?.();
}

function onTabClick(key) {
  if (key === prevTab) return;
  // 切换 tab 前关闭旧 panel 的搜索
  if (searchOpen[prevTab]) {
    const oldPanel = panelRefByTab[prevTab]?.value;
    oldPanel?.toggleSearch?.();
    searchOpen[prevTab] = false;
  }
  activeTab.value = key;
  mountedTabs[key] = true;
  prevTab = key;
}

watch(
  () => route.query.tab,
  (tab) => {
    const resolved = resolveAgentSkillsTab(tab);
    if (resolved !== activeTab.value) {
      if (searchOpen[activeTab.value]) {
        const oldPanel = panelRefByTab[activeTab.value]?.value;
        oldPanel?.toggleSearch?.();
        searchOpen[activeTab.value] = false;
      }
      activeTab.value = resolved;
      mountedTabs[resolved] = true;
      prevTab = resolved;
    }
  }
);

async function refreshActiveTab() {
  const panel = panelRefByTab[activeTab.value]?.value;
  if (activeTab.value === "agents") {
    await panel?.reload?.({ foreground: true });
    await routingCatalogRef.value?.refreshIfOpen?.();
    return;
  }
  if (activeTab.value === "skills") {
    await panel?.reload?.({ foreground: true });
    await routingCatalogRef.value?.refreshIfOpen?.();
    return;
  }
  await panel?.load?.({ foreground: true });
}

async function openRoutingCatalog(filename) {
  routingCatalogReady.value = true;
  await nextTick();
  await routingCatalogRef.value?.openCatalog?.(filename);
}

function connectExternalAgent() {
  agentsPanelRef.value?.openExternalAgentModal?.();
}

async function onRegistryChanged() {
  writeRoutingCatalogCache("skills.md", "");
  await routingCatalogRef.value?.refreshIfOpen?.();
}
</script>

<template>
  <FeatureSubsystemShell :show-intro="false">
    <div class="agent-skills-view">
      <n-tabs v-model:value="activeTab" type="line" animated @update:value="onTabClick">
        <!-- ── agents tab ── -->
        <n-tab-pane name="agents" :tab="t('admin.agentSkills.tabAgents')">
          <div class="agents-tab-header-inline">
            <div class="agents-tab-actions">
              <IconAction
                :label="t('common.refresh')"
                :icon="RefreshOutline"
                :loading="refreshing"
                @click="refreshActiveTab"
              />
              <IconAction
                :label="t('admin.agentSkills.connectExternalAgent')"
                :icon="DownloadOutline"
                @click="connectExternalAgent"
              />
              <IconAction
                :label="t('common.search')"
                :icon="SearchOutline"
                :active="searchOpen.agents"
                @click="toggleSearchForTab('agents')"
              />
            </div>
            <n-button
              quaternary
              size="small"
              class="agent-skills-inline-btn"
              :loading="routingCatalogLoading && routingCatalogType === 'agents.md'"
              @click="openRoutingCatalog('agents.md')"
            >
              agents.md
            </n-button>
          </div>
          <AgentsTabPanel
            v-if="mountedTabs.agents"
            ref="agentsPanelRef"
            @registry-changed="onRegistryChanged"
          />
        </n-tab-pane>

        <!-- ── skills tab ── -->
        <n-tab-pane name="skills" :tab="t('admin.agentSkills.tabSkills')">
          <SkillsTabPanel
            v-if="mountedTabs.skills"
            ref="skillsPanelRef"
            :refreshing="refreshing"
            :on-refresh="refreshActiveTab"
            :on-connect-mcp="() => skillsPanelRef?.openMcpSkillModal?.()"
            @registry-changed="onRegistryChanged"
          />
        </n-tab-pane>

        <!-- ── tools tab ── -->
        <n-tab-pane name="tools" :tab="t('admin.agentSkills.tabTools')">
          <ToolsTabPanel
            v-if="mountedTabs.tools"
            ref="toolsPanelRef"
            :refreshing="refreshing"
            :on-refresh="refreshActiveTab"
          />
        </n-tab-pane>

        <!-- ── styles tab ── -->
        <n-tab-pane name="styles" :tab="t('admin.agentSkills.tabStyles')">
          <StyleTabPanel
            v-if="mountedTabs.styles"
            ref="stylePanelRef"
          />
        </n-tab-pane>

        <!-- ── memory tab ── -->
        <n-tab-pane name="memory" :tab="t('admin.agentSkills.tabMemory')">
          <MemoryTabPanel
            v-if="mountedTabs.memory"
            ref="memoryPanelRef"
          />
        </n-tab-pane>

        <!-- ── aip-keys tab ── -->
        <n-tab-pane name="aip-keys" :tab="t('admin.agentSkills.tabAipKeys')">
          <AipKeysPanel
            v-if="mountedTabs['aip-keys']"
            ref="aipKeysPanelRef"
            :refreshing="refreshing"
            :on-refresh="refreshActiveTab"
          />
        </n-tab-pane>
      </n-tabs>

      <RoutingCatalogDrawer v-if="routingCatalogReady" ref="routingCatalogRef" />
    </div>
  </FeatureSubsystemShell>
</template>

<style scoped>
.agent-skills-view {
  padding: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex: 1;
  height: 100%;
}
.agent-skills-view :deep(.n-tabs) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.agent-skills-view :deep(.n-tabs .n-tabs-tab-panes) {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.agent-skills-view :deep(.n-tab-pane) {
  height: auto;
  min-height: 100%;
}

.agents-tab-header-inline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
  flex-shrink: 0;
}

.agents-tab-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.agent-skills-inline-btn {
  width: auto !important;
  padding: 0 8px !important;
  border-radius: 4px !important;
}
</style>

<style>
/* 共享样式（非 scoped） */
@import "../../styles/agent-skills.css";
</style>
