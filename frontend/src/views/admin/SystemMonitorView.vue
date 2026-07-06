<script setup>
import { usePlatformUi } from "../../composables/usePlatformUi";
import { useI18n } from "../../composables/useI18n";
import { computed, h, onMounted, ref } from "vue";
import {
  DocumentTextOutline,
  CloudUploadOutline,
  GridOutline,
  ConstructOutline,
  PeopleOutline,
  RadioOutline } from "@vicons/ionicons5";
import {
  NCard,
  NGrid,
  NGi,
  NStatistic,
  NProgress,
  NDataTable,
  NSpace,
  NEmpty,
  NTag,
  NIcon } from "naive-ui";
import { fetchAuditLogs, fetchDashboardStats, fetchSystemMetrics } from "../../api/client";
import { sanitizeUserFacingMessage } from "../../utils/uiMessage.js";
import ListRefreshButton from "../../components/ListRefreshButton.vue";
import ListTableFooter from "../../components/ListTableFooter.vue";
import { useClientListPagination } from "../../composables/useClientListPagination.js";

const ui = usePlatformUi();
const { t } = useI18n();
const loadingLogs = ref(false);
const loadingMetrics = ref(false);
const loadingStats = ref(false);
const logs = ref([]);
const metrics = ref(null);
const stats = ref(null);

const CARD_KEYS = [
  "documents_total",
  "documents_indexed",
  "features_total",
  "features_pending",
  "users_registered",
  "users_online",
];

const CARD_ICONS = {
  documents_total: DocumentTextOutline,
  documents_indexed: CloudUploadOutline,
  features_total: GridOutline,
  features_pending: ConstructOutline,
  users_registered: PeopleOutline,
  users_online: RadioOutline,
};

const CARD_ACCENTS = {
  documents_total: "#5b9cf5",
  documents_indexed: "#34d399",
  features_total: "var(--platform-accent)",
  features_pending: "#fbbf24",
  users_registered: "#60a5fa",
  users_online: "#f472b6",
};

const CARD_I18N_KEYS = {
  documents_total: "documentsTotal",
  documents_indexed: "documentsIndexed",
  features_total: "featuresTotal",
  features_pending: "featuresPending",
  users_registered: "usersRegistered",
  users_online: "usersOnline",
};

function formatQueueError(message) {
  return sanitizeUserFacingMessage(message, "知识库队列指标暂不可用");
}

function formatBytes(n) {
  if (n == null || Number.isNaN(n)) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = Number(n);
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function formatNumber(n) {
  if (n == null || Number.isNaN(n)) return "—";
  return Number(n).toLocaleString();
}

function formatUptime(sec) {
  if (!sec) return "—";
  const d = Math.floor(sec / 86400);
  const hr = Math.floor((sec % 86400) / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (d > 0) return t("admin.monitor.uptimeDays", { days: d, hours: hr });
  if (hr > 0) return t("admin.monitor.uptimeHours", { hours: hr, minutes: m });
  return t("admin.monitor.uptimeMinutes", { minutes: m });
}

function formatTime(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function formatUnixTime(ts) {
  if (!ts) return "—";
  try {
    return new Date(ts * 1000).toLocaleString();
  } catch {
    return "—";
  }
}

const overviewCards = computed(() => {
  const s = stats.value;
  if (!s) return [];
  return CARD_KEYS.map((key) => {
    const i18nKey = CARD_I18N_KEYS[key];
    return {
      key,
      label: t(`admin.monitor.cards.${i18nKey}.label`),
      hint: t(`admin.monitor.cards.${i18nKey}.hint`),
      value: s[key],
      names: key === "users_online" ? s.users_online_names || [] : [],
      icon: CARD_ICONS[key],
      accent: CARD_ACCENTS[key],
    };
  });
});

const logColumns = computed(() => [
  {
    title: t("admin.monitor.logTime"),
    key: "created_at",
    width: 204,
    render: (r) => formatTime(r.created_at),
  },
  {
    title: t("admin.monitor.logUser"),
    key: "username",
    width: 120,
    render: (r) => r.username || "—",
  },
  { title: t("admin.monitor.logAction"), key: "action", minWidth: 192, ellipsis: { tooltip: true } },
  { title: "IP", key: "ip_address", width: 144, render: (r) => r.ip_address || "—" },
]);

const gpuRows = computed(() => metrics.value?.gpus || []);

const {
  page: gpuPage,
  pageSize: gpuPageSize,
  total: gpuTotal,
  pagedItems: gpuPagedItems,
  onPageChange: onGpuPageChange,
} = useClientListPagination(gpuRows);

const {
  page: logsPage,
  pageSize: logsPageSize,
  total: logsTotal,
  pagedItems: logsPagedItems,
  onPageChange: onLogsPageChange,
} = useClientListPagination(logs);

const gpuColumns = computed(() => [
  { title: "GPU", key: "index", width: 72, render: (r) => `#${r.index}` },
  { title: t("admin.monitor.gpuModel"), key: "name", ellipsis: { tooltip: true } },
  {
    title: t("admin.monitor.gpuVram"),
    key: "vram",
    width: 288,
    render(row) {
      const pct =
        row.memory_total_mb > 0
          ? Math.round((row.memory_used_mb / row.memory_total_mb) * 100)
          : 0;
      return h("div", { class: "gpu-vram-cell" }, [
        h("span", null, `${row.memory_used_mb.toFixed(0)} / ${row.memory_total_mb.toFixed(0)} MB`),
        h(NProgress, {
          type: "line",
          percentage: pct,
          showIndicator: false,
          height: 6,
          style: "margin-top: 4px"}),
      ]);
    }},
  {
    title: t("admin.monitor.gpuUtilization"),
    key: "utilization_percent",
    width: 108,
    render: (r) => (r.utilization_percent != null ? `${r.utilization_percent}%` : "—")},
]);

const knowflowQueue = computed(() => metrics.value?.knowflow_queue || null);

const knowflowQueueStuck = computed(() => Boolean(knowflowQueue.value?.stuck));

const refreshing = computed(
  () => loadingLogs.value || loadingMetrics.value || loadingStats.value
);

async function loadLogs() {
  loadingLogs.value = true;
  try {
    logs.value = await fetchAuditLogs(200);
  } catch (e) {
    ui.error(e.message);
  } finally {
    loadingLogs.value = false;
  }
}

async function loadMetrics() {
  loadingMetrics.value = true;
  try {
    metrics.value = await fetchSystemMetrics();
  } catch (e) {
    ui.error(e.message);
  } finally {
    loadingMetrics.value = false;
  }
}

async function loadStats() {
  loadingStats.value = true;
  try {
    stats.value = await fetchDashboardStats();
  } catch (e) {
    ui.error(e.message);
  } finally {
    loadingStats.value = false;
  }
}

async function refreshAll() {
  await Promise.all([loadStats(), loadMetrics(), loadLogs()]);
}

onMounted(() => {
  void refreshAll();
});
</script>

<template>
  <div class="monitor-page">
    <div class="monitor-page__toolbar">
      <span v-if="stats" class="metric-hint">
        {{ t("admin.monitor.dataUpdatedAt", { time: formatUnixTime(stats.collected_at) }) }}
      </span>
      <n-space :size="10">
        <ListRefreshButton
          :label="t('admin.monitor.refreshLogs')"
          :loading="loadingLogs"
          @click="loadLogs"
        />
        <ListRefreshButton
          :label="t('admin.monitor.refreshAll')"
          :loading="refreshing"
          @click="refreshAll"
        />
      </n-space>
    </div>

    <n-card class="monitor-section" :bordered="false">
      <div v-if="overviewCards.length" class="overview-grid">
        <article
          v-for="card in overviewCards"
          :key="card.key"
          class="overview-card"
          :style="{ '--card-accent': card.accent }"
        >
          <div class="overview-card__icon">
            <n-icon :size="26" :component="card.icon" />
          </div>
          <div class="overview-card__body">
            <div class="overview-card__label">{{ card.label }}</div>
            <div class="overview-card__value">{{ formatNumber(card.value) }}</div>
            <div v-if="card.names.length" class="overview-card__names">
              <n-tag
                v-for="(name, index) in card.names"
                :key="`${name}-${index}`"
                size="small"
                :bordered="false"
              >
                {{ name }}
              </n-tag>
            </div>
            <div class="overview-card__hint">{{ card.hint }}</div>
          </div>
        </article>
      </div>
      <n-empty v-else :description="t('admin.monitor.noStats')" size="small" />
    </n-card>

    <n-card class="monitor-section" :bordered="false">
      <template v-if="metrics">
        <n-grid :cols="4" :x-gap="16" :y-gap="16" responsive="screen" item-responsive>
          <n-gi span="4 m:2 l:1">
            <n-statistic :label="t('admin.monitor.cpuUsage')">
              <template #default>{{ metrics.cpu.percent?.toFixed(1) }}%</template>
            </n-statistic>
            <n-progress
              type="line"
              :percentage="Math.min(100, metrics.cpu.percent || 0)"
              :show-indicator="false"
              style="margin-top: 10px"
            />
            <div class="metric-hint">
              {{
                t("admin.monitor.physicalCores", {
                  physical: metrics.cpu.count_physical || "—",
                  logical: metrics.cpu.count_logical || "—",
                })
              }}
            </div>
          </n-gi>
          <n-gi span="4 m:2 l:1">
            <n-statistic :label="t('admin.monitor.memory')">
              <template #default>{{ metrics.memory.percent?.toFixed(1) }}%</template>
            </n-statistic>
            <n-progress
              type="line"
              :percentage="Math.min(100, metrics.memory.percent || 0)"
              :show-indicator="false"
              status="info"
              style="margin-top: 10px"
            />
            <div class="metric-hint">
              {{ formatBytes(metrics.memory.used_bytes) }} /
              {{ formatBytes(metrics.memory.total_bytes) }}
            </div>
          </n-gi>
          <n-gi span="4 m:2 l:1">
            <n-statistic :label="t('admin.monitor.disk')">
              <template #default>{{ metrics.disk.percent?.toFixed(1) }}%</template>
            </n-statistic>
            <n-progress
              type="line"
              :percentage="Math.min(100, metrics.disk.percent || 0)"
              :show-indicator="false"
              status="warning"
              style="margin-top: 10px"
            />
            <div class="metric-hint">
              {{ formatBytes(metrics.disk.used_bytes) }} /
              {{ formatBytes(metrics.disk.total_bytes) }}
            </div>
          </n-gi>
          <n-gi span="4 m:2 l:1">
            <n-statistic :label="t('admin.monitor.uptime')">
              <template #default>{{ formatUptime(metrics.uptime_seconds) }}</template>
            </n-statistic>
            <div class="metric-hint">{{ metrics.hostname }}</div>
            <div class="metric-hint">v{{ metrics.app_version }}</div>
          </n-gi>
        </n-grid>
        <div class="meta-row">
          <n-tag size="small" :bordered="false">{{ metrics.platform }}</n-tag>
          <n-tag size="small" :bordered="false">Python {{ metrics.python_version }}</n-tag>
          <span v-if="metrics.cpu.load_avg" class="metric-hint">
            {{
              t("admin.monitor.loadAvg", {
                values: metrics.cpu.load_avg.map((x) => x.toFixed(2)).join(" / "),
              })
            }}
          </span>
          <span class="metric-hint">
            {{
              t("admin.monitor.swap", {
                used: formatBytes(metrics.swap.used_bytes),
                total: formatBytes(metrics.swap.total_bytes),
              })
            }}
          </span>
        </div>
        <div v-if="metrics.knowflow_queue" class="knowflow-queue-section">
          <div class="section-title">{{ t("admin.monitor.knowflowQueueTitle") }}</div>
          <div
            v-if="metrics.knowflow_queue.error"
            class="metric-hint metric-hint--warn knowflow-queue-section__error"
          >
            {{ formatQueueError(metrics.knowflow_queue.error) }}
          </div>
          <div class="knowflow-queue-status">
            <n-tag
              size="medium"
              :type="
                !metrics.knowflow_queue.available
                  ? 'default'
                  : knowflowQueueStuck
                    ? 'warning'
                    : 'success'
              "
              :bordered="false"
            >
              {{
                !metrics.knowflow_queue.available
                  ? t("admin.monitor.knowflowQueueUnknown")
                  : knowflowQueueStuck
                    ? t("admin.monitor.knowflowQueueStuck")
                    : t("admin.monitor.knowflowQueueHealthy")
              }}
            </n-tag>
            <p class="knowflow-queue-status__hint metric-hint">
              {{
                knowflowQueueStuck
                  ? t("admin.monitor.knowflowQueueStuckDetail", {
                      pending: metrics.knowflow_queue.pending_tasks || 0,
                      lag: metrics.knowflow_queue.queue_lag || 0,
                    })
                  : metrics.knowflow_queue.watchdog_enabled
                    ? t("admin.monitor.knowflowWatchdogHint", {
                        minutes: metrics.knowflow_queue.watchdog_stuck_minutes || 10,
                      })
                    : t("admin.monitor.knowflowQueueHealthyHint")
              }}
            </p>
            <div v-if="knowflowQueueStuck" class="knowflow-queue-status__detail">
              <n-tag
                size="small"
                :type="metrics.knowflow_queue.executor_active ? 'success' : 'warning'"
                :bordered="false"
              >
                {{
                  metrics.knowflow_queue.executor_active
                    ? t("admin.monitor.knowflowExecutorActive")
                    : t("admin.monitor.knowflowExecutorIdle")
                }}
              </n-tag>
            </div>
          </div>
          <ul
            v-if="
              knowflowQueueStuck &&
              (metrics.knowflow_queue.top_backlog_documents || []).length
            "
            class="knowflow-backlog-list"
          >
            <li
              v-for="row in metrics.knowflow_queue.top_backlog_documents"
              :key="`${row.name}-${row.pending_tasks}`"
            >
              <span class="knowflow-backlog-list__count" :title="t('admin.monitor.knowflowBacklogTaskCount', { count: row.pending_tasks })">
                {{ row.pending_tasks }}
              </span>
              <span class="knowflow-backlog-list__name">{{ row.name }}</span>
            </li>
          </ul>
        </div>
        <div class="gpu-section">
          <div class="section-title">{{ t("admin.monitor.gpuSection") }}</div>
          <div v-if="gpuRows.length" class="admin-list-table">
            <n-data-table
              :columns="gpuColumns"
              :data="gpuPagedItems"
              :bordered="false"
              size="small"
              :pagination="false"
            />
            <ListTableFooter
              :page="gpuPage"
              :page-size="gpuPageSize"
              :item-count="gpuTotal"
              @update:page="onGpuPageChange"
            />
          </div>
          <n-empty v-else :description="t('admin.monitor.noGpu')" size="small" />
        </div>
      </template>
      <n-empty v-else :description="t('admin.monitor.loadingMetrics')" size="small" />
    </n-card>

    <div class="admin-list-table">
      <n-card class="monitor-section monitor-section--logs" :bordered="false">
        <template #header-extra>
          <ListRefreshButton
            :label="t('admin.monitor.refreshLogs')"
            :loading="loadingLogs"
            @click="loadLogs"
          />
        </template>
        <n-data-table
          :columns="logColumns"
          :data="logsPagedItems"
          :loading="loadingLogs"
          :scroll-x="640"
          size="small"
          :pagination="false"
        />
      </n-card>
      <ListTableFooter
        :page="logsPage"
        :page-size="logsPageSize"
        :item-count="logsTotal"
        @update:page="onLogsPageChange"
      />
    </div>
  </div>
</template>

<style scoped>
.monitor-page {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 19px;
}

.monitor-page__toolbar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 14px;
  flex-wrap: wrap;
}

.monitor-section {
  border-radius: 19px;
}

.monitor-section--logs :deep(.n-data-table) {
  max-height: 504px;
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  align-items: stretch;
}

.overview-card {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  min-height: 130px;
  box-sizing: border-box;
  padding: 17px 19px;
  border-radius: 14px;
  background: var(--platform-ui-glass-fill-subtle, rgba(255, 255, 255, 0.22));
  border: 1px solid color-mix(in srgb, var(--card-accent) 18%, transparent);
  transition: box-shadow 0.2s ease, border-color 0.2s ease;
}

.overview-card:hover {
  border-color: color-mix(in srgb, var(--card-accent) 32%, transparent);
  box-shadow: 0 5px 17px color-mix(in srgb, var(--card-accent) 10%, transparent);
}

.overview-card__icon {
  flex-shrink: 0;
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  color: var(--card-accent);
  background: color-mix(in srgb, var(--card-accent) 12%, transparent);
}

.overview-card__body {
  min-width: 0;
}

.overview-card__label {
  font-size: 0.8125rem;
  color: var(--n-text-color-3);
}

.overview-card__value {
  margin-top: 5px;
  font-size: 1.625rem;
  font-weight: 700;
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
}

.overview-card__hint {
  margin-top: 7px;
  font-size: 0.75rem;
  color: var(--n-text-color-3);
  line-height: 1.35;
}

.overview-card__names {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 10px;
}

.metric-hint {
  font-size: 14px;
  color: var(--n-text-color-3);
  margin-top: 7px;
}

.meta-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-top: 19px;
}

.gpu-section {
  margin-top: 24px;
}

.knowflow-queue-section {
  margin-top: 24px;
}

.knowflow-backlog-list {
  margin: 14px 0 0;
  padding: 0;
  list-style: none;
  font-size: 14px;
  color: var(--n-text-color-2);
}

.knowflow-queue-status {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 10px;
}

.knowflow-queue-status__hint {
  margin: 0;
}

.knowflow-queue-status__detail {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.knowflow-backlog-list li {
  display: flex;
  gap: 10px;
  padding: 5px 0;
  border-bottom: 1px solid var(--n-border-color);
}

.knowflow-backlog-list__count {
  flex: 0 0 2.5rem;
  font-variant-numeric: tabular-nums;
  color: var(--n-text-color-3);
}

.knowflow-backlog-list__name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.metric-hint--warn {
  color: var(--platform-caution);
}

.section-title {
  font-weight: 600;
  margin-bottom: 10px;
}

.gpu-vram-cell {
  min-width: 192px;
}

@media (max-width: 960px) {
  .overview-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .overview-grid {
    grid-template-columns: 1fr;
  }
}
</style>
