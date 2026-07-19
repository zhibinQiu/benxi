<script setup>
import { computed, defineAsyncComponent, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { SearchOutline, RefreshOutline, DownloadOutline } from "@vicons/ionicons5";
import IconAction from "../../components/IconAction.vue";
import FeatureSubsystemShell from "../../components/FeatureSubsystemShell.vue";
import { resolveAgentSkillsTab } from "../../constants/agentSkillsTabs.js";
import { useI18n } from "../../composables/useI18n";
import { readPanelLoading } from "../../utils/panelExpose.js";

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
const AipKeysPanel = defineAsyncComponent(
  () => import("../../components/aip/AipKeysPanel.vue")
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
const aipKeysPanelRef = ref(null);

const panelRefByTab = {
  agents: agentsPanelRef,
  skills: skillsPanelRef,
  tools: toolsPanelRef,
  memory: memoryPanelRef,
  "aip-keys": aipKeysPanelRef,
};

const refreshing = computed(() =>
  readPanelLoading(panelRefByTab[activeTab.value]?.value)
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
  if (activeTab.value === "agents" || activeTab.value === "skills") {
    await panel?.reload?.({ foreground: true });
    return;
  }
  await panel?.load?.({ foreground: true });
}

function connectExternalAgent() {
  agentsPanelRef.value?.openExternalAgentModal?.();
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
          </div>
          <AgentsTabPanel
            v-if="mountedTabs.agents"
            ref="agentsPanelRef"
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
  overflow: visible;
}
.agent-skills-view :deep(.n-tabs-nav) {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--platform-bg);
}
.agent-skills-view :deep(.n-tabs-tab--active) {
  color: var(--n-tab-text-color) !important;
}
.agent-skills-view :deep(.n-tabs-tab):hover {
  color: var(--n-tab-text-color) !important;
}
.agent-skills-view :deep(.n-tabs-bar) {
  display: none;
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
  gap: 2px;
}

/* 智能体 tab 头部图标按钮紧凑化：与技能 tab 按钮大小一致 */
.agents-tab-actions :deep(.icon-action) {
  width: 22px !important;
  height: 22px !important;
}
.agents-tab-actions :deep(.n-icon),
.agents-tab-actions :deep(.n-icon svg) {
  font-size: 13px !important;
  width: 13px;
  height: 13px;
}

</style>

<style>
/* 共享样式（非 scoped） */
@import "../../styles/agent-skills.css";
</style>
