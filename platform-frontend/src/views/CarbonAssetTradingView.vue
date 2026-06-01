<script setup>
import { computed, h, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { navigateWithReturn } from "../utils/navigationReturn";
import {
  NAlert,
  NButton,
  NCard,
  NDataTable,
  NForm,
  NFormItem,
  NGi,
  NGrid,
  NInputNumber,
  NSelect,
  NSpace,
  NSpin,
  NStatistic,
  NTabPane,
  NTabs,
  NTag,
  NText,
  useMessage,
} from "naive-ui";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import {
  createCarbonAssetTrade,
  fetchCarbonAssetHoldings,
  fetchCarbonAssetMarket,
  fetchCarbonAssetOverview,
  fetchCarbonAssetTrades,
  resetCarbonAssetDemo,
} from "../api/client";

const message = useMessage();
const route = useRoute();
const router = useRouter();
const loading = ref(true);
const submitting = ref(false);
const overview = ref(null);
const holdings = ref([]);
const marketSnap = ref(null);
const market = computed(() => marketSnap.value?.quotes ?? []);
const trades = ref([]);
const tradeForm = ref({
  side: "buy",
  asset_code: "CEA",
  quantity_tco2: 100,
  price_cny: null,
});

const sideOptions = [
  { label: "买入", value: "buy" },
  { label: "卖出", value: "sell" },
];
const assetOptions = [
  { label: "CEA 全国碳配额", value: "CEA" },
  { label: "CCER", value: "CCER" },
];

const holdingColumns = [
  { title: "资产", key: "asset_name", ellipsis: { tooltip: true } },
  { title: "持仓 (tCO₂e)", key: "quantity_tco2", width: 120 },
  { title: "可用", key: "available_tco2", width: 100 },
  { title: "成本 (¥/t)", key: "avg_cost_cny", width: 100 },
  { title: "市价 (¥/t)", key: "market_price_cny", width: 100 },
  { title: "市值 (¥)", key: "market_value_cny", width: 120 },
  {
    title: "浮动盈亏",
    key: "pnl_cny",
    width: 120,
    render: (row) => {
      const pos = row.pnl_cny >= 0;
      return h(
        "span",
        { style: { color: pos ? "#0d9488" : "#dc2626" } },
        `${pos ? "+" : ""}${row.pnl_cny} (${row.pnl_pct}%)`
      );
    },
  },
];

function sourceLabel(row) {
  const map = {
    cneeex: "上证环交所",
    custom: "自定义",
    estimated: "参考估算",
    demo: "演示",
  };
  return map[row.source] || row.source;
}

const marketColumns = [
  { title: "品种", key: "asset_name", ellipsis: { tooltip: true } },
  {
    title: "来源",
    key: "source",
    width: 100,
    render: (row) =>
      h(
        NTag,
        {
          size: "small",
          type: row.live ? "success" : row.source === "estimated" ? "warning" : "default",
          bordered: false,
        },
        { default: () => sourceLabel(row) }
      ),
  },
  { title: "交易日", key: "trade_date", width: 108, render: (row) => row.trade_date || "—" },
  { title: "最新价 (¥/t)", key: "last_price_cny", width: 110 },
  {
    title: "涨跌幅",
    key: "change_pct",
    width: 90,
    render: (row) => {
      const pos = row.change_pct >= 0;
      return h(
        NTag,
        { size: "small", type: pos ? "success" : "error", bordered: false },
        { default: () => `${pos ? "+" : ""}${row.change_pct}%` }
      );
    },
  },
  { title: "成交量 (t)", key: "volume_tco2", width: 110 },
  {
    title: "",
    key: "history",
    width: 88,
    render: (row) =>
      h(
        NButton,
        {
          size: "tiny",
          tertiary: true,
          type: "primary",
          onClick: (e) => {
            e.stopPropagation();
            openHistory(row);
          },
        },
        { default: () => "走势" }
      ),
  },
];

function openHistory(row) {
  if (row.asset_code === "CEA" || row.asset_code === "CCER") {
    navigateWithReturn(
      router,
      {
        name: "carbon-assets-history",
        query: { asset: row.asset_code },
      },
      route
    );
  }
}

function marketRowProps(row) {
  return {
    style: "cursor: pointer",
    onClick: () => openHistory(row),
  };
}

const tradeColumns = [
  {
    title: "方向",
    key: "side",
    width: 72,
    render: (row) =>
      h(
        NTag,
        { size: "small", type: row.side === "buy" ? "success" : "warning", bordered: false },
        { default: () => (row.side === "buy" ? "买入" : "卖出") }
      ),
  },
  { title: "品种", key: "asset_code", width: 72 },
  { title: "数量 (t)", key: "quantity_tco2", width: 100 },
  { title: "价格 (¥/t)", key: "price_cny", width: 100 },
  { title: "金额 (¥)", key: "amount_cny", width: 110 },
  {
    title: "时间",
    key: "created_at",
    ellipsis: { tooltip: true },
    render: (row) => formatTime(row.created_at),
  },
];

function formatTime(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("zh-CN", { hour12: false });
  } catch {
    return iso;
  }
}

const selectedQuote = computed(() =>
  market.value.find((m) => m.asset_code === tradeForm.value.asset_code)
);

async function loadAll({ refreshMarket = false } = {}) {
  loading.value = true;
  try {
    const [o, h, m, t] = await Promise.all([
      fetchCarbonAssetOverview(),
      fetchCarbonAssetHoldings(),
      fetchCarbonAssetMarket({ refresh: refreshMarket }),
      fetchCarbonAssetTrades(),
    ]);
    overview.value = o;
    holdings.value = h;
    marketSnap.value = m;
    trades.value = t;
  } catch (e) {
    message.error(e.message || "加载失败");
  } finally {
    loading.value = false;
  }
}

async function submitTrade() {
  submitting.value = true;
  try {
    const payload = {
      side: tradeForm.value.side,
      asset_code: tradeForm.value.asset_code,
      quantity_tco2: tradeForm.value.quantity_tco2,
    };
    if (tradeForm.value.price_cny) payload.price_cny = tradeForm.value.price_cny;
    const res = await createCarbonAssetTrade(payload);
    message.success(res.message || "成交成功");
    tradeForm.value.price_cny = null;
    await loadAll();
  } catch (e) {
    message.error(e.message || "下单失败");
  } finally {
    submitting.value = false;
  }
}

async function onResetDemo() {
  try {
    await resetCarbonAssetDemo();
    message.success("已恢复演示初始数据");
    await loadAll();
  } catch (e) {
    message.error(e.message);
  }
}

function fillMarketPrice() {
  if (selectedQuote.value) {
    tradeForm.value.price_cny = selectedQuote.value.last_price_cny;
  }
}

onMounted(loadAll);
</script>

<template>
  <FeatureSubsystemShell
    fill
    description="碳配额与 CCER 持仓管理、行情查看与模拟交易（演示数据，非真实市场对接）。"
  >
    <NSpin :show="loading">
      <NSpace vertical :size="16" class="carbon-asset-page">
        <NAlert v-if="marketSnap?.hint" type="success" :bordered="false">
          {{ marketSnap.hint }}
        </NAlert>
        <NAlert type="info" :bordered="false">
          持仓与成交为<strong>演示数据</strong>（内存）；CEA 行情在可访问上海环交所时自动更新，CCER
          可能为估算或演示价。点击「刷新行情」可强制重新抓取。
        </NAlert>

        <NGrid v-if="overview" :cols="4" :x-gap="12" :y-gap="12" responsive="screen">
          <NGi>
            <NCard size="small" :bordered="true">
              <NStatistic label="持仓市值" tabular-nums>
                <template #prefix>¥</template>
                {{ overview.total_market_value.toLocaleString() }}
              </NStatistic>
            </NCard>
          </NGi>
          <NGi>
            <NCard size="small">
              <NStatistic label="碳资产总量" tabular-nums>
                {{ overview.total_quota_tco2.toLocaleString() }}
                <template #suffix>tCO₂e</template>
              </NStatistic>
            </NCard>
          </NGi>
          <NGi>
            <NCard size="small">
              <NStatistic label="可交易余额" tabular-nums>
                {{ overview.available_quota_tco2.toLocaleString() }}
                <template #suffix>tCO₂e</template>
              </NStatistic>
            </NCard>
          </NGi>
          <NGi>
            <NCard size="small">
              <NStatistic label="本年模拟成交" tabular-nums>
                {{ overview.ytd_trade_count }} 笔 / {{ overview.ytd_trade_volume_tco2 }} t
              </NStatistic>
            </NCard>
          </NGi>
        </NGrid>

        <NTabs type="line" animated>
          <NTabPane name="holdings" tab="资产持仓">
            <NDataTable
              :columns="holdingColumns"
              :data="holdings"
              :bordered="false"
              size="small"
              :pagination="false"
            />
          </NTabPane>
          <NTabPane name="market" tab="市场行情">
            <NSpace align="center" justify="space-between" style="margin-bottom: 8px">
              <NText depth="3">
                点击行或「走势」进入历史走势页（CEA 存库每日同步，CCER 为估算）
              </NText>
              <NButton
                size="tiny"
                type="primary"
                tertiary
                @click="
                  navigateWithReturn(
                    router,
                    { name: 'carbon-assets-history', query: { asset: 'CEA' } },
                    route
                  )
                "
              >
                CEA 历史走势
              </NButton>
            </NSpace>
            <NDataTable
              :columns="marketColumns"
              :data="market"
              :row-props="marketRowProps"
              :bordered="false"
              size="small"
              :pagination="false"
            />
          </NTabPane>
          <NTabPane name="trade" tab="模拟交易">
            <NGrid :cols="2" :x-gap="16" item-responsive responsive="screen">
              <NGi span="2 m:1">
                <NCard title="下单" size="small">
                  <NForm label-placement="left" label-width="88">
                    <NFormItem label="方向">
                      <NSelect v-model:value="tradeForm.side" :options="sideOptions" />
                    </NFormItem>
                    <NFormItem label="品种">
                      <NSelect v-model:value="tradeForm.asset_code" :options="assetOptions" />
                    </NFormItem>
                    <NFormItem label="数量">
                      <NInputNumber
                        v-model:value="tradeForm.quantity_tco2"
                        :min="0.01"
                        :step="10"
                        style="width: 100%"
                      >
                        <template #suffix>tCO₂e</template>
                      </NInputNumber>
                    </NFormItem>
                    <NFormItem label="限价">
                      <NSpace align="center">
                        <NInputNumber
                          v-model:value="tradeForm.price_cny"
                          :min="0.01"
                          :step="0.1"
                          clearable
                          placeholder="市价"
                          style="width: 160px"
                        >
                          <template #suffix>¥/t</template>
                        </NInputNumber>
                        <NButton size="small" tertiary @click="fillMarketPrice">
                          填入市价
                          <template v-if="selectedQuote">
                            ({{ selectedQuote.last_price_cny }})
                          </template>
                        </NButton>
                      </NSpace>
                    </NFormItem>
                    <NFormItem>
                      <NButton type="primary" :loading="submitting" @click="submitTrade">
                        提交模拟成交
                      </NButton>
                    </NFormItem>
                  </NForm>
                </NCard>
              </NGi>
              <NGi span="2 m:1">
                <NCard title="最近成交" size="small">
                  <NDataTable
                    :columns="tradeColumns"
                    :data="trades"
                    :bordered="false"
                    size="small"
                    :max-height="280"
                    :pagination="false"
                  />
                </NCard>
              </NGi>
            </NGrid>
          </NTabPane>
        </NTabs>

        <NSpace>
          <NButton quaternary size="small" @click="loadAll()">刷新</NButton>
          <NButton quaternary size="small" @click="loadAll({ refreshMarket: true })">
            刷新行情
          </NButton>
          <NButton quaternary size="small" @click="onResetDemo">重置演示</NButton>
        </NSpace>
      </NSpace>
    </NSpin>
  </FeatureSubsystemShell>
</template>

<style scoped>
.carbon-asset-page {
  width: 100%;
  max-width: 1200px;
}
</style>
