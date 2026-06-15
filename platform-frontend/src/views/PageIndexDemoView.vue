<script setup>
defineOptions({ name: "PageIndexDemoView" });
import { computed, onMounted, ref } from "vue";
import { NAlert, NButton, NIcon } from "naive-ui";
import { AddOutline, GitBranchOutline } from "@vicons/ionicons5";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import KnowledgeScopeTree from "../components/KnowledgeScopeTree.vue";
import KnowledgeSearchPanel from "../components/KnowledgeSearchPanel.vue";
import { fetchPageindexMeta, pageindexSearchStream } from "../api/pageindex.js";
import { useI18n } from "../composables/useI18n.js";
import { messages } from "../locales";
import { readKnowledgeScopeSelection } from "../utils/knowledgeScopeSelectionCache.js";

const { t, locale } = useI18n();

const selection = ref(readKnowledgeScopeSelection());
const panelKey = ref(0);
const meta = ref(null);
const metaLoading = ref(true);

const suggestions = computed(
  () => messages[locale.value]?.pageindexDemo?.suggestions || []
);

const selectionHint = computed(() => {
  if (!selection.value?.totalSelected) {
    return t("pageindexDemo.selectIndexedDocs");
  }
  if (!selection.value?.documentIds?.length) {
    return t("pageindexDemo.selectedNoneIndexed", {
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
    return t("pageindexDemo.selectedNoneIndexed", { total: totalSelected });
  }

  if (type === "document") {
    return label;
  }

  if (totalSelected !== indexReadyCount) {
    return t("pageindexDemo.selectedPartial", {
      ready: indexReadyCount,
      total: totalSelected,
    });
  }

  return t("pageindexDemo.selectedCount", { count: indexReadyCount });
});

const canAsk = computed(() => (selection.value?.documentIds?.length || 0) > 0);
const hasCheckedDocs = computed(() => (selection.value?.totalSelected || 0) > 0);

const metaHint = computed(() => {
  if (metaLoading.value) return "";
  if (!meta.value?.enabled) return t("pageindexDemo.disabled");
  if (!meta.value?.package_available) return t("pageindexDemo.packageMissing");
  if (!meta.value?.llm_configured) return t("pageindexDemo.llmMissing");
  return meta.value?.hint || "";
});

const showMetaAlert = computed(() => Boolean(metaHint.value));

async function loadMeta() {
  metaLoading.value = true;
  try {
    meta.value = await fetchPageindexMeta();
  } catch {
    meta.value = null;
  } finally {
    metaLoading.value = false;
  }
}

async function handleChatStream(params, callbacks) {
  if (!canAsk.value) {
    throw new Error(t("pageindexDemo.selectIndexedDocs"));
  }
  return pageindexSearchStream(
    {
      question: params.message,
      documentIds: selection.value.documentIds,
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

onMounted(loadMeta);
</script>

<template>
  <FeatureSubsystemShell fill flush-start flush-end :show-intro="false">
    <template #extra>
      <div class="pageindex-demo-toolbar">
        <n-icon :size="16" :component="GitBranchOutline" class="pageindex-demo-toolbar__icon" />
        <span class="pageindex-demo-toolbar__hint">{{ selectionHint }}</span>
        <n-button
          size="small"
          quaternary
          class="pageindex-demo-toolbar__reset"
          @click="resetSearch"
        >
          <template #icon>
            <n-icon :component="AddOutline" />
          </template>
          {{ t("pageindexDemo.newSearch") }}
        </n-button>
      </div>
    </template>

    <div v-if="showMetaAlert" class="pageindex-demo-alert">
      <n-alert type="warning" :bordered="false">
        {{ metaHint }}
      </n-alert>
    </div>

    <div class="pageindex-demo-page">
      <aside class="pageindex-demo-page__sider">
        <KnowledgeScopeTree @selection-change="onSelectionChange" />
      </aside>

      <main class="pageindex-demo-page__main">
        <p class="pageindex-demo-page__intro">
          {{ t("pageindexDemo.intro") }}
        </p>
        <KnowledgeSearchPanel
          :key="panelKey"
          class="pageindex-demo-page__panel"
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
.pageindex-demo-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.pageindex-demo-toolbar__icon {
  flex-shrink: 0;
  opacity: 0.75;
}

.pageindex-demo-toolbar__hint {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  opacity: 0.85;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pageindex-demo-alert {
  padding: 0 16px 8px;
}

.pageindex-demo-page {
  display: flex;
  gap: 0;
  min-height: 0;
  flex: 1;
  height: 100%;
}

.pageindex-demo-page__sider {
  width: min(320px, 36vw);
  flex-shrink: 0;
  border-right: 1px solid var(--platform-border-subtle, rgba(255, 255, 255, 0.08));
  min-height: 0;
  overflow: hidden;
}

.pageindex-demo-page__main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.pageindex-demo-page__intro {
  margin: 0;
  padding: 12px 20px 0;
  font-size: 13px;
  line-height: 1.5;
  opacity: 0.78;
}

.pageindex-demo-page__panel {
  flex: 1;
  min-height: 0;
}
</style>
