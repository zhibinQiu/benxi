<script setup>
defineOptions({ name: "KnowledgeSearchView" });
import { computed, ref } from "vue";
import { NButton, NCheckbox, NIcon } from "naive-ui";
import { AddOutline, SearchOutline } from "@vicons/ionicons5";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import HintTooltip from "../components/HintTooltip.vue";
import KnowledgeScopeTree from "../components/KnowledgeScopeTree.vue";
import KnowledgeSearchPanel from "../components/KnowledgeSearchPanel.vue";
import { knowledgeQaChatStream } from "../api/knowledge.js";
import { useI18n } from "../composables/useI18n.js";
import { messages } from "../locales";
import { readKnowledgeScopeSelection } from "../utils/knowledgeScopeSelectionCache.js";

const { t, locale } = useI18n();

const selection = ref(readKnowledgeScopeSelection());
const panelKey = ref(0);
const useAgentic = ref(true);

const suggestions = computed(
  () => messages[locale.value]?.knowledgeSearch?.suggestions || []
);

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

function onSelectionChange(next) {
  selection.value = next;
}

function resetSearch() {
  panelKey.value += 1;
}
</script>

<template>
  <FeatureSubsystemShell fill flush-start flush-end :show-intro="false">
    <template #extra>
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
        <n-icon :size="16" :component="SearchOutline" class="knowledge-search-toolbar__icon" />
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
    </template>

    <div class="knowledge-search-page">
      <aside class="knowledge-search-page__sider">
        <KnowledgeScopeTree @selection-change="onSelectionChange" />
      </aside>

      <main class="knowledge-search-page__main">
        <KnowledgeSearchPanel
          :key="panelKey"
          class="knowledge-search-page__panel"
          :suggestions="canAsk ? suggestions : []"
          :can-search="canAsk"
          :has-checked-docs="hasCheckedDocs"
          :stream-chat="handleChatStream"
        />
      </main>
    </div>
  </FeatureSubsystemShell>
</template>

<style scoped>
.knowledge-search-page {
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

.knowledge-search-page__sider {
  flex-shrink: 0;
  width: min(300px, 36vw);
  min-width: 228px;
  border-right: 1px solid var(--platform-border);
  background: var(--platform-bg-secondary);
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.knowledge-search-page__main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.knowledge-search-page__panel {
  flex: 1;
  min-height: 0;
  border-radius: 0;
}

.knowledge-search-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-width: 0;
}

.knowledge-search-toolbar__agent {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
  font-size: 13px;
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
  font-size: 12px;
  line-height: 1.45;
  color: var(--platform-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.knowledge-search-toolbar__reset {
  flex-shrink: 0;
}

@media (max-width: 900px) {
  .knowledge-search-page {
    flex-direction: column;
  }

  .knowledge-search-page__sider {
    width: 100%;
    max-height: 38vh;
    border-right: none;
    border-bottom: 1px solid var(--platform-border);
  }
}
</style>
