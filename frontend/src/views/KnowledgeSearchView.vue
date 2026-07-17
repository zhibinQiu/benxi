<script setup>
defineOptions({ name: "KnowledgeSearchView" });
import { computed, inject, ref } from "vue";
import { AddOutline, GitNetworkOutline } from "@vicons/ionicons5";
import KnowledgeSearchPanel from "../components/KnowledgeSearchPanel.vue";
import IconAction from "../components/IconAction.vue";
import { createPlatformChatStream } from "../api/rag.js";
import { useI18n } from "../composables/useI18n.js";
import { usePageHeaderExtension } from "../composables/usePageHeaderExtension.js";
import { KNOWLEDGE_SCOPE_SELECTION_KEY, readKnowledgeScopeSelection } from "../utils/knowledgeScopeSelectionCache.js";

const knowledgeQaChatStream = createPlatformChatStream("/api/v1/knowledge/qa/chat/stream");

const { t, tm } = useI18n();
const { headerExtensionActive } = usePageHeaderExtension();

const selection = inject(
  KNOWLEDGE_SCOPE_SELECTION_KEY,
  ref(readKnowledgeScopeSelection())
);
const panelKey = ref(0);
const useAgentic = ref(true);

const suggestions = computed(() => tm("knowledgeSearch.suggestions") || []);

const canAsk = computed(() => (selection.value?.documentIds?.length || 0) > 0);
const hasCheckedDocs = computed(() => (selection.value?.totalSelected || 0) > 0);

async function handleChatStream(params, callbacks) {
  if (!canAsk.value) {
    throw new Error(t("knowledgeSearch.selectIndexedDocs"));
  }
  return knowledgeQaChatStream(
    {
      ...params,
      document_ids: selection.value.documentIds,
      use_agentic: useAgentic.value,
    },
    callbacks
  );
}

function resetSearch() {
  panelKey.value += 1;
}
</script>

<template>
  <div class="knowledge-feature-panel accent-theme">
    <Teleport v-if="headerExtensionActive" to="#header-actions">
      <IconAction
        :label="t('knowledgeSearch.useAgent')"
        :icon="GitNetworkOutline"
        :active="useAgentic"
        @click="useAgentic = !useAgentic"
      />
      <IconAction
        :label="t('knowledgeSearch.newSearch')"
        :icon="AddOutline"
        @click="resetSearch"
      />
    </Teleport>

    <KnowledgeSearchPanel
      :key="panelKey"
      class="knowledge-search-page__panel"
      :suggestions="canAsk ? suggestions : []"
      :can-search="canAsk"
      :has-checked-docs="hasCheckedDocs"
      :stream-chat="handleChatStream"
    />
  </div>
</template>

<style scoped>
.knowledge-feature-panel {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  height: 100%;
}

.knowledge-search-page__panel {
  flex: 1;
  min-height: 0;
  border-radius: 0;
}

/* ── 知识检索页面：通过 accent-theme 变量实现蓝色主题 ── */
.knowledge-search-page__panel :deep(.knowledge-search-panel__icon) {
  color: var(--platform-accent);
}
.knowledge-search-page__panel :deep(.agent-workflow__agent-tag) {
  color: var(--platform-accent);
  background: var(--platform-accent-soft);
  border: 1px solid var(--platform-accent-border-soft);
}
.knowledge-search-page__panel :deep(.agent-workflow__checkbox) {
  background: var(--platform-accent-soft);
  color: var(--platform-accent);
}
.knowledge-search-page__panel :deep(.agent-workflow__checkbox--done) {
  background: var(--platform-accent-soft);
  color: var(--platform-accent);
}
</style>
