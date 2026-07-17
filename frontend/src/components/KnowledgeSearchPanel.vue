<script setup>
import { computed, defineAsyncComponent, nextTick, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref } from "vue";
import { disposeRichContentInElement } from "../utils/richContentLifecycle.js";
import { NIcon } from "naive-ui";
import { SearchOutline } from "@vicons/ionicons5";
import ChatComposer from "./ChatComposer.vue";
import ChatBubbleActions from "./ChatBubbleActions.vue";
import KnowledgeChatContent from "./KnowledgeChatContent.vue";
import KnowledgeCitationCard from "./KnowledgeCitationCard.vue";
const KnowledgeMindMap = defineAsyncComponent(() => import("./KnowledgeMindMap.vue"));
import AgentWorkflowProgress from "./AgentWorkflowProgress.vue";
import { usePlatformUi } from "../composables/usePlatformUi.js";
import { useI18n } from "../composables/useI18n.js";
import { handleAgentWorkflowForNotifications } from "../composables/useNotificationAlerts.js";
import { emptyAgentWorkflow, applyAgentWorkflowEvent } from "../utils/agentWorkflow.js";
import { copyChatMessageText, shareChatMessageText } from "../utils/chatBubbleActions.js";
import { alignCitationsWithContent } from "../utils/reportCitations.js";

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
const answerCitationView = computed(() =>
  alignCitationsWithContent(answer.value, citations.value)
);
const displayCitations = computed(() => answerCitationView.value.citations);
const workflow = ref(emptyAgentWorkflow());
const answerView = ref("answer");
const citationsExpanded = ref(false);
const resultsRef = ref(null);
const composerRef = ref(null);
const mindmapRef = ref(null);
/** KeepAlive 失活时不挂载检索结果 DOM（答案/引用/思维导图） */
const resultsDomActive = ref(true);
const answerFeedback = ref(null);
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
  hasResults.value ? { min: 1, max: 6 } : { min: 3, max: 8 }
);

const displaySubtitle = computed(() => t("knowledgeSearch.subtitle"));

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
  citationsExpanded.value = false;
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
  answerFeedback.value = null;
  citations.value = [];
  workflow.value = {
    ...emptyWorkflow(),
    running: true,
    currentTitle: t("knowledgeSearch.thinking"),
  };
  answerView.value = "answer";
  citationsExpanded.value = false;
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
          handleAgentWorkflowForNotifications(ev);
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
          if (scrollTick % 4 === 0) {
            const el = resultsRef.value?.querySelector?.('.knowledge-search-panel__summary-body');
            if (el) el.scrollTop = el.scrollHeight;
          }
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

async function copyCurrentAnswer() {
  await copyChatMessageText(answer.value, { ui, t });
}

async function shareCurrentAnswer() {
  await shareChatMessageText(answer.value, {
    ui,
    t,
    title: t("knowledgeSearch.title"),
  });
}

function setAnswerFeedback(value) {
  answerFeedback.value = value;
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
  resultsDomActive.value = false;
  if (resultsRef.value) disposeRichContentInElement(resultsRef.value);
  answerView.value = "answer";
});

onActivated(() => {
  resultsDomActive.value = true;
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
              <n-icon :size="43" :component="SearchOutline" />
            </div>
            <h1 class="knowledge-search-panel__title">
              {{ t("knowledgeSearch.title") }}
            </h1>
            <p class="knowledge-search-panel__sub">{{ displaySubtitle }}</p>
          </div>
        </div>
      </Transition>

        <div v-if="hasResults && resultsDomActive" ref="resultsRef" class="knowledge-search-panel__results">
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
                v-if="sending && (workflow.running || workflow.steps.length)"
                :workflow="workflow"
                :keep-visible-after-done="sending"
                :awaiting-reply="sending && !answer"
                compact
              />
              <div
                v-else-if="sending && !answer"
                class="knowledge-search-panel__loading platform-inline-loading"
              >
                <n-spin size="tiny" />
                {{ t("knowledgeSearch.thinking") }}
              </div>
              <div v-else-if="sending && answer" class="knowledge-search-panel__streaming">
                <KnowledgeChatContent
                  :content="answerCitationView.content"
                  :citations="displayCitations"
                  @open-citation="onCitationClick"
                />
              </div>
              <KnowledgeChatContent
                v-else-if="answer"
                :content="answerCitationView.content"
                :citations="displayCitations"
                @open-citation="onCitationClick"
              />
            </template>
            <ChatBubbleActions
              v-if="answer && !sending"
              align="start"
              show-retry
              :retry-disabled="sending || !question.trim()"
              :feedback="answerFeedback"
              @copy="copyCurrentAnswer"
              @share="shareCurrentAnswer"
              @retry="retryCurrentSearch"
              @feedback="setAnswerFeedback"
            />
          </div>
        </section>

        <div v-if="displayCitations.length" class="ks-cite-fold">
          <button
            type="button"
            class="ks-cite-fold__toggle"
            @click="citationsExpanded = !citationsExpanded"
          >
            <span class="ks-cite-fold__chevron">{{ citationsExpanded ? "▾" : "▸" }}</span>
            <span class="ks-cite-fold__title">{{ t("knowledgeSearch.citationsSection") }}</span>
            <span class="ks-cite-fold__count">{{ displayCitations.length }}</span>
          </button>
          <div v-if="citationsExpanded" class="ks-cite-fold__body">
            <KnowledgeCitationCard
              v-for="c in displayCitations"
              :id="`knowledge-cite-card-${c.index}`"
              :key="`${c.index}-${c.chunk_id || c.document_id}`"
              :citation="c"
              :question="question"
            />
          </div>
        </div>

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
        >
          <template v-if="$slots.toolbar" #toolbar>
            <slot name="toolbar" />
          </template>
        </ChatComposer>
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
  --knowledge-search-content-max: 864px;
  --knowledge-search-content-gutter: 24px;
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
  padding-bottom: min(9vh, 77px);
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
  padding-top: 29px;
  flex-shrink: 0;
}

.knowledge-search-panel__hero {
  text-align: center;
  max-width: 672px;
  margin-bottom: 24px;
}

.knowledge-search-panel__icon {
  width: 86px;
  height: 86px;
  margin: 0 auto 19px;
  border-radius: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--platform-accent);
  background: var(--platform-accent-gradient-soft);
  border: 1px solid var(--platform-accent-border-soft);
  box-shadow: 0 5px 19px color-mix(in srgb, var(--platform-accent) 10%, transparent);
}

.knowledge-search-panel__title {
  margin: 0 0 12px;
  font-size: 30px;
  letter-spacing: 0.02em;
}

.knowledge-search-panel__sub {
  margin: 0;
  font-size: var(--platform-font-size-lg);
  color: #94a3b8;
}

.knowledge-search-panel__composer-shell {
  flex-shrink: 0;
  padding-bottom: var(--knowledge-search-content-gutter);
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.knowledge-search-panel__composer-shell--landing {
  flex-shrink: 0;
  margin-top: 0;
}

.knowledge-search-panel__body--results .knowledge-search-panel__composer-shell {
  margin-top: 12px;
  padding-top: 0;
}

.knowledge-search-panel__composer-shell :deep(.chat-composer) {
  border-radius: 19px;
}

.knowledge-search-panel__suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}

.knowledge-search-panel__chip {
  padding: 4px 12px;
  font-size: 11px;
  font-weight: 400;
  color: var(--platform-text-tertiary);
  background: transparent;
  border: 1px solid var(--platform-border-color-tertiary, var(--platform-bg-tertiary));
  border-radius: var(--platform-radius-pill);
  cursor: pointer;
  white-space: nowrap;
  transition:
    all var(--platform-duration-smooth, 0.2s) var(--platform-ease-smooth, ease);
}

.knowledge-search-panel__chip:hover:not(:disabled) {
  color: var(--platform-accent-pressed);
  background: var(--platform-accent-soft);
  border-color: var(--platform-accent-border);
  box-shadow: 0 2px 8px color-mix(in srgb, var(--platform-accent) 10%, transparent);
  transform: translateY(-1px);
}

.knowledge-search-panel__chip:active:not(:disabled) {
  transform: translateY(0);
  box-shadow: none;
}

.knowledge-search-panel__chip:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.knowledge-search-panel__results {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding-block: 19px var(--knowledge-search-content-gutter);
  -webkit-overflow-scrolling: touch;
  box-sizing: border-box;
}

.knowledge-search-panel__results-inner {
  display: flex;
  flex-direction: column;
  gap: var(--knowledge-search-content-gutter);
}

.knowledge-search-panel__question-block {
  padding-bottom: 5px;
  border-bottom: 1px solid var(--platform-border);
}

.knowledge-search-panel__question-label {
  margin-bottom: 10px;
}

.knowledge-search-panel__question {
  margin: 0;
  font-size: var(--platform-font-size-base);
  line-height: 1.5;
  color: var(--platform-text);
}

.knowledge-search-panel__question-label,
.knowledge-search-panel__summary-label,
.knowledge-search-panel__citations-label {
  font-size: var(--platform-font-size-sm);
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--platform-text-secondary);
}

.knowledge-search-panel__summary {
  flex-shrink: 0;
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
  padding: 0;
  border: none;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  overflow: visible;
}

.knowledge-search-panel__summary-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.knowledge-search-panel__summary-title {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.knowledge-search-panel__summary-tabs {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px;
  border-radius: 1199px;
  background: color-mix(in srgb, var(--platform-bg) 70%, transparent);
  border: 1px solid color-mix(in srgb, var(--platform-border) 80%, transparent);
}

.knowledge-search-panel__summary-tab {
  border: none;
  background: transparent;
  color: var(--platform-text-secondary);
  font-size: 12px;
  line-height: 1;
  padding: 7px 12px;
  border-radius: 1199px;
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
  background: var(--platform-accent-gradient);
  box-shadow: 0 2px 10px color-mix(in srgb, var(--platform-accent) 22%, transparent);
}

.knowledge-search-panel__summary-label {
  margin-bottom: 0;
  font-size: 12px;
  text-transform: none;
  letter-spacing: 0.02em;
  color: var(--platform-text);
}

.knowledge-search-panel__summary-body {
  width: 100%;
  min-width: 0;
  font-size: var(--platform-font-size-base);
  line-height: 1.6;
  color: var(--platform-text);
  overflow-wrap: anywhere;
  word-break: break-word;
  /* 流式/完成内容高度限制：不占满整个视口 */
  max-height: 60vh;
  overflow-y: auto;
  overscroll-behavior: contain;
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

.knowledge-search-panel__loading {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: var(--platform-font-size-sm);
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

.knowledge-search-panel__no-cites {
  font-size: var(--platform-font-size-base);
  color: var(--platform-text-secondary);
}

.knowledge-search-panel :deep(.ai-chat-textarea.n-input) {
  --n-padding-left: 19px;
  --n-padding-right: 19px;
  --n-line-height-textarea: 1.55;
  font-size: var(--platform-font-size-base);
}

.knowledge-search-panel :deep(.ai-chat-textarea .n-input__textarea-el),
.knowledge-search-panel :deep(.ai-chat-textarea .n-input__placeholder),
.knowledge-search-panel :deep(.ai-chat-textarea .n-input__textarea-mirror) {
  font-size: var(--platform-font-size-base);
  line-height: 1.55;
}

/* ── 与本析智能保持同款的径向渐变背景 ── */
.knowledge-search-panel__results {
  background:
    radial-gradient(ellipse at 20% 50%, color-mix(in srgb, var(--platform-accent) 2%, transparent) 0%, transparent 55%),
    radial-gradient(ellipse at 80% 20%, color-mix(in srgb, var(--platform-accent) 1.5%, transparent) 0%, transparent 55%);
}

/* ── 与本析智能保持同款的 Markdown 排版 ── */
.knowledge-search-panel__summary-body :deep(p) {
  margin: 0 0 0.6em;
  font-size: var(--platform-font-size-base);
  line-height: 1.7;
  color: var(--platform-text);
  font-kerning: normal;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

.knowledge-search-panel__summary-body :deep(p:last-child) {
  margin-bottom: 0;
}

.knowledge-search-panel__summary-body :deep(ul),
.knowledge-search-panel__summary-body :deep(ol) {
  margin: 0.5em 0;
  padding-left: 1.4em;
  font-size: var(--platform-font-size-base);
  line-height: 1.7;
}

.knowledge-search-panel__summary-body :deep(li) {
  margin-bottom: 0.2em;
}

.knowledge-search-panel__summary-body :deep(code) {
  font-size: 0.85em;
  padding: 2px 8px;
  border-radius: 6px;
  background: color-mix(in srgb, var(--platform-accent) 6%, transparent);
  border: 1px solid color-mix(in srgb, var(--platform-accent) 12%, transparent);
  font-family: "SF Mono", "Fira Code", "Cascadia Code", Consolas, monospace;
  font-weight: 500;
  color: color-mix(in srgb, var(--platform-accent-pressed) 80%, var(--platform-text));
}

.knowledge-search-panel__summary-body :deep(pre) {
  margin: 0.6em 0;
  padding: 16px 18px;
  border-radius: 10px;
  background: #1a1a2e;
  border: 1px solid rgba(255, 255, 255, 0.06);
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

.knowledge-search-panel__summary-body :deep(pre code) {
  padding: 0;
  background: transparent;
  border: none;
  font-weight: 400;
  color: #e4e4e7;
  font-size: 0.82em;
  line-height: 1.55;
}

.knowledge-search-panel__summary-body :deep(h1),
.knowledge-search-panel__summary-body :deep(h2),
.knowledge-search-panel__summary-body :deep(h3),
.knowledge-search-panel__summary-body :deep(h4) {
  margin: 0.8em 0 0.4em;
  font-weight: 600;
  line-height: 1.4;
  color: var(--platform-text);
}

.knowledge-search-panel__summary-body :deep(h1) { font-size: 1.25em; }
.knowledge-search-panel__summary-body :deep(h2) { font-size: 1.15em; }
.knowledge-search-panel__summary-body :deep(h3) { font-size: 1.05em; }

.knowledge-search-panel__summary-body :deep(blockquote) {
  margin: 0.5em 0;
  padding: 4px 12px;
  border-left: 3px solid var(--platform-accent);
  color: var(--platform-text-secondary);
  background: color-mix(in srgb, var(--platform-bg-tertiary) 30%, transparent);
  border-radius: 0 6px 6px 0;
}

.knowledge-search-panel__summary-body :deep(hr) {
  margin: 1em 0;
  border: none;
  border-top: 1px solid var(--platform-border);
}

.knowledge-search-panel__summary-body :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 0.6em 0;
  font-size: var(--platform-font-size-base);
}

.knowledge-search-panel__summary-body :deep(th),
.knowledge-search-panel__summary-body :deep(td) {
  padding: 8px 12px;
  border: 1px solid var(--platform-border);
  text-align: left;
}

.knowledge-search-panel__summary-body :deep(th) {
  background: color-mix(in srgb, var(--platform-bg-tertiary) 50%, transparent);
  font-weight: 600;
}

/* ── 与本析智能同款的折叠引用面板 ── */
.ks-cite-fold {
  margin: 5px 0;
  border: 1px solid var(--platform-border);
  border-radius: 8px;
  overflow: hidden;
  background: var(--platform-bg-secondary);
}

.ks-cite-fold__toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 8px 12px;
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: var(--platform-font-size-base);
  color: var(--platform-text-secondary);
  text-align: left;
  transition: background 0.15s ease;
  font-family: inherit;
}

.ks-cite-fold__toggle:hover {
  background: var(--platform-bg-tertiary);
}

.ks-cite-fold__chevron {
  font-size: var(--platform-font-size-sm);
  color: var(--platform-text-tertiary);
  flex-shrink: 0;
}

.ks-cite-fold__title {
  color: var(--platform-text-secondary);
}

.ks-cite-fold__count {
  margin-left: auto;
  font-size: var(--platform-font-size-sm);
  color: var(--platform-text-tertiary);
  background: var(--platform-bg-tertiary);
  padding: 1px 7px;
  border-radius: 1199px;
}

.ks-cite-fold__body {
  padding: 4px 12px 12px;
  border-top: 1px solid var(--platform-border);
  display: flex;
  flex-direction: column;
  gap: 17px;
}
</style>
