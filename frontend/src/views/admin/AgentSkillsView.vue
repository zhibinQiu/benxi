<script setup>
import { computed, defineAsyncComponent, nextTick, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { NTabPane, NTabs } from "naive-ui";
import FeatureSubsystemShell from "../../components/FeatureSubsystemShell.vue";
import AgentSkillsToolbar from "../../components/aip/AgentSkillsToolbar.vue";
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

watch(activeTab, (tab) => {
  mountedTabs[tab] = true;
});

watch(
  () => route.query.tab,
  (tab) => {
    activeTab.value = resolveAgentSkillsTab(tab);
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

function createAipKey() {
  aipKeysPanelRef.value?.openCreate?.();
}

async function onRegistryChanged() {
  writeRoutingCatalogCache("skills.md", "");
  await routingCatalogRef.value?.refreshIfOpen?.();
}
</script>

<template>
  <FeatureSubsystemShell :show-intro="false">
    <template #extra>
      <AgentSkillsToolbar
        :active-tab="activeTab"
        :refreshing="refreshing"
        :routing-catalog-loading="routingCatalogLoading"
        :routing-catalog-type="routingCatalogType"
        @refresh="refreshActiveTab"
        @open-routing-catalog="openRoutingCatalog"
        @connect-external-agent="connectExternalAgent"
        @create-aip-key="createAipKey"
      />
    </template>

    <div class="agent-skills-view">
      <NTabs v-model:value="activeTab" type="line" class="agent-skills-tabs" :tabs-padding="0">
        <NTabPane name="agents" :tab="t('admin.agentSkills.tabAgents')">
          <AgentsTabPanel
            v-if="mountedTabs.agents"
            v-show="activeTab === 'agents'"
            ref="agentsPanelRef"
            @registry-changed="onRegistryChanged"
          />
        </NTabPane>

        <NTabPane name="skills" :tab="t('admin.agentSkills.tabSkills')">
          <SkillsTabPanel
            v-if="mountedTabs.skills"
            v-show="activeTab === 'skills'"
            ref="skillsPanelRef"
            @registry-changed="onRegistryChanged"
          />
        </NTabPane>

        <NTabPane name="tools" :tab="t('admin.agentSkills.tabTools')">
          <ToolsTabPanel
            v-if="mountedTabs.tools"
            v-show="activeTab === 'tools'"
            ref="toolsPanelRef"
          />
        </NTabPane>

        <NTabPane name="styles" :tab="t('admin.agentSkills.tabStyles')">
          <StyleTabPanel
            v-if="mountedTabs.styles"
            v-show="activeTab === 'styles'"
            ref="stylePanelRef"
          />
        </NTabPane>

        <NTabPane name="memory" :tab="t('admin.agentSkills.tabMemory')">
          <MemoryTabPanel
            v-if="mountedTabs.memory"
            v-show="activeTab === 'memory'"
            ref="memoryPanelRef"
          />
        </NTabPane>

        <NTabPane name="aip-keys" :tab="t('admin.agentSkills.tabAipKeys')">
          <AipKeysPanel
            v-if="mountedTabs['aip-keys']"
            v-show="activeTab === 'aip-keys'"
            ref="aipKeysPanelRef"
          />
        </NTabPane>
      </NTabs>

      <RoutingCatalogDrawer v-if="routingCatalogReady" ref="routingCatalogRef" />
    </div>
  </FeatureSubsystemShell>
</template>

<style scoped>
.agent-skills-view {
  max-width: 1440px;
}

/* ── Tabs ── */
.agent-skills-tabs {
  margin-top: 18px;
}

.agent-skills-tabs :deep(.n-tabs-tab),
.agent-skills-tabs :deep(.n-tabs-tab .n-tabs-tab__label) {
  font-size: var(--platform-font-size-sm) !important;
}

.agent-skills-tabs :deep(.n-tabs-nav) {
  padding-bottom: 2px;
}

.agent-skills-tabs :deep(.n-tabs-tab) {
  padding: 8px 0 12px;
  margin-right: 24px;
  transition: color 0.18s ease;
}
</style>

<style>
/* 共享样式：AgentsTabPanel / SkillsTabPanel / AgentSkillsToolbar 等子组件依赖 */
@import "../../styles/agent-skills.css";
</style>
