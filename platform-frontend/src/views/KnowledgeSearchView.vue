<script setup>
import { computed, ref, watch } from "vue";
import { NIcon } from "naive-ui";
import { SearchOutline } from "@vicons/ionicons5";
import AiChatPanel from "../components/AiChatPanel.vue";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import KnowledgeScopeTree from "../components/KnowledgeScopeTree.vue";
import { knowledgeQaChatSend } from "../api/knowledge.js";

const selectedKey = ref("");
const selection = ref(null);
const sessionId = ref(null);

const suggestions = [
  "这份文档的核心结论是什么？",
  "有哪些与碳排放核算相关的要点？",
  "请列出文档中的关键数据指标",
];

const selectionHint = computed(() => {
  if (!selection.value) {
    return "请从左侧选择知识库、分级目录或具体文档后开始提问";
  }
  const count = selection.value.documentIds?.length || 0;
  if (count === 0) {
    return `已选「${selection.value.label}」，该范围内暂无可问答文档`;
  }
  if (selection.value.type === "document") {
    return `当前文档：${selection.value.label}`;
  }
  return `当前范围：${selection.value.label}（${count} 份文档，最多 20 份参与问答）`;
});

const canAsk = computed(() => (selection.value?.documentIds?.length || 0) > 0);

async function handleChatSend({ message, conversationId }) {
  if (!canAsk.value) {
    throw new Error("请从左侧选择包含文档的知识库或具体文档");
  }
  const result = await knowledgeQaChatSend({
    message,
    conversationId: conversationId || sessionId.value,
    documentIds: selection.value.documentIds,
  });
  sessionId.value = result.conversation_id;
  return result;
}

function onSelectionChange(next) {
  selection.value = next;
  sessionId.value = null;
}

watch(selectedKey, (key) => {
  if (!key) onSelectionChange(null);
});
</script>

<template>
  <FeatureSubsystemShell fill :show-intro="false">
    <div class="knowledge-search-page">
      <aside class="knowledge-search-page__sider">
        <KnowledgeScopeTree
          v-model:selected-key="selectedKey"
          @selection-change="onSelectionChange"
        />
      </aside>

      <main class="knowledge-search-page__main">
        <div class="knowledge-search-page__scope-bar feature-local-nav">
          <n-icon :size="16" :component="SearchOutline" class="knowledge-search-page__scope-icon" />
          <span>{{ selectionHint }}</span>
        </div>

        <AiChatPanel
          class="knowledge-search-page__chat"
          chat-scope="knowledge-search"
          title="知识检索"
          description="基于企业知识库文档进行语义检索与问答，支持按分级库或单篇文档限定范围，并展示引用来源。"
          subtitle="选择左侧文档范围后开始提问"
          reply-placeholder="基于所选文档继续提问…"
          :suggestions="canAsk ? suggestions : []"
          :icon="SearchOutline"
          :streaming="false"
          :show-citations="true"
          :chat-send="handleChatSend"
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
  width: min(280px, 34vw);
  min-width: 220px;
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

.knowledge-search-page__chat :deep(.ai-home) {
  border-radius: 0;
  height: 100%;
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
