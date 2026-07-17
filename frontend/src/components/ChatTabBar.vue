<script setup>
import { ref, onMounted, onUnmounted } from "vue";
import { CloseOutline, AddOutline, TimeOutline, CheckmarkOutline, CloseCircleOutline } from "@vicons/ionicons5";
import { NIcon } from "naive-ui";
import { useI18n } from "../composables/useI18n.js";
import CurveAnimation from "./CurveAnimation.vue";

const props = defineProps({
  tabs: { type: Array, required: true },
  activeTabId: { type: String, required: true },
  canCreateTab: { type: Boolean, default: true },
  tabCount: { type: Number, default: 0 },
  /** { [tabId]: boolean } */
  tabStreaming: { type: Object, default: () => ({}) },
  /** { [tabId]: boolean } */
  tabHasContent: { type: Object, default: () => ({}) },
  /** 操作栏介绍性文字，tab 过多侵占空间时自动隐藏 */
  introText: { type: String, default: "" },
});

const emit = defineEmits(["switch", "close", "create", "history", "closeAll"]);

const { t } = useI18n();

const scrollRef = ref(null);
const isOverflow = ref(false);

let resizeObserver = null;

function checkOverflow() {
  const el = scrollRef.value;
  if (el) {
    isOverflow.value = el.scrollWidth > el.clientWidth;
  }
}

onMounted(() => {
  checkOverflow();
  if (scrollRef.value) {
    resizeObserver = new ResizeObserver(checkOverflow);
    resizeObserver.observe(scrollRef.value);
  }
});

onUnmounted(() => {
  if (resizeObserver) {
    resizeObserver.disconnect();
    resizeObserver = null;
  }
});
</script>

<template>
  <div class="chat-tab-bar">
    <div ref="scrollRef" class="chat-tab-bar__scroll">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        type="button"
        class="chat-tab"
        :class="{
          'chat-tab--active': tab.id === activeTabId,
          'chat-tab--streaming': tabStreaming[tab.id],
          'chat-tab--done': !tabStreaming[tab.id] && tabHasContent[tab.id],
        }"
        :title="tab.title || t('chat.newChat')"
        @click="emit('switch', tab.id)"
      >
        <span v-if="tabStreaming[tab.id]" class="chat-tab__spinner" aria-hidden="true">
          <CurveAnimation preset="rose-three" :size="16" inline rotate label="" />
        </span>
        <span v-else-if="tabHasContent[tab.id]" class="chat-tab__check" aria-hidden="true">
          <n-icon :size="10" :component="CheckmarkOutline" />
        </span>
        <span class="chat-tab__title">{{ tab.title || t("chat.newChat") }}</span>
        <button
          v-if="tabs.length > 1"
          type="button"
          class="chat-tab__close"
          :aria-label="t('chat.closeTab')"
          @click.stop="emit('close', tab.id)"
        >
          <n-icon :size="12" :component="CloseOutline" />
        </button>
      </button>
      <!-- 新建对话按钮：仅加号 -->
      <button
        type="button"
        class="chat-tab chat-tab--new"
        :disabled="!canCreateTab"
        :aria-label="t('chat.newChat')"
        :title="t('chat.newChat')"
        @click="emit('create')"
      >
        <n-icon :size="16" :component="AddOutline" />
      </button>
    </div>
    <div class="chat-tab-bar__actions">
      <button
        v-if="tabs.length > 1"
        type="button"
        class="chat-tab-action"
        :aria-label="t('chat.closeAllTabs')"
        :title="t('chat.closeAllTabs')"
        @click="emit('closeAll')"
      >
        <n-icon :size="16" :component="CloseCircleOutline" />
      </button>
      <span v-if="introText && !isOverflow" class="chat-tab-bar__intro">{{ introText }}</span>
      <button
        type="button"
        class="chat-tab-action"
        :aria-label="t('chat.viewHistory')"
        :title="t('chat.viewHistory')"
        @click="emit('history')"
      >
        <n-icon :size="16" :component="TimeOutline" />
      </button>
    </div>
  </div>
</template>

<style scoped>
.chat-tab-bar {
  display: flex;
  align-items: stretch;
  width: 100%;
  min-width: 0;
  border-bottom: 1px solid var(--platform-border);
}

.chat-tab-bar__scroll {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: stretch;
  gap: 0;
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.chat-tab-bar__scroll::-webkit-scrollbar {
  display: none;
}

/* --- 扁平矩形标签：无圆角，等宽 1/7 --- */
.chat-tab {
  all: unset;
  box-sizing: border-box;
  flex: 0 0 calc(100% / 7);
  max-width: calc(100% / 7);
  min-width: 0;
  height: 28px;
  display: inline-flex;
  align-items: center;
  gap: 0;
  padding: 0 6px 0 10px;
  border-right: 1px solid var(--platform-border);
  background: var(--platform-bg-secondary);
  color: var(--platform-text-tertiary);
  font-size: 11px;
  font-family: inherit;
  line-height: 1;
  cursor: pointer;
  transition: background var(--platform-duration-smooth) ease, color var(--platform-duration-smooth) ease;
  white-space: nowrap;
  position: relative;
  border-radius: 0;
  -webkit-appearance: none;
  appearance: none;
}

/* 活跃标签左侧相邻的标签不需要右侧分隔线 */
.chat-tab:has(+ .chat-tab--active) {
  border-right: none;
}

.chat-tab:hover {
  background: var(--platform-bg-tertiary);
  color: var(--platform-text);
}

/* --- 活跃标签：白色背景，左侧 accent 竖线指示器 --- */
.chat-tab--active {
  background: var(--platform-bg-elevated);
  color: var(--platform-text);
  font-weight: 500;
  border-right: none;
  border-radius: 0;
  z-index: 1;
}

/* 活跃标签左侧 accent 竖线指示器 */
.chat-tab--active::before {
  content: "";
  position: absolute;
  left: 0;
  top: 3px;
  bottom: 3px;
  width: 2.5px;
  border-radius: 1px;
  background: var(--platform-accent);
}

.chat-tab--active:hover {
  background: var(--platform-bg-elevated);
}

/* --- 已完成标签 --- */
.chat-tab--done {
  color: var(--platform-text-secondary);
}

/* --- 新建对话按钮：仅加号，不参与等分 --- */
.chat-tab--new {
  all: unset;
  box-sizing: border-box;
  flex: none;
  width: 36px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0;
  padding: 0;
  background: transparent;
  color: var(--platform-text-tertiary);
  font-size: 12px;
  font-family: inherit;
  line-height: 1;
  cursor: pointer;
  white-space: nowrap;
  border-radius: 0;
  -webkit-appearance: none;
  appearance: none;
}

.chat-tab--new:hover:not(:disabled) {
  background: var(--platform-bg-secondary);
  color: var(--platform-accent);
}

.chat-tab--new:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.chat-tab__title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
  flex: 1;
}

/* --- 流式加载动画 --- */
.chat-tab__spinner {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  margin-right: 4px;
  line-height: 0;
}

/* --- 已完成对号 --- */
.chat-tab__check {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 10px;
  height: 10px;
  margin-right: 3px;
  color: var(--platform-accent);
}

/* --- 关闭按钮 --- */
.chat-tab__close {
  all: unset;
  box-sizing: border-box;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  margin-left: 4px;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--platform-text-tertiary);
  cursor: pointer;
  opacity: 0;
  transition: opacity var(--platform-duration-smooth) ease, background var(--platform-duration-smooth) ease, color var(--platform-duration-smooth) ease;
  -webkit-appearance: none;
  appearance: none;
}

.chat-tab:hover .chat-tab__close,
.chat-tab--active .chat-tab__close {
  opacity: 1;
}

.chat-tab__close:hover {
  background: var(--platform-bg-tertiary);
  color: var(--platform-text-secondary);
}

/* --- 操作栏介绍文字 --- */
.chat-tab-bar__intro {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  height: 28px;
  font-size: 11px;
  color: var(--platform-text-tertiary);
  line-height: 1;
  white-space: nowrap;
  padding: 0 8px;
  user-select: none;
}

/* --- 右侧操作区 --- */
.chat-tab-bar__actions {
  flex-shrink: 0;
  display: flex;
  align-items: center;
}

.chat-tab-action {
  all: unset;
  box-sizing: border-box;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 28px;
  background: transparent;
  color: var(--platform-text-tertiary);
  cursor: pointer;
  transition: background var(--platform-duration-smooth) ease, color var(--platform-duration-smooth) ease;
  -webkit-appearance: none;
  appearance: none;
}

.chat-tab-action:hover:not(:disabled) {
  border-radius: 50%;
  background: var(--platform-bg-secondary);
  color: var(--platform-accent);
}

.chat-tab-action:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
