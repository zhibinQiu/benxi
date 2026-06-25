<script setup>
import { useI18n } from "../composables/useI18n";
import { usePlatformUi } from "../composables/usePlatformUi";
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
} from "naive-ui";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import ListRefreshButton from "../components/ListRefreshButton.vue";
import ListTableFooter from "../components/ListTableFooter.vue";
import { useClientListPagination } from "../composables/useClientListPagination.js";
import {
  createCarbonAssetTrade,
  fetchCarbonAssetHoldings,
  fetchCarbonAssetMarket,
  fetchCarbonAssetOverview,
  fetchCarbonAssetTrades,
  resetCarbonAssetDemo,
} from "../api/client";

const ui = usePlatformUi();
const { t, locale } = useI18n();
const route = useRoute();
const router = useRouter();
const loading = ref(true);
const submitting = ref(false);
const overview = ref(null);
const holdings = ref([]);
const marketSnap = ref(null);
const market = computed(() => marketSnap.value?.quotes ?? []);
const trades = ref([]);

const {
  page: holdingsPage,
  pageSize: holdingsPageSize,
  total: holdingsTotal,
  pagedItems: holdingsPagedItems,
  onPageChange: onHoldingsPageChange,
} = useClientListPagination(holdings);

const {
  page: marketPage,
  pageSize: marketPageSize,
  total: marketTotal,
  pagedItems: marketPagedItems,
  onPageChange: onMarketPageChange,
} = useClientListPagination(market);

const {
  page: tradesPage,
  pageSize: tradesPageSize,
  total: tradesTotal,
  pagedItems: tradesPagedItems,
  onPageChange: onTradesPageChange,
} = useClientListPagination(trades);

const tradeForm = ref({
  side: "buy",
  asset_code: "CEA",
  quantity_tco2: 100,
  price_cny: null,
});

const dateLocale = computed(() => (locale.value === "zh" ? "zh-CN" : "en-US"));

const sideOptions = computed(() => [
  { label: t("carbonTrading.sideBuy"), value: "buy" },
  { label: t("carbonTrading.sideSell"), value: "sell" },
]);

const assetOptions = computed(() => [
  { label: t("carbonTrading.assetCea"), value: "CEA" },
  { label: t("carbonTrading.assetCcer"), value: "CCER" },
]);

function sourceLabel(row) {
  const map = {
    cneeex: t("carbonTrading.sourceCneeex"),
    custom: t("carbonTrading.sourceCustom"),
    estimated: t("carbonTrading.sourceEstimated"),
    demo: t("carbonTrading.sourceDemo"),
  };
  return map[row.source] || row.source;
}

const holdingColumns = computed(() => [
  { title: t("carbonTrading.colAsset"), key: "asset_name", ellipsis: { tooltip: true } },
  { title: t("carbonTrading.colHolding"), key: "quantity_tco2", width: 120 },
  { title: t("carbonTrading.colAvailable"), key: "available_tco2", width: 100 },
  { title: t("carbonTrading.colCost"), key: "avg_cost_cny", width: 100 },
  { title: t("carbonTrading.colMarketPrice"), key: "market_price_cny", width: 100 },
  { title: t("carbonTrading.colMarketValue"), key: "market_value_cny", width: 120 },
  {
    title: t("carbonTrading.colPnl"),
    key: "pnl_cny",
    width: 120,
    render: (row) => {
      const pos = row.pnl_cny >= 0;
      return h(
        "span",
        { style: { color: pos ? "#5b9cf5" : "#dc2626" } },
        `${pos ? "+" : ""}${row.pnl_cny} (${row.pnl_pct}%)`
      );
    },
  },
]);

const marketColumns = computed(() => [
  { title: t("carbonTrading.colVariety"), key: "asset_name", ellipsis: { tooltip: true } },
  {
    title: t("carbonTrading.colSource"),
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
  {
    title: t("carbonTrading.colTradeDate"),
    key: "trade_date",
    width: 108,
    render: (row) => row.trade_date || t("carbonTrading.emDash"),
  },
  { title: t("carbonTrading.colLastPrice"), key: "last_price_cny", width: 110 },
  {
    title: t("carbonTrading.colChangePct"),
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
  { title: t("carbonTrading.colVolume"), key: "volume_tco2", width: 110 },
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
        { default: () => t("carbonTrading.trend") }
      ),
  },
]);

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

const tradeColumns = computed(() => [
  {
    title: t("carbonTrading.colSide"),
    key: "side",
    width: 72,
    render: (row) =>
      h(
        NTag,
        { size: "small", type: row.side === "buy" ? "success" : "warning", bordered: false },
        {
          default: () =>
            row.side === "buy" ? t("carbonTrading.sideBuy") : t("carbonTrading.sideSell"),
        }
      ),
  },
  { title: t("carbonTrading.colVariety"), key: "asset_code", width: 72 },
  { title: t("carbonTrading.colQuantity"), key: "quantity_tco2", width: 100 },
  { title: t("carbonTrading.colPrice"), key: "price_cny", width: 100 },
  { title: t("carbonTrading.colAmount"), key: "amount_cny", width: 110 },
  {
    title: t("carbonTrading.colTime"),
    key: "created_at",
    ellipsis: { tooltip: true },
    render: (row) => formatTime(row.created_at),
  },
]);

function formatTime(iso) {
  if (!iso) return t("carbonTrading.emDash");
  try {
    return new Date(iso).toLocaleString(dateLocale.value, { hour12: false });
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
    const [o, h, m, tr] = await Promise.all([
      fetchCarbonAssetOverview(),
      fetchCarbonAssetHoldings(),
      fetchCarbonAssetMarket({ refresh: refreshMarket }),
      fetchCarbonAssetTrades(),
    ]);
    overview.value = o;
    holdings.value = h;
    marketSnap.value = m;
    trades.value = tr;
  } catch (e) {
    ui.error(e.message || t("carbonTrading.loadFailed"));
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
    ui.success(res.message || t("carbonTrading.tradeSuccess"));
    tradeForm.value.price_cny = null;
    await loadAll();
  } catch (e) {
    ui.error(e.message || t("carbonTrading.tradeFailed"));
  } finally {
    submitting.value = false;
  }
}

async function onResetDemo() {
  try {
    await resetCarbonAssetDemo();
    ui.success(t("carbonTrading.resetSuccess"));
    await loadAll();
  } catch (e) {
    ui.error(e.message);
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
  <FeatureSubsystemShell fill :description="t('carbonTrading.description')">
    <NSpin :show="loading">
      <NSpace vertical :size="16" class="carbon-asset-page">
        <NAlert v-if="marketSnap?.hint" type="success" :bordered="false">
          {{ marketSnap.hint }}
        </NAlert>
        <NAlert type="info" :bordered="false">
          <span v-html="t('carbonTrading.demoAlert')" />
        </NAlert>

        <NGrid v-if="overview" :cols="4" :x-gap="12" :y-gap="12" responsive="screen">
          <NGi>
            <NCard size="small" :bordered="true">
              <NStatistic :label="t('carbonTrading.statMarketValue')" tabular-nums>
                <template #prefix>¥</template>
                {{ overview.total_market_value.toLocaleString() }}
              </NStatistic>
            </NCard>
          </NGi>
          <NGi>
            <NCard size="small">
              <NStatistic :label="t('carbonTrading.statTotalQuota')" tabular-nums>
                {{ overview.total_quota_tco2.toLocaleString() }}
                <template #suffix>tCO₂e</template>
              </NStatistic>
            </NCard>
          </NGi>
          <NGi>
            <NCard size="small">
              <NStatistic :label="t('carbonTrading.statAvailable')" tabular-nums>
                {{ overview.available_quota_tco2.toLocaleString() }}
                <template #suffix>tCO₂e</template>
              </NStatistic>
            </NCard>
          </NGi>
          <NGi>
            <NCard size="small">
              <NStatistic :label="t('carbonTrading.statYtdTrades')" tabular-nums>
                {{
                  t("carbonTrading.ytdTradeFormat", {
                    count: overview.ytd_trade_count,
                    volume: overview.ytd_trade_volume_tco2,
                  })
                }}
              </NStatistic>
            </NCard>
          </NGi>
        </NGrid>

        <NTabs type="line" animated>
          <NTabPane name="holdings" :tab="t('carbonTrading.tabHoldings')">
            <div class="admin-list-table">
              <NDataTable
                :columns="holdingColumns"
                :data="holdingsPagedItems"
                :bordered="false"
                size="small"
                :pagination="false"
              />
              <ListTableFooter
                :page="holdingsPage"
                :page-size="holdingsPageSize"
                :item-count="holdingsTotal"
                @update:page="onHoldingsPageChange"
              />
            </div>
          </NTabPane>
          <NTabPane name="market" :tab="t('carbonTrading.tabMarket')">
            <NSpace align="center" justify="space-between" style="margin-bottom: 8px">
              <NText depth="3">{{ t("carbonTrading.marketHint") }}</NText>
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
                {{ t("carbonTrading.ceaHistory") }}
              </NButton>
            </NSpace>
            <div class="admin-list-table">
              <NDataTable
                :columns="marketColumns"
                :data="marketPagedItems"
                :row-props="marketRowProps"
                :bordered="false"
                size="small"
                :pagination="false"
              />
              <ListTableFooter
                :page="marketPage"
                :page-size="marketPageSize"
                :item-count="marketTotal"
                @update:page="onMarketPageChange"
              />
            </div>
          </NTabPane>
          <NTabPane name="trade" :tab="t('carbonTrading.tabTrade')">
            <NGrid :cols="2" :x-gap="16" item-responsive responsive="screen">
              <NGi span="2 m:1">
                <NCard :title="t('carbonTrading.orderTitle')" size="small">
                  <NForm label-placement="left" label-width="88">
                    <NFormItem :label="t('carbonTrading.formSide')">
                      <NSelect v-model:value="tradeForm.side" :options="sideOptions" />
                    </NFormItem>
                    <NFormItem :label="t('carbonTrading.formAsset')">
                      <NSelect v-model:value="tradeForm.asset_code" :options="assetOptions" />
                    </NFormItem>
                    <NFormItem :label="t('carbonTrading.formQuantity')">
                      <NInputNumber
                        v-model:value="tradeForm.quantity_tco2"
                        :min="0.01"
                        :step="10"
                        style="width: 100%"
                      >
                        <template #suffix>tCO₂e</template>
                      </NInputNumber>
                    </NFormItem>
                    <NFormItem :label="t('carbonTrading.formLimitPrice')">
                      <NSpace align="center">
                        <NInputNumber
                          v-model:value="tradeForm.price_cny"
                          :min="0.01"
                          :step="0.1"
                          clearable
                          :placeholder="t('carbonTrading.marketPricePlaceholder')"
                          style="width: 160px"
                        >
                          <template #suffix>¥/t</template>
                        </NInputNumber>
                        <NButton size="small" tertiary @click="fillMarketPrice">
                          {{ t("carbonTrading.fillMarketPrice") }}
                          <template v-if="selectedQuote">
                            ({{ selectedQuote.last_price_cny }})
                          </template>
                        </NButton>
                      </NSpace>
                    </NFormItem>
                    <NFormItem>
                      <NButton type="primary" :loading="submitting" @click="submitTrade">
                        {{ t("carbonTrading.submitTrade") }}
                      </NButton>
                    </NFormItem>
                  </NForm>
                </NCard>
              </NGi>
              <NGi span="2 m:1">
                <NCard :title="t('carbonTrading.recentTrades')" size="small">
                  <div class="admin-list-table">
                    <NDataTable
                      :columns="tradeColumns"
                      :data="tradesPagedItems"
                      :bordered="false"
                      size="small"
                      :max-height="280"
                      :pagination="false"
                    />
                    <ListTableFooter
                      :page="tradesPage"
                      :page-size="tradesPageSize"
                      :item-count="tradesTotal"
                      @update:page="onTradesPageChange"
                    />
                  </div>
                </NCard>
              </NGi>
            </NGrid>
          </NTabPane>
        </NTabs>

        <NSpace>
          <ListRefreshButton :label="t('carbonTrading.refresh')" @click="loadAll()" />
          <ListRefreshButton
            :label="t('carbonTrading.refreshMarket')"
            @click="loadAll({ refreshMarket: true })"
          />
          <NButton quaternary size="small" @click="onResetDemo">{{ t("carbonTrading.resetDemo") }}</NButton>
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
