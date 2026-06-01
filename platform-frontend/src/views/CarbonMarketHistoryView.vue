<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { NButton, NCard, NSelect, NSpin, NText, NSpace, useMessage } from "naive-ui";
import * as echarts from "echarts";
import { fetchCarbonAssetHistory } from "../api/client";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import { goBackToEntry } from "../utils/navigationReturn";

const route = useRoute();
const router = useRouter();
const message = useMessage();

const loading = ref(true);
const series = ref(null);
const chartEl = ref(null);
const days = ref(120);

const assetOptions = [
  { label: "CEA 全国碳配额", value: "CEA" },
  { label: "CCER 官方", value: "CCER" },
];

const assetCode = computed(() => {
  const code = String(route.query.asset || "CEA").toUpperCase();
  return code === "CCER" ? "CCER" : "CEA";
});

function onAssetChange(code) {
  const query = { asset: code };
  if (route.query.return) query.return = route.query.return;
  router.replace({ name: "carbon-assets-history", query });
}

const pageTitle = computed(
  () => `${series.value?.asset_name || assetCode.value} · 历史走势`
);

const syncHint = computed(() => {
  const s = series.value;
  if (!s) return "";
  const parts = [];
  if (s.data_through) parts.push(`数据截至 ${s.data_through}`);
  if (s.last_synced_at) {
    try {
      const t = new Date(s.last_synced_at).toLocaleString("zh-CN", { hour12: false });
      parts.push(`最近同步 ${t}`);
    } catch {
      parts.push(`最近同步 ${s.last_synced_at}`);
    }
  }
  if (assetCode.value === "CEA") {
    parts.push("每日收盘后自动从环交所同步");
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
    color: ["#0d9488"],
    grid: { left: 48, right: 24, top: 32, bottom: 48 },
    tooltip: {
      trigger: "axis",
      valueFormatter: (v) => (v != null ? `¥${v}/t` : "—"),
    },
    xAxis: {
      type: "category",
      data: pts.map((p) => p.trade_date),
      axisLabel: { rotate: 35, fontSize: 11 },
    },
    yAxis: {
      type: "value",
      name: "收盘价 (元/吨)",
      scale: true,
    },
    series: [
      {
        name: "收盘价",
        type: "line",
        smooth: true,
        showSymbol: pts.length < 40,
        data: pts.map((p) => p.close_cny),
        areaStyle: { color: "rgba(13, 148, 136, 0.08)" },
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
    message.error(e.message || "加载历史走势失败");
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
        <NButton quaternary size="small" @click="goBack">← 返回碳资产</NButton>
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
            :options="[
              { label: '近 90 日', value: 90 },
              { label: '近 120 日', value: 120 },
              { label: '近 180 日', value: 180 },
              { label: '近 365 日', value: 365 },
            ]"
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
          <NText v-else-if="!loading" depth="3">暂无历史数据</NText>
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
