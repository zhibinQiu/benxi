<script setup>
import { computed, nextTick, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref } from "vue";
import { NIcon } from "naive-ui";
import { SearchOutline } from "@vicons/ionicons5";
import ChatComposer from "./ChatComposer.vue";
import ChatBubbleRetry from "./ChatBubbleRetry.vue";
import KnowledgeChatContent from "./KnowledgeChatContent.vue";
import KnowledgeCitationCard from "./KnowledgeCitationCard.vue";
import KnowledgeMindMap from "./KnowledgeMindMap.vue";
import AgentWorkflowProgress from "./AgentWorkflowProgress.vue";
import { usePlatformUi } from "../composables/usePlatformUi.js";
import { useI18n } from "../composables/useI18n.js";
import { emptyAgentWorkflow, applyAgentWorkflowEvent } from "../utils/agentWorkflow.js";
import { PLATFORM_APP_NAME } from "../constants/platform.js";

const props = defineProps({
  suggestions: { type: Array, default: () => [] },
  streamChat: { type: Function, required: true },
  canSearch: { type: Boolean, default: true },
  hasCheckedDocs: { type: Boolean, default: false },
});

const { t } = useI18n();
const ui = usePlatformUi();

const phase = ref("landing");
const input = ref("");
const sending = ref(false);
const question = ref("");
const answer = ref("");
const citations = ref([]);
const workflow = ref(emptyAgentWorkflow());
const answerView = ref("answer");
const resultsRef = ref(null);
const composerRef = ref(null);
const mindmapRef = ref(null);
let streamAbort = null;

const hasResults = computed(() => phase.value === "results");

const composerPlaceholder = computed(() => {
  if (props.canSearch) {
    return hasResults.value
      ? t("knowledgeSearch.searchAgainPlaceholder")
      : t("knowledgeSearch.inputPlaceholder");
  }
  if (props.hasCheckedDocs) {
    return t("knowledgeSearch.inputPlaceholderNotIndexed");
  }
  return t("knowledgeSearch.inputPlaceholderNeedSelection");
});

const composerRows = computed(() =>
  hasResults.value ? { min: 1, max: 1 } : { min: 3, max: 8 }
);

const displaySubtitle = computed(() => `${PLATFORM_APP_NAME} · ${t("knowledgeSearch.title")}`);

function emptyWorkflow() {
  return emptyAgentWorkflow();
}

function applyWorkflowEvent(state, ev) {
  return applyAgentWorkflowEvent(state, ev, t);
}

async function scrollResultsTop() {
  await nextTick();
  const el = resultsRef.value;
  if (el) el.scrollTop = 0;
}

function resetSearch() {
  streamAbort?.abort();
  streamAbort = null;
  sending.value = false;
  phase.value = "landing";
  input.value = "";
  question.value = "";
  answer.value = "";
  citations.value = [];
  workflow.value = emptyWorkflow();
  answerView.value = "answer";
}

defineExpose({ resetSearch });

async function runSearch(content) {
  const text = (content || input.value).trim();
  if (!text) return;
  if (!props.canSearch) {
    ui.error(
      props.hasCheckedDocs
        ? t("knowledgeSearch.searchBlockedNotIndexed")
        : t("knowledgeSearch.selectIndexedDocs")
    );
    return;
  }

  if (sending.value) {
    streamAbort?.abort();
  }
  streamAbort = new AbortController();

  question.value = text;
  answer.value = "";
  citations.value = [];
  workflow.value = emptyWorkflow();
  answerView.value = "answer";
  phase.value = "results";
  sending.value = true;
  input.value = "";

  await scrollResultsTop();

  let scrollTick = 0;
  try {
    await props.streamChat(
      { message: text, history: [], conversationId: null },
      {
        signal: streamAbort.signal,
        onWorkflow: (ev) => {
          applyWorkflowEvent(workflow.value, ev);
        },
        onCitations: (items) => {
          if (Array.isArray(items)) citations.value = items;
        },
        onReplace: (full) => {
          answer.value = full;
        },
        onDelta: (delta) => {
          answer.value += delta;
          scrollTick += 1;
        },
        onError: (err) => {
          throw err;
        },
        onDone: (payload) => {
          const full = (payload?.reply || "").trim();
          if (full && full.length >= answer.value.length) {
            answer.value = full;
          }
          if (Array.isArray(payload?.citations)) {
            citations.value = payload.citations;
          }
          workflow.value.running = false;
        },
      }
    );
    if (!answer.value.trim()) {
      answer.value = "未能生成回答，请尝试调整问题或重新选择文档。";
    }
  } catch (e) {
    if (e?.name === "AbortError") return;
    ui.error(e.message || "检索失败");
    if (!answer.value.trim()) {
      answer.value = "抱歉，检索失败，请稍后重试。";
    }
  } finally {
    sending.value = false;
    streamAbort = null;
    workflow.value.running = false;
  }
}

function onComposerKeydown(e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    runSearch();
  }
}

function useSuggestion(text) {
  input.value = text;
  runSearch(text);
}

function retryCurrentSearch() {
  if (sending.value || !question.value.trim()) return;
  runSearch(question.value);
}

function stopGeneration() {
  streamAbort?.abort();
  sending.value = false;
  workflow.value.running = false;
}

function cleanupStream() {
  streamAbort?.abort();
  streamAbort = null;
  sending.value = false;
  workflow.value.running = false;
}

async function focusComposer() {
  await nextTick();
  composerRef.value?.focus?.();
}

function onCitationClick(index) {
  const el = document.getElementById(`knowledge-cite-card-${index}`);
  el?.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function showAnswerView() {
  answerView.value = "answer";
}

async function showMindmapView() {
  answerView.value = "mindmap";
  await nextTick();
  mindmapRef.value?.loadMindmap?.();
}

onBeforeUnmount(() => {
  cleanupStream();
});

onDeactivated(() => {
  cleanupStream();
});

onActivated(() => {
  focusComposer();
});

onMounted(() => {
  focusComposer();
});
</script>

<template>
  <div class="knowledge-search-panel">
    <div
      class="knowledge-search-panel__body"
      :class="{
        'knowledge-search-panel__body--landing': !hasResults,
        'knowledge-search-panel__body--results': hasResults,
      }"
    >
      <Transition name="ai-welcome">
        <div v-if="!hasResults" key="landing" class="knowledge-search-panel__landing knowledge-search-panel__content-column">
          <div class="knowledge-search-panel__hero">
            <div class="knowledge-search-panel__icon">
              <n-icon :size="36" :component="SearchOutline" />
            </div>
            <h1 class="knowledge-search-panel__title platform-text-gradient">
              {{ t("knowledgeSearch.title") }}
            </h1>
            <p class="knowledge-search-panel__sub">{{ displaySubtitle }}</p>
          </div>
        </div>
      </Transition>

        <div v-if="hasResults" ref="resultsRef" class="knowledge-search-panel__results">
        <div class="knowledge-search-panel__results-inner knowledge-search-panel__content-column">
        <section class="knowledge-search-panel__question-block">
          <div class="knowledge-search-panel__question-label">
            {{ t("knowledgeSearch.questionLabel") }}
          </div>
          <h2 class="knowledge-search-panel__question">{{ question }}</h2>
        </section>

        <section class="knowledge-search-panel__summary">
          <div class="knowledge-search-panel__summary-head">
            <div class="knowledge-search-panel__summary-title">
              <span class="knowledge-search-panel__summary-label">
                {{ t("knowledgeSearch.summaryLabel") }}
              </span>
            </div>
            <div
              v-if="answer && !sending"
              class="knowledge-search-panel__summary-tabs"
              role="tablist"
            >
              <button
                type="button"
                class="knowledge-search-panel__summary-tab"
                :class="{ 'knowledge-search-panel__summary-tab--active': answerView === 'answer' }"
                role="tab"
                :aria-selected="answerView === 'answer'"
                @click="showAnswerView"
              >
                {{ t("knowledgeSearch.answerTab") }}
              </button>
              <button
                type="button"
                class="knowledge-search-panel__summary-tab"
                :class="{ 'knowledge-search-panel__summary-tab--active': answerView === 'mindmap' }"
                role="tab"
                :aria-selected="answerView === 'mindmap'"
                @click="showMindmapView"
              >
                {{ t("knowledgeSearch.mindmapTab") }}
              </button>
            </div>
          </div>
          <div class="knowledge-search-panel__summary-body">
            <template v-if="answerView === 'mindmap' && answer && !sending">
              <KnowledgeMindMap
                ref="mindmapRef"
                :question="question"
                :answer="answer"
              />
            </template>
            <template v-else>
              <AgentWorkflowProgress
                v-if="sending && !answer && workflow.running"
                :workflow="workflow"
                compact
              />
              <div v-else-if="sending && !answer" class="knowledge-search-panel__loading platform-inline-loading">
                <n-spin size="tiny" />
                {{ t("knowledgeSearch.thinking") }}
              </div>
              <div v-else-if="sending" class="knowledge-search-panel__streaming">
                <KnowledgeChatContent
                  :content="answer"
                  :citations="citations"
                  @open-citation="onCitationClick"
                />
                <span class="knowledge-search-panel__cursor">▍</span>
              </div>
              <KnowledgeChatContent
                v-else-if="answer"
                :content="answer"
                :citations="citations"
                @open-citation="onCitationClick"
              />
            </template>
            <ChatBubbleRetry
              v-if="answer && !sending"
              align="start"
              @retry="retryCurrentSearch"
            />
          </div>
        </section>

        <section v-if="citations.length" class="knowledge-search-panel__citations">
          <div class="knowledge-search-panel__citations-head">
            <span class="knowledge-search-panel__citations-icon" aria-hidden="true">📎</span>
            <span class="knowledge-search-panel__citations-label">
              {{ t("knowledgeSearch.citationsSection") }}
            </span>
          </div>
          <div class="knowledge-search-panel__citation-list">
            <KnowledgeCitationCard
              v-for="c in citations"
              :id="`knowledge-cite-card-${c.index}`"
              :key="`${c.index}-${c.chunk_id || c.document_id}`"
              :citation="c"
              :question="question"
            />
          </div>
        </section>

        <div v-else-if="!sending" class="knowledge-search-panel__no-cites">
          {{ t("knowledgeSearch.noCitations") }}
        </div>
        </div>
      </div>

      <div
        class="knowledge-search-panel__composer-shell knowledge-search-panel__content-column"
        :class="{ 'knowledge-search-panel__composer-shell--landing': !hasResults }"
      >
        <ChatComposer
          ref="composerRef"
          v-model="input"
          :placeholder="composerPlaceholder"
          :loading="sending"
          :disable-input-while-loading="false"
          :min-rows="composerRows.min"
          :max-rows="composerRows.max"
          @keydown="onComposerKeydown"
          @send="runSearch()"
          @stop="stopGeneration"
        />
        <div
          v-if="!hasResults && suggestions.length"
          class="knowledge-search-panel__suggestions"
        >
          <button
            v-for="s in suggestions"
            :key="s"
            type="button"
            class="knowledge-search-panel__chip"
            :disabled="sending"
            @click="useSuggestion(s)"
          >
            {{ s }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.knowledge-search-panel {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--platform-chat-gradient);
  overflow: hidden;
  --knowledge-search-content-max: 640px;
  --knowledge-search-content-gutter: 20px;
}

.knowledge-search-panel__content-column {
  width: min(
    var(--knowledge-search-content-max),
    calc(100% - var(--knowledge-search-content-gutter) * 2)
  );
  margin-inline: auto;
  padding-inline: var(--knowledge-search-content-gutter);
  box-sizing: border-box;
}

.knowledge-search-panel__body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.knowledge-search-panel__body--landing {
  justify-content: center;
  align-items: center;
  padding-bottom: min(9vh, 64px);
  overflow: auto;
}

.knowledge-search-panel__body--results {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.knowledge-search-panel__landing {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding-top: 24px;
  flex-shrink: 0;
}

.knowledge-search-panel__hero {
  text-align: center;
  max-width: 560px;
  margin-bottom: 20px;
}

.knowledge-search-panel__icon {
  width: 72px;
  height: 72px;
  margin: 0 auto 16px;
  border-radius: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--platform-accent);
  background: var(--platform-accent-gradient-soft);
  border: 1px solid var(--platform-accent-border-soft);
  box-shadow: 0 4px 16px color-mix(in srgb, var(--platform-accent) 10%, transparent);
}

.knowledge-search-panel__title {
  margin: 0 0 10px;
  font-size: 28px;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.knowledge-search-panel__sub {
  margin: 0;
  font-size: 13px;
  color: #94a3b8;
}

.knowledge-search-panel__composer-shell {
  flex-shrink: 0;
  padding-bottom: var(--knowledge-search-content-gutter);
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.knowledge-search-panel__composer-shell--landing {
  flex-shrink: 0;
  margin-top: 0;
}

.knowledge-search-panel__body--results .knowledge-search-panel__composer-shell {
  margin-top: 10px;
  padding-top: 0;
}

.knowledge-search-panel__composer-shell :deep(.chat-composer) {
  border-radius: 16px;
}

.knowledge-search-panel__suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.knowledge-search-panel__chip {
  padding: 6px 12px;
  font-size: 12px;
  color: var(--platform-accent-pressed);
  background: var(--platform-accent-muted);
  border: 1px solid var(--platform-accent-border-soft);
  border-radius: 999px;
  cursor: pointer;
  transition: background 0.15s ease;
}

.knowledge-search-panel__chip:hover:not(:disabled) {
  background: var(--platform-accent-soft);
}

.knowledge-search-panel__chip:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.knowledge-search-panel__results {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding-block: 16px var(--knowledge-search-content-gutter);
  -webkit-overflow-scrolling: touch;
  box-sizing: border-box;
}

.knowledge-search-panel__results-inner {
  display: flex;
  flex-direction: column;
  gap: var(--knowledge-search-content-gutter);
}

.knowledge-search-panel__question-block {
  padding-bottom: 4px;
  border-bottom: 1px solid var(--platform-border);
}

.knowledge-search-panel__question-label {
  margin-bottom: 8px;
}

.knowledge-search-panel__question {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  line-height: 1.5;
  color: var(--platform-text);
}

.knowledge-search-panel__question-label,
.knowledge-search-panel__summary-label,
.knowledge-search-panel__citations-label {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--platform-text-secondary);
}

.knowledge-search-panel__summary {
  flex-shrink: 0;
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
  padding: 14px 16px 16px;
  border-radius: calc(var(--platform-radius-sm) + 4px);
  border: 1px solid color-mix(in srgb, #6366f1 18%, var(--platform-border));
  background: linear-gradient(
    165deg,
    color-mix(in srgb, #6366f1 7%, var(--platform-bg-elevated)) 0%,
    var(--platform-bg-elevated) 42%,
    color-mix(in srgb, #0ea5e9 5%, var(--platform-bg-elevated)) 100%
  );
  box-shadow:
    0 1px 2px rgba(15, 23, 42, 0.05),
    0 10px 28px color-mix(in srgb, #6366f1 8%, transparent);
  position: relative;
  overflow: visible;
}

.knowledge-search-panel__summary::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  background: linear-gradient(180deg, #818cf8, #6366f1 55%, #38bdf8);
  border-radius: 4px 0 0 4px;
}

.knowledge-search-panel__summary-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.knowledge-search-panel__summary-title {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.knowledge-search-panel__summary-tabs {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--platform-bg) 70%, transparent);
  border: 1px solid color-mix(in srgb, var(--platform-border) 80%, transparent);
}

.knowledge-search-panel__summary-tab {
  border: none;
  background: transparent;
  color: var(--platform-text-secondary);
  font-size: 12px;
  font-weight: 600;
  line-height: 1;
  padding: 7px 12px;
  border-radius: 999px;
  cursor: pointer;
  transition:
    background 0.15s ease,
    color 0.15s ease;
}

.knowledge-search-panel__summary-tab:hover {
  color: var(--platform-text);
}

.knowledge-search-panel__summary-tab--active {
  color: #fff;
  background: linear-gradient(135deg, #6366f1, #4f46e5);
  box-shadow: 0 2px 8px color-mix(in srgb, #6366f1 28%, transparent);
}

.knowledge-search-panel__summary-label {
  margin-bottom: 0;
  font-size: 14px;
  text-transform: none;
  letter-spacing: 0.02em;
  color: var(--platform-text);
  font-weight: 700;
}

.knowledge-search-panel__summary-body {
  width: 100%;
  min-width: 0;
  font-size: 15px;
  line-height: 1.8;
  color: var(--platform-text);
  overflow-wrap: anywhere;
  word-break: break-word;
}

.knowledge-search-panel__summary-body :deep(.knowledge-chat-content) {
  width: 100%;
  max-width: 100%;
}

.knowledge-search-panel__summary-body :deep(.knowledge-chat-content pre),
.knowledge-search-panel__summary-body :deep(.knowledge-chat-content table) {
  max-width: 100%;
  overflow-x: auto;
}

.knowledge-search-panel__citations {
  margin-top: 4px;
  padding-top: 20px;
  border-top: 1px dashed color-mix(in srgb, var(--platform-border) 80%, transparent);
}

.knowledge-search-panel__citations-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.knowledge-search-panel__citations-icon {
  font-size: 14px;
  line-height: 1;
  opacity: 0.85;
}

.knowledge-search-panel__citations-label {
  margin-bottom: 0;
  text-transform: none;
  letter-spacing: 0.02em;
  font-size: 13px;
  color: var(--platform-text);
}

.knowledge-search-panel__loading {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  color: var(--platform-text-secondary);
}

.knowledge-search-panel__loading--failed {
  color: var(--platform-danger, #dc2626);
}

.knowledge-search-panel__streaming {
  display: block;
  width: 100%;
  min-width: 0;
}

.knowledge-search-panel__cursor {
  animation: knowledge-search-blink 1s step-end infinite;
  color: var(--platform-accent);
}

@keyframes knowledge-search-blink {
  50% {
    opacity: 0;
  }
}

.knowledge-search-panel__citation-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
  width: 100%;
  box-sizing: border-box;
}

.knowledge-search-panel__no-cites {
  font-size: 13px;
  color: var(--platform-text-secondary);
}

.knowledge-search-panel :deep(.ai-chat-textarea.n-input) {
  --n-padding-left: 16px;
  --n-padding-right: 16px;
  --n-line-height-textarea: 1.55;
  font-size: 15px;
}

.knowledge-search-panel :deep(.ai-chat-textarea .n-input__textarea-el),
.knowledge-search-panel :deep(.ai-chat-textarea .n-input__placeholder),
.knowledge-search-panel :deep(.ai-chat-textarea .n-input__textarea-mirror) {
  font-size: 15px;
  line-height: 1.55;
}
</style>
