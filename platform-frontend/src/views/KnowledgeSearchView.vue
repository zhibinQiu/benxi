<script setup>
defineOptions({ name: "KnowledgeSearchView" });
import { computed, ref } from "vue";
import { NIcon } from "naive-ui";
import { SearchOutline } from "@vicons/ionicons5";
import AiChatPanel from "../components/AiChatPanel.vue";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import KnowledgeScopeTree from "../components/KnowledgeScopeTree.vue";
import { knowledgeQaChatStream } from "../api/knowledge.js";

const selection = ref(null);
const sessionId = ref(null);

const suggestions = [
  "这份文档的核心结论是什么？",
  "有哪些与碳排放核算相关的要点？",
  "请列出文档中的关键数据指标",
];

const selectionHint = computed(() => {
  if (!selection.value?.documentIds?.length) return "";
  const {
    documentIds = [],
    totalSelected = 0,
    indexReadyCount = 0,
    label,
    type} = selection.value;

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
  const prevIds = [...(selection.value?.documentIds || [])].sort().join(",");
  const nextIds = [...(next?.documentIds || [])].sort().join(",");
  if (sessionId.value && prevIds !== nextIds) {
    sessionId.value = null;
  }
  selection.value = next;
}
</script>

<template>
  <FeatureSubsystemShell fill :show-intro="false">
    <div class="knowledge-search-page">
      <aside class="knowledge-search-page__sider">
        <KnowledgeScopeTree @selection-change="onSelectionChange" />
      </aside>

      <main class="knowledge-search-page__main">
        <div class="knowledge-search-page__scope-bar feature-local-nav">
          <n-icon :size="16" :component="SearchOutline" class="knowledge-search-page__scope-icon" />
          <span v-if="selectionHint">{{ selectionHint }}</span>
        </div>

        <AiChatPanel
          class="knowledge-search-page__chat"
          chat-scope="knowledge-search"
          title="知识检索"
          reply-placeholder="基于所选文档继续提问…"
          :suggestions="canAsk ? suggestions : []"
          :icon="SearchOutline"
          :streaming="true"
          :show-workflow-progress="true"
          :rich-markdown="true"
          :show-citations="true"
          :linkify-citations="true"
          :stream-chat="handleChatStream"
          v-model:conversation-id="sessionId"
          title-gradient
          :show-chat-header-brand="false"
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
  border-radius: var(--platform-radius);
  overflow: hidden;
  border: 1px solid var(--platform-border);
  background: var(--platform-bg-elevated);
}

.knowledge-search-page__sider {
  flex-shrink: 0;
  width: min(320px, 38vw);
  min-width: 240px;
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

.knowledge-search-page__scope-bar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  font-size: 12px;
  line-height: 1.45;
  color: var(--platform-text-secondary);
}

.knowledge-search-page__scope-icon {
  flex-shrink: 0;
  color: var(--platform-accent);
}

.knowledge-search-page__chat {
  flex: 1;
  min-height: 0;
  border-radius: 0;
}

@media (max-width: 900px) {
  .knowledge-search-page {
    flex-direction: column;
  }

  .knowledge-search-page__sider {
    width: 100%;
    max-height: 40vh;
    border-right: none;
    border-bottom: 1px solid var(--platform-border);
  }
}
</style>
