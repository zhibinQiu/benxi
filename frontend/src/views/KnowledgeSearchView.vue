<script setup>
defineOptions({ name: "KnowledgeSearchView" });
import { computed, inject, ref } from "vue";
import { NButton, NCheckbox, NIcon } from "naive-ui";
import { AddOutline, SearchOutline } from "@vicons/ionicons5";
import HintTooltip from "../components/HintTooltip.vue";
import KnowledgeSearchPanel from "../components/KnowledgeSearchPanel.vue";
import { usePageHeaderExtension } from "../composables/usePageHeaderExtension.js";
import { knowledgeQaChatStream } from "../api/knowledge.js";
import { useI18n } from "../composables/useI18n.js";
import { KNOWLEDGE_SCOPE_SELECTION_KEY, readKnowledgeScopeSelection } from "../utils/knowledgeScopeSelectionCache.js";

const { t, tm } = useI18n();
const { headerExtensionActive } = usePageHeaderExtension();

const selection = inject(
  KNOWLEDGE_SCOPE_SELECTION_KEY,
  ref(readKnowledgeScopeSelection())
);
const panelKey = ref(0);
const useAgentic = ref(true);

const suggestions = computed(() => tm("knowledgeSearch.suggestions") || []);

const selectionHint = computed(() => {
  if (!selection.value?.totalSelected) {
    return t("knowledgeSearch.selectIndexedDocs");
  }
  if (!selection.value?.documentIds?.length) {
    return t("knowledgeSearch.selectedNoneIndexed", {
      total: selection.value.totalSelected,
    });
  }
  const {
    documentIds = [],
    totalSelected = 0,
    indexReadyCount = 0,
    label,
    type,
  } = selection.value;

  if (indexReadyCount === 0) {
    return t("knowledgeSearch.selectedNoneIndexed", { total: totalSelected });
  }

  if (type === "document") {
    return label;
  }

  if (totalSelected !== indexReadyCount) {
    return t("knowledgeSearch.selectedPartial", {
      ready: indexReadyCount,
      total: totalSelected,
    });
  }

  return t("knowledgeSearch.selectedCount", { count: indexReadyCount });
});

const canAsk = computed(() => (selection.value?.documentIds?.length || 0) > 0);
const hasCheckedDocs = computed(() => (selection.value?.totalSelected || 0) > 0);

async function handleChatStream(params, callbacks) {
  if (!canAsk.value) {
    throw new Error(t("knowledgeSearch.selectIndexedDocs"));
  }
  return knowledgeQaChatStream(
    {
      ...params,
      documentIds: selection.value.documentIds,
      useAgentic: useAgentic.value,
    },
    callbacks
  );
}

function resetSearch() {
  panelKey.value += 1;
}
</script>

<template>
  <div class="knowledge-feature-panel">
    <Teleport v-if="headerExtensionActive" to="#page-header-extension">
    <div class="subsystem-extra-bar">
      <div class="subsystem-extra-row">
        <div class="knowledge-search-toolbar">
          <label class="knowledge-search-toolbar__agent">
            <n-checkbox v-model:checked="useAgentic" size="small">
              {{ t("knowledgeSearch.useAgent") }}
            </n-checkbox>
            <HintTooltip
              :text="t('knowledgeSearch.useAgentTooltip')"
              variant="inline"
              placement="bottom"
            />
          </label>
          <n-icon :size="19" :component="SearchOutline" class="knowledge-search-toolbar__icon" />
          <span class="knowledge-search-toolbar__hint">{{ selectionHint }}</span>
          <n-button
            size="small"
            quaternary
            class="knowledge-search-toolbar__reset"
            @click="resetSearch"
          >
            <template #icon>
              <n-icon :component="AddOutline" />
            </template>
            {{ t("knowledgeSearch.newSearch") }}
          </n-button>
        </div>
      </div>
    </div>
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

.knowledge-search-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  min-width: 0;
}

.knowledge-search-toolbar__agent {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
  font-size: 16px;
  color: var(--platform-text);
  cursor: pointer;
  user-select: none;
}

.knowledge-search-toolbar__icon {
  flex-shrink: 0;
  color: var(--platform-accent);
}

.knowledge-search-toolbar__hint {
  flex: 1;
  min-width: 0;
  font-size: 14px;
  line-height: 1.45;
  color: var(--platform-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.knowledge-search-toolbar__reset {
  flex-shrink: 0;
}
</style>
