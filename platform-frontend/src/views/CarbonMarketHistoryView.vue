<script setup>
import { useI18n } from "../composables/useI18n";
import { usePlatformUi } from "../composables/usePlatformUi";
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { NButton, NCard, NSelect, NSpin, NText, NSpace } from "naive-ui";
import * as echarts from "echarts";
import { fetchCarbonAssetHistory } from "../api/client";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import { goBackToEntry } from "../utils/navigationReturn";

const route = useRoute();
const router = useRouter();
const ui = usePlatformUi();
const { t, locale } = useI18n();

const loading = ref(true);
const series = ref(null);
const chartEl = ref(null);
const days = ref(120);

const dateLocale = computed(() => (locale.value === "zh" ? "zh-CN" : "en-US"));

const assetOptions = computed(() => [
  { label: t("carbonMarketHistory.assetCea"), value: "CEA" },
  { label: t("carbonMarketHistory.assetCcer"), value: "CCER" },
]);

const dayOptions = computed(() => [
  { label: t("carbonMarketHistory.days90"), value: 90 },
  { label: t("carbonMarketHistory.days120"), value: 120 },
  { label: t("carbonMarketHistory.days180"), value: 180 },
  { label: t("carbonMarketHistory.days365"), value: 365 },
]);

const assetCode = computed(() => {
  const code = String(route.query.asset || "CEA").toUpperCase();
  return code === "CCER" ? "CCER" : "CEA";
});

function onAssetChange(code) {
  const query = { asset: code };
  if (route.query.return) query.return = route.query.return;
  router.replace({ name: "carbon-assets-history", query });
}

const pageTitle = computed(() =>
  t("carbonMarketHistory.pageTitle", {
    name: series.value?.asset_name || assetCode.value,
  })
);

const syncHint = computed(() => {
  const s = series.value;
  if (!s) return "";
  const parts = [];
  if (s.data_through) {
    parts.push(t("carbonMarketHistory.dataThrough", { date: s.data_through }));
  }
  if (s.last_synced_at) {
    try {
      const time = new Date(s.last_synced_at).toLocaleString(dateLocale.value, {
        hour12: false,
      });
      parts.push(t("carbonMarketHistory.lastSync", { time }));
    } catch {
      parts.push(t("carbonMarketHistory.lastSync", { time: s.last_synced_at }));
    }
  }
  if (assetCode.value === "CEA") {
    parts.push(t("carbonMarketHistory.ceaSyncHint"));
  }
  return parts.join(" · ");
});

let chart = null;

function disposeChart() {
  if (chart) {
    chart.dispose();
    chart = null;
  }
}

function renderChart() {
  if (!chartEl.value || !series.value?.points?.length) return;
  disposeChart();
  chart = echarts.init(chartEl.value);
  const pts = series.value.points;
  chart.setOption({
    color: ["#5b9cf5"],
    grid: { left: 48, right: 24, top: 32, bottom: 48 },
    tooltip: {
      trigger: "axis",
      valueFormatter: (v) =>
        v != null ? t("carbonMarketHistory.tooltipPrice", { value: v }) : t("carbonMarketHistory.emDash"),
    },
    xAxis: {
      type: "category",
      data: pts.map((p) => p.trade_date),
      axisLabel: { rotate: 35, fontSize: 11 },
    },
    yAxis: {
      type: "value",
      name: t("carbonMarketHistory.chartYAxis"),
      scale: true,
    },
    series: [
      {
        name: t("carbonMarketHistory.chartClosePrice"),
        type: "line",
        smooth: true,
        showSymbol: pts.length < 40,
        data: pts.map((p) => p.close_cny),
        areaStyle: { color: "rgba(91, 156, 245, 0.08)" },
      },
    ],
  });
}

async function loadHistory() {
  loading.value = true;
  series.value = null;
  disposeChart();
  try {
    series.value = await fetchCarbonAssetHistory(assetCode.value, { days: days.value });
    await nextTick();
    renderChart();
  } catch (e) {
    ui.error(e.message || t("carbonMarketHistory.loadFailed"));
  } finally {
    loading.value = false;
  }
}

function goBack() {
  goBackToEntry(router, route, { name: "carbon-assets" });
}

function handleResize() {
  chart?.resize();
}

watch([assetCode, days], () => loadHistory());

watch(locale, () => {
  if (series.value?.points?.length) renderChart();
});

onMounted(() => {
  window.addEventListener("resize", handleResize);
  loadHistory();
});
onBeforeUnmount(() => {
  window.removeEventListener("resize", handleResize);
  disposeChart();
});
</script>

<template>
  <FeatureSubsystemShell :title="pageTitle" icon="stats-chart">
    <div class="carbon-history-page">
      <NSpace align="center" justify="space-between" style="margin-bottom: 16px">
        <NButton quaternary size="small" @click="goBack">{{ t("carbonMarketHistory.back") }}</NButton>
        <NSpace align="center">
          <NSelect
            :value="assetCode"
            :options="assetOptions"
            size="small"
            style="width: 180px"
            @update:value="onAssetChange"
          />
          <NSelect
            v-model:value="days"
            size="small"
            style="width: 120px"
            :options="dayOptions"
          />
        </NSpace>
      </NSpace>

      <NCard size="small">
        <NSpin :show="loading">
          <NText v-if="series?.hint" depth="3" style="display: block; margin-bottom: 8px">
            {{ series.hint }}
          </NText>
          <NText v-if="syncHint" depth="3" style="display: block; margin-bottom: 12px">
            {{ syncHint }}
          </NText>
          <div v-if="series?.points?.length" ref="chartEl" class="history-chart" />
          <NText v-else-if="!loading" depth="3">{{ t("carbonMarketHistory.noData") }}</NText>
        </NSpin>
      </NCard>
    </div>
  </FeatureSubsystemShell>
</template>

<style scoped>
.carbon-history-page {
  width: 100%;
  max-width: 1100px;
}
.history-chart {
  width: 100%;
  height: min(480px, 62vh);
}
</style>
