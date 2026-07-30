<script setup>
import { ref, computed, nextTick } from "vue";
import { HelpCircleOutline } from "@vicons/ionicons5";
import FeatureSection from "../FeatureSection.vue";
import CarbonCeaQuoteChart from "../CarbonCeaQuoteChart.vue";
import { openExternal } from "../../utils/openExternal.js";
import { fetchCarbonSettings, syncMarketQuotes } from "../../api/carbonCompliance";
import { carbonPageCache } from "../../composables/useCarbonEnterprise";
import { isRouteAbortError } from "../../api/http.js";
import { usePlatformUi } from "../../composables/usePlatformUi";
import { useI18n } from "../../composables/useI18n";

const emit = defineEmits(["settings-loaded"]);

const ui = usePlatformUi();
const { t } = useI18n();
const marketChartRef = ref(null);
const lastSyncInfo = ref("");
const marketSourceTick = ref(0);

const marketSourceLines = computed(() => {
  marketSourceTick.value;
  return marketChartRef.value?.getSourceLines?.() || [];
});

function refreshMarketSourceInfo() {
  marketSourceTick.value += 1;
}

async function refreshCharts() {
  await nextTick();
  marketChartRef.value?.resize?.();
  refreshMarketSourceInfo();
  setTimeout(() => {
    marketChartRef.value?.resize?.();
    refreshMarketSourceInfo();
  }, 150);
}

function applySyncMeta(settings) {
  const syncMeta = settings?.integrations || {};
  lastSyncInfo.value = syncMeta.last_sync_at
    ? t("carbonAssistant.lastSyncAt", { time: syncMeta.last_sync_at }) +
      (syncMeta.last_sync_ok === false ? t("carbonAssistant.lastSyncPartialFail") : "")
    : t("carbonAssistant.neverAutoSynced");
}

async function onMarketSynced() {
  try {
    const settings = await fetchCarbonSettings();
    carbonPageCache.settings = settings;
    lastSyncInfo.value = settings?.integrations?.last_sync_at
      ? t("carbonAssistant.lastSyncAt", { time: settings.integrations.last_sync_at }) +
        (settings.integrations.last_sync_ok === false ? t("carbonAssistant.lastSyncPartialFail") : "")
      : t("carbonAssistant.quotesRefreshed");
    emit("settings-loaded", settings);
  } catch {
    lastSyncInfo.value = t("carbonAssistant.quotesRefreshed");
  }
}

async function handleSyncMarket({ silent = false } = {}) {
  try {
    const data = await syncMarketQuotes();
    if (!data?.ok && !silent) {
      ui.warning(t("carbonAssistant.quotesParseFailed"));
    } else if (!silent) {
      ui.success(t("carbonAssistant.quotesUpdated"));
    }
    await onMarketSynced();
    await marketChartRef.value?.reloadLocal?.();
    await refreshCharts();
  } catch (e) {
    if (!silent && !isRouteAbortError(e)) ui.error(e?.message || t("carbonAssistant.syncFailed"));
  }
}

async function loadMarket({ autoSync = false, force = false } = {}) {
  try {
    let settings = carbonPageCache.settings;
    if (!settings || force) {
      settings = await fetchCarbonSettings();
      carbonPageCache.settings = settings;
    }
    applySyncMeta(settings);
    emit("settings-loaded", settings);
    const syncMeta = settings?.integrations || {};
    if (autoSync && !syncMeta.last_sync_at) {
      await handleSyncMarket({ silent: true });
    }
    await refreshCharts();
  } catch (e) {
    if (!isRouteAbortError(e)) ui.error(e?.message || t("carbonAssistant.loadMarketFailed"));
  }
}

defineExpose({
  loadMarket,
  refreshCharts,
  refreshMarketSourceInfo,
  resizeChart: () => marketChartRef.value?.resize?.(),
});
</script>

<template>
  <FeatureSection :title="t('carbonAssistant.marketTitle')">
    <template #extra>
      <n-popover trigger="click" placement="bottom-end" style="max-width: 320px">
        <template #trigger>
          <n-button quaternary circle size="tiny" @click.stop>
            <template #icon><n-icon :component="HelpCircleOutline" :size="14" /></template>
          </n-button>
        </template>
        <div class="cc-help-pop">
          <div class="cc-help-pop-title">{{ t("carbonAssistant.marketDataSource") }}</div>
          <p v-if="lastSyncInfo">{{ lastSyncInfo }}</p>
          <p v-else>{{ t("carbonAssistant.marketNotSynced") }}</p>
          <div v-for="(s, i) in marketSourceLines" :key="i" class="cc-help-source">
            <div>{{ s.name }}</div>
            <div class="cc-field-hint">
              <span v-if="s.queried">{{ t("carbonAssistant.marketFetched", { count: s.queried }) }}</span>
              <span v-if="s.latest != null">{{ t("carbonAssistant.marketLatest", { price: s.latest }) }}</span>
            </div>
            <n-button size="tiny" tertiary @click="openExternal(s.page)">
              {{ t("carbonAssistant.marketOpenSource") }}
            </n-button>
          </div>
          <p v-if="!marketSourceLines.length" class="cc-field-hint">
            {{ t("carbonAssistant.marketChartHint") }}
          </p>
        </div>
      </n-popover>
    </template>
    <div class="cc-charts">
      <CarbonCeaQuoteChart ref="marketChartRef" @market-synced="onMarketSynced" />
    </div>
  </FeatureSection>
</template>
