<script setup>
import { computed } from "vue";
import { NIcon } from "naive-ui";
import {
  LanguageOutline,
  ChatbubblesOutline,
  GitCompareOutline,
  DocumentTextOutline,
  MicOutline,
  ScanOutline,
  StatsChartOutline,
  LeafOutline,
  SparklesOutline,
  CreateOutline,
  WalletOutline,
  NewspaperOutline,
  SearchOutline,
  GitNetworkOutline,
  CheckmarkCircleOutline,
  TrendingUpOutline,
  AnalyticsOutline,
} from "@vicons/ionicons5";
import { useAppPreferences } from "../composables/useAppPreferences";
import { messages } from "../locales";

const { locale } = useAppPreferences();

const iconMap = {
  "document-text": DocumentTextOutline,
  search: SearchOutline,
  sparkles: SparklesOutline,
  language: LanguageOutline,
  "git-compare": GitCompareOutline,
  "stats-chart": StatsChartOutline,
  analytics: AnalyticsOutline,
  "trending-up": TrendingUpOutline,
  leaf: LeafOutline,
  wallet: WalletOutline,
  mic: MicOutline,
  scan: ScanOutline,
  "git-network": GitNetworkOutline,
  create: CreateOutline,
  newspaper: NewspaperOutline,
  chatbubbles: ChatbubblesOutline,
  todos: CheckmarkCircleOutline,
};

const iconStyles = {
  "document-text": "linear-gradient(135deg, #60a5fa 0%, #2563eb 100%)",
  search: "linear-gradient(135deg, #c084fc 0%, #7c3aed 100%)",
  sparkles: "linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%)",
  language: "linear-gradient(135deg, #22d3ee 0%, #0891b2 100%)",
  "git-compare": "linear-gradient(135deg, #818cf8 0%, #4f46e5 100%)",
  "stats-chart": "linear-gradient(135deg, #34d399 0%, #059669 100%)",
  analytics: "linear-gradient(135deg, #2dd4bf 0%, #0d9488 100%)",
  "trending-up": "linear-gradient(135deg, #fb923c 0%, #ea580c 100%)",
  leaf: "linear-gradient(135deg, #4ade80 0%, #16a34a 100%)",
  wallet: "linear-gradient(135deg, #f472b6 0%, #db2777 100%)",
  mic: "linear-gradient(135deg, #a78bfa 0%, #9333ea 100%)",
  scan: "linear-gradient(135deg, #38bdf8 0%, #0284c7 100%)",
  "git-network": "linear-gradient(135deg, #e879f9 0%, #c026d3 100%)",
  create: "linear-gradient(135deg, #f87171 0%, #dc2626 100%)",
  newspaper: "linear-gradient(135deg, #94a3b8 0%, #475569 100%)",
  chatbubbles: "linear-gradient(135deg, #86efac 0%, #15803d 100%)",
  todos: "linear-gradient(135deg, #fcd34d 0%, #d97706 100%)",
};

function chunk(items, size) {
  const groups = [];
  for (let i = 0; i < items.length; i += size) {
    groups.push(items.slice(i, i + size));
  }
  return groups;
}

const cards = computed(() => {
  const list = messages[locale.value]?.login?.showcaseCards;
  return Array.isArray(list) ? list : [];
});

const panels = computed(() => chunk(cards.value, 4));

function resolveIcon(key) {
  return iconMap[key] || SparklesOutline;
}

function resolveIconStyle(key) {
  return iconStyles[key] || iconStyles.sparkles;
}
</script>

<template>
  <div v-if="panels.length" class="login-feature-ticker" aria-hidden="true">
    <div class="login-feature-ticker__fade login-feature-ticker__fade--right" />
    <div class="login-feature-ticker__viewport">
      <div class="login-feature-ticker__track">
        <div v-for="copy in 2" :key="copy" class="login-feature-ticker__set">
          <section
            v-for="(panel, panelIndex) in panels"
            :key="`${copy}-${panelIndex}`"
            class="login-feature-ticker__panel"
          >
            <article
              v-for="(card, cardIndex) in panel"
              :key="`${copy}-${panelIndex}-${cardIndex}`"
              class="login-feature-ticker__card"
            >
              <span
                class="login-feature-ticker__icon"
                :style="{ background: resolveIconStyle(card.icon) }"
              >
                <n-icon :size="16" :component="resolveIcon(card.icon)" />
              </span>
              <span class="login-feature-ticker__text">
                <span class="login-feature-ticker__card-title">{{ card.title }}</span>
                <span class="login-feature-ticker__card-desc">{{ card.desc }}</span>
              </span>
            </article>
          </section>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-feature-ticker {
  position: relative;
  width: 100%;
  margin-top: 4px;
  min-height: 0;
  pointer-events: none;
}

.login-feature-ticker__viewport {
  overflow: hidden;
  width: 100%;
  max-height: 100%;
}

.login-feature-ticker__fade {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 48px;
  z-index: 1;
  pointer-events: none;
}

.login-feature-ticker__fade--right {
  right: 0;
  background: linear-gradient(to left, var(--platform-bg, #f4f6fb) 0%, transparent 100%);
}

html[data-theme="dark"] .login-feature-ticker__fade--right {
  background: linear-gradient(to left, var(--platform-bg, #0f0f14) 0%, transparent 100%);
}

.login-feature-ticker__track {
  display: flex;
  width: max-content;
  animation: login-feature-ticker-scroll 56s linear infinite;
}

.login-feature-ticker__set {
  display: flex;
  align-items: stretch;
  gap: 12px;
  padding-right: 4px;
}

.login-feature-ticker__panel {
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
  gap: 6px;
  flex-shrink: 0;
  width: clamp(252px, 28vw, 320px);
  padding: 8px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.22);
  backdrop-filter: blur(24px) saturate(170%);
  -webkit-backdrop-filter: blur(24px) saturate(170%);
  border: 1px solid rgba(255, 255, 255, 0.38);
  box-shadow:
    0 8px 28px rgba(91, 120, 200, 0.12),
    inset 0 1px 0 rgba(255, 255, 255, 0.45);
}

html[data-theme="dark"] .login-feature-ticker__panel {
  background: rgba(22, 22, 32, 0.38);
  border-color: rgba(147, 197, 253, 0.12);
  box-shadow:
    0 8px 28px rgba(0, 0, 0, 0.28),
    inset 0 1px 0 rgba(255, 255, 255, 0.06);
}

.login-feature-ticker__card {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  min-width: 0;
  padding: 6px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.32);
  border: 1px solid rgba(255, 255, 255, 0.35);
}

html[data-theme="dark"] .login-feature-ticker__card {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.06);
}

.login-feature-ticker__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 30px;
  height: 30px;
  border-radius: 9px;
  color: #fff;
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.18);
}

.login-feature-ticker__text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.login-feature-ticker__card-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--platform-text);
  line-height: 1.35;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.login-feature-ticker__card-desc {
  font-size: 10px;
  color: var(--platform-text-secondary);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

@keyframes login-feature-ticker-scroll {
  from {
    transform: translateX(0);
  }
  to {
    transform: translateX(-50%);
  }
}

@media (prefers-reduced-motion: reduce) {
  .login-feature-ticker__track {
    animation: none;
    flex-wrap: wrap;
    gap: 10px;
    width: 100%;
  }

  .login-feature-ticker__set {
    display: contents;
  }

  .login-feature-ticker__set:last-child {
    display: none;
  }

  .login-feature-ticker__fade {
    display: none;
  }
}
</style>
