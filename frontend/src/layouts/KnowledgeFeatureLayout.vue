<script setup>
defineOptions({ name: "KnowledgeFeatureLayout" });
import { computed, defineAsyncComponent, onActivated, provide, ref, watch } from "vue";
import { useRoute } from "vue-router";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import KnowledgeScopeTree from "../components/KnowledgeScopeTree.vue";
import {
  KNOWLEDGE_SCOPE_SELECTION_KEY,
  readKnowledgeScopeSelection,
} from "../utils/knowledgeScopeSelectionCache.js";

/** 仅保留当前活跃面板，切换检索/报告时释放非活跃 AiChatPanel 实例 */
const KEEP_ALIVE_MAX = 1;

const KnowledgeSearchView = defineAsyncComponent(
  () => import("../views/KnowledgeSearchView.vue")
);
const ReportGenerationView = defineAsyncComponent(
  () => import("../views/ReportGenerationView.vue")
);

const PANEL_COMPONENTS = {
  "knowledge-search": KnowledgeSearchView,
  "report-generation": ReportGenerationView,
};

const route = useRoute();
const activePanel = ref(String(route.name || ""));

watch(
  () => route.name,
  (name) => {
    activePanel.value = String(name || "");
  },
  { immediate: true }
);

const activePanelComponent = computed(() => PANEL_COMPONENTS[activePanel.value] || null);

const selection = ref(readKnowledgeScopeSelection());
provide(KNOWLEDGE_SCOPE_SELECTION_KEY, selection);

function onSelectionChange(next) {
  selection.value = next;
}

onActivated(() => {
  activePanel.value = String(route.name || "");
  selection.value = readKnowledgeScopeSelection();
});
</script>

<template>
  <FeatureSubsystemShell fill flush-start flush-end :show-intro="false">
    <div
      class="knowledge-feature-page"
      :class="activePanel === 'knowledge-search' ? 'knowledge-search-page' : 'report-gen-page'"
    >
      <aside class="knowledge-feature-page__sider knowledge-search-page__sider">
        <KnowledgeScopeTree @selection-change="onSelectionChange" />
      </aside>
      <main class="knowledge-feature-page__main knowledge-search-page__main report-gen-page__main">
        <KeepAlive :max="KEEP_ALIVE_MAX">
          <component
            :is="activePanelComponent"
            v-if="activePanelComponent"
            :key="activePanel"
          />
        </KeepAlive>
      </main>
    </div>
  </FeatureSubsystemShell>
</template>

<style scoped>
.knowledge-feature-page {
  display: flex;
  flex: 1;
  min-height: 0;
  height: 100%;
  width: 100%;
  box-sizing: border-box;
  border-radius: 0;
  overflow: hidden;
  border: 1px solid var(--platform-border);
  border-left: none;
  border-right: none;
  background: var(--platform-bg-elevated);
}

.knowledge-feature-page__sider {
  flex-shrink: 0;
  width: min(360px, 36vw);
  min-width: 274px;
  border-right: 1px solid var(--platform-border);
  background: var(--platform-bg-secondary);
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.knowledge-feature-page__main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.knowledge-feature-page__main :deep(> *) {
  flex: 1;
  min-height: 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  height: 100%;
}

@media (max-width: 900px) {
  .knowledge-feature-page {
    flex-direction: column;
  }

  .knowledge-feature-page__sider {
    width: 100%;
    max-height: 38vh;
    border-right: none;
    border-bottom: 1px solid var(--platform-border);
  }
}
</style>
