<script setup>
defineOptions({ name: "KnowledgeSearchView" });
import { computed, onMounted, ref } from "vue";
import { NButton, NIcon } from "naive-ui";
import { AddOutline, SearchOutline } from "@vicons/ionicons5";
import AiChatPanel from "../components/AiChatPanel.vue";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import KnowledgeScopeTree from "../components/KnowledgeScopeTree.vue";
import { knowledgeQaChatStream } from "../api/knowledge.js";
import { clearChatSession } from "../utils/chatSessionPersist.js";

const selection = ref(null);
const chatResetKey = ref(0);

const suggestions = [
  "这份文档的核心结论是什么？",
  "有哪些与碳排放核算相关的要点？",
  "请列出文档中的关键数据指标",
];

const selectionDocKey = computed(() =>
  [...(selection.value?.documentIds || [])].sort().join(",")
);

const chatPanelKey = computed(
  () => `${selectionDocKey.value || "none"}:${chatResetKey.value}`
);

const selectionHint = computed(() => {
  if (!selection.value?.documentIds?.length) {
    return "请从左侧勾选已成功索引的文档";
  }
  const {
    documentIds = [],
    totalSelected = 0,
    indexReadyCount = 0,
    label,
    type,
  } = selection.value;

  if (indexReadyCount === 0) {
    return `已选 ${totalSelected} 份，无已索引文档`;
  }

  if (type === "document") {
    return label;
  }

  if (totalSelected !== indexReadyCount) {
    return `${indexReadyCount}/${totalSelected} 份可问答`;
  }

  return `${indexReadyCount} 份文档`;
});

const canAsk = computed(() => (selection.value?.documentIds?.length || 0) > 0);

async function handleChatStream(params, callbacks) {
  if (!canAsk.value) {
    throw new Error("请从左侧勾选已成功索引的文档");
  }
  return knowledgeQaChatStream(
    {
      ...params,
      documentIds: selection.value.documentIds,
    },
    callbacks
  );
}

function onSelectionChange(next) {
  selection.value = next;
  chatResetKey.value += 1;
}

function resetChat() {
  chatResetKey.value += 1;
}

onMounted(() => {
  clearChatSession("knowledge-search");
});
</script>

<template>
  <FeatureSubsystemShell fill flush-start :show-intro="false">
    <template #extra>
      <div class="knowledge-search-toolbar">
        <n-icon :size="16" :component="SearchOutline" class="knowledge-search-toolbar__icon" />
        <span class="knowledge-search-toolbar__hint">{{ selectionHint }}</span>
        <n-button
          size="small"
          quaternary
          class="knowledge-search-toolbar__reset"
          @click="resetChat"
        >
          <template #icon>
            <n-icon :component="AddOutline" />
          </template>
          新检索
        </n-button>
      </div>
    </template>

    <div class="knowledge-search-page">
      <aside class="knowledge-search-page__sider">
        <KnowledgeScopeTree @selection-change="onSelectionChange" />
      </aside>

      <main class="knowledge-search-page__main">
        <AiChatPanel
          :key="chatPanelKey"
          class="knowledge-search-page__chat"
          title="知识检索"
          reply-placeholder="基于所选文档继续提问…"
          :suggestions="canAsk ? suggestions : []"
          :icon="SearchOutline"
          :streaming="true"
          :show-workflow-progress="true"
          :rich-markdown="true"
          :show-citations="true"
          :linkify-citations="true"
          :show-session-actions="false"
          :show-chat-header-brand="false"
          :stream-chat="handleChatStream"
          title-gradient
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
  border-radius: 0 var(--platform-radius) 0 0;
  overflow: hidden;
  border: 1px solid var(--platform-border);
  border-left: none;
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

.knowledge-search-page__chat {
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
