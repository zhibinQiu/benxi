<script setup>
defineOptions({ name: "KnowledgeSearchView" });
import { computed, inject, ref } from "vue";
import { NIcon } from "naive-ui";
import { AddOutline, SearchOutline } from "@vicons/ionicons5";
import KnowledgeSearchPanel from "../components/KnowledgeSearchPanel.vue";
import { usePageHeaderExtension } from "../composables/usePageHeaderExtension.js";
import { createPlatformChatStream } from "../api/rag.js";
import { useI18n } from "../composables/useI18n.js";
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
    <Teleport v-if="headerExtensionActive" to="#page-header-extension">
    <div class="subsystem-extra-bar">
      <div class="subsystem-extra-row">
        <div class="knowledge-search-toolbar">
          <n-icon :size="19" :component="SearchOutline" class="knowledge-search-toolbar__icon" />
          <span class="knowledge-search-toolbar__hint">{{ selectionHint }}</span>
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
  >
    <template #toolbar>
      <label
        class="ks-toolbar-btn ks-toolbar-btn--agent"
        :class="{ 'ks-toolbar-btn--active': useAgentic }"
      >
        <input
          v-model="useAgentic"
          type="checkbox"
          class="ks-toolbar-btn__checkbox"
        />
        <span>{{ t("knowledgeSearch.useAgent") }}</span>
      </label>
      <button
        type="button"
        class="ks-toolbar-btn"
        :disabled="loadingHistory"
        @click="resetSearch"
      >
        <n-icon :size="13" :component="AddOutline" />
        <span>{{ t("knowledgeSearch.newSearch") }}</span>
      </button>
    </template>
  </KnowledgeSearchPanel>
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

.knowledge-search-toolbar__icon {
  flex-shrink: 0;
  color: var(--platform-icon);
}

.knowledge-search-toolbar__hint {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  line-height: 1.45;
  color: var(--platform-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ks-toolbar-btn {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 3px 8px;
  font-size: 12px;
  line-height: 1.3;
  border: 1px solid var(--platform-border);
  background: var(--platform-bg-secondary);
  color: var(--platform-text-secondary);
  border-radius: 6px;
  white-space: nowrap;
  cursor: pointer;
  font-family: inherit;
  transition: color var(--platform-duration-smooth) ease,
              background var(--platform-duration-smooth) ease,
              border-color var(--platform-duration-smooth) ease;
}
.ks-toolbar-btn:hover {
  color: var(--platform-text);
  background: var(--platform-bg-tertiary);
  border-color: var(--platform-border-strong);
}
.ks-toolbar-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.ks-toolbar-btn__checkbox {
  appearance: none;
  width: 12px;
  height: 12px;
  border: 1.5px solid var(--platform-text-tertiary);
  border-radius: 3px;
  background: transparent;
  cursor: pointer;
  flex-shrink: 0;
  transition: background 0.15s, border-color 0.15s;
  margin: 0;
}
.ks-toolbar-btn--active .ks-toolbar-btn__checkbox {
  background: var(--platform-accent);
  border-color: var(--platform-accent);
}
.ks-toolbar-btn--agent:hover .ks-toolbar-btn__checkbox {
  border-color: var(--platform-accent);
}
</style>
