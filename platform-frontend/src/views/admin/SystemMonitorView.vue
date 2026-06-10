<script setup>
import { computed, h, onMounted, onUnmounted, ref } from "vue";
import {
  NCard,
  NGrid,
  NGi,
  NStatistic,
  NProgress,
  NDataTable,
  NButton,
  NSpace,
  NEmpty,
  NTag,
  useMessage,
} from "naive-ui";
import { fetchAuditLogs, fetchSystemMetrics } from "../../api/client";

const message = useMessage();
const loadingLogs = ref(false);
const loadingMetrics = ref(false);
const logs = ref([]);
const metrics = ref(null);
let metricsTimer = null;

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

function formatUptime(sec) {
  if (!sec) return "—";
  const d = Math.floor(sec / 86400);
  const h = Math.floor((sec % 86400) / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (d > 0) return `${d} 天 ${h} 小时`;
  if (h > 0) return `${h} 小时 ${m} 分`;
  return `${m} 分钟`;
}

function formatTime(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

const logColumns = [
  { title: "时间", key: "created_at", width: 170, render: (r) => formatTime(r.created_at) },
  { title: "用户", key: "username", width: 100, render: (r) => r.username || "—" },
  { title: "操作", key: "action", minWidth: 160, ellipsis: { tooltip: true } },
  { title: "IP", key: "ip_address", width: 120, render: (r) => r.ip_address || "—" },
];

const gpuRows = computed(() => metrics.value?.gpus || []);

const gpuColumns = [
  { title: "GPU", key: "index", width: 60, render: (r) => `#${r.index}` },
  { title: "型号", key: "name", ellipsis: { tooltip: true } },
  {
    title: "显存",
    key: "vram",
    width: 200,
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
          style: "margin-top: 4px",
        }),
      ]);
    },
  },
  {
    title: "利用率",
    key: "utilization_percent",
    width: 90,
    render: (r) => (r.utilization_percent != null ? `${r.utilization_percent}%` : "—"),
  },
];

async function loadLogs() {
  loadingLogs.value = true;
  try {
    logs.value = await fetchAuditLogs(200);
  } catch (e) {
    message.error(e.message);
  } finally {
    loadingLogs.value = false;
  }
}

async function loadMetrics() {
  loadingMetrics.value = true;
  try {
    metrics.value = await fetchSystemMetrics();
  } catch (e) {
    message.error(e.message);
  } finally {
    loadingMetrics.value = false;
  }
}

async function refreshAll() {
  await Promise.all([loadMetrics(), loadLogs()]);
}

onMounted(async () => {
  await refreshAll();
  metricsTimer = setInterval(loadMetrics, 15000);
});

onUnmounted(() => {
  if (metricsTimer) clearInterval(metricsTimer);
});
</script>

<template>
  <n-space vertical :size="16" class="monitor-page">
    <n-card title="系统资源">
      <template #header-extra>
        <n-button size="small" :loading="loadingMetrics" @click="loadMetrics">刷新</n-button>
      </template>
      <template v-if="metrics">
        <n-grid :cols="4" :x-gap="16" :y-gap="16" responsive="screen">
          <n-gi>
            <n-statistic label="CPU 使用率">
              <template #default>{{ metrics.cpu.percent?.toFixed(1) }}%</template>
            </n-statistic>
            <n-progress
              type="line"
              :percentage="Math.min(100, metrics.cpu.percent || 0)"
              :show-indicator="false"
              style="margin-top: 8px"
            />
            <div class="metric-hint">
              {{ metrics.cpu.count_physical || "—" }} 物理核 /
              {{ metrics.cpu.count_logical || "—" }} 逻辑核
            </div>
          </n-gi>
          <n-gi>
            <n-statistic label="内存">
              <template #default>{{ metrics.memory.percent?.toFixed(1) }}%</template>
            </n-statistic>
            <n-progress
              type="line"
              :percentage="Math.min(100, metrics.memory.percent || 0)"
              :show-indicator="false"
              status="info"
              style="margin-top: 8px"
            />
            <div class="metric-hint">
              {{ formatBytes(metrics.memory.used_bytes) }} /
              {{ formatBytes(metrics.memory.total_bytes) }}
            </div>
          </n-gi>
          <n-gi>
            <n-statistic label="磁盘 (/)">
              <template #default>{{ metrics.disk.percent?.toFixed(1) }}%</template>
            </n-statistic>
            <n-progress
              type="line"
              :percentage="Math.min(100, metrics.disk.percent || 0)"
              :show-indicator="false"
              status="warning"
              style="margin-top: 8px"
            />
            <div class="metric-hint">
              {{ formatBytes(metrics.disk.used_bytes) }} /
              {{ formatBytes(metrics.disk.total_bytes) }}
            </div>
          </n-gi>
          <n-gi>
            <n-statistic label="运行时长">
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
            负载 {{ metrics.cpu.load_avg.map((x) => x.toFixed(2)).join(" / ") }}
          </span>
          <span class="metric-hint">
            交换分区 {{ formatBytes(metrics.swap.used_bytes) }} /
            {{ formatBytes(metrics.swap.total_bytes) }}
          </span>
        </div>
        <div class="gpu-section">
          <div class="section-title">显存 (GPU)</div>
          <n-data-table
            v-if="gpuRows.length"
            :columns="gpuColumns"
            :data="gpuRows"
            :bordered="false"
            size="small"
          />
          <n-empty v-else description="未检测到 NVIDIA GPU 或 nvidia-smi 不可用" size="small" />
        </div>
      </template>
    </n-card>

    <n-card title="用户操作日志">
      <template #header-extra>
        <n-button size="small" :loading="loadingLogs" @click="loadLogs">刷新</n-button>
      </template>
      <n-data-table
        :columns="logColumns"
        :data="logs"
        :loading="loadingLogs"
        :scroll-x="640"
        size="small"
      />
    </n-card>
  </n-space>
</template>

<style scoped>
.monitor-page {
  width: 100%;
}
.metric-hint {
  font-size: 12px;
  color: var(--n-text-color-3);
  margin-top: 6px;
}
.meta-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 16px;
}
.gpu-section {
  margin-top: 20px;
}
.section-title {
  font-weight: 600;
  margin-bottom: 8px;
}
.gpu-vram-cell {
  min-width: 160px;
}
</style>
