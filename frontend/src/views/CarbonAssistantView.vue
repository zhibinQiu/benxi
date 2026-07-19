<script setup>
defineOptions({ name: "CarbonAssistantView" });
import { ref, computed, watch, onMounted, onUnmounted } from "vue";
import {
  DocumentTextOutline,
  LeafOutline,
  TrendingUpOutline,
  CloseCircleOutline,
  DownloadOutline,
  BulbOutline,
  ShareSocialOutline,
  RefreshOutline,
} from "@vicons/ionicons5";
import { useI18n } from "../composables/useI18n";
import { usePlatformUi } from "../composables/usePlatformUi";
import {
  fetchTradingSnapshot,
  submitCarbonReport,
  fetchCarbonReports,
  cancelCarbonReport,
  deleteCarbonReport,
  downloadCarbonReport,
  viewCarbonReport,
  getCarbonReportShareUrl,
  fetchCarbonReportDetail,
} from "../api/carbonAssistant";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import FeatureSection from "../components/FeatureSection.vue";
import SelectOptionTile from "../components/SelectOptionTile.vue";
import IconAction from "../components/IconAction.vue";
import { boostNotificationPolling } from "../composables/useNotificationAlerts";

const ui = usePlatformUi();
const { t } = useI18n();
const sharingReportId = ref(null);

const activeTab = ref("trading");
const tabs = [
  { value: "trading", label: "碳交易" },
  { value: "reports", label: "碳报告" },
  { value: "strategy", label: "减碳策略" },
];

const REPORT_TYPE_LABELS = {
  market_brief: "碳交易简报",
  policy_digest: "政策摘要",
  strategy: "减碳策略",
};

function reportTypeLabel(type) {
  return REPORT_TYPE_LABELS[type] || type || "报告";
}

function formatReportTime(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return String(iso);
  }
}

function parseReportConclusion(content) {
  const raw = String(content || "").trim();
  if (!raw) return { title: "", sentence: "" };
  const sectionMatch = raw.match(
    /(?:^|\n)#{1,3}\s*先看结论\s*\n([\s\S]*?)(?=\n#{1,3}\s|$)/
  );
  let block = (sectionMatch?.[1] || raw).trim();
  block = block.replace(/^#{1,3}\s*先看结论\s*\n+/i, "").trim();
  const lines = block.split(/\n+/).map((l) => l.trim()).filter(Boolean);
  let sentence = "";
  for (const line of lines) {
    if (/^#{1,3}\s/.test(line) || /^[-*•]\s/.test(line)) continue;
    const cleaned = line.replace(/^>\s*/, "").replace(/^\*+|\*+$/g, "").trim();
    if (cleaned.length >= 12) {
      sentence = cleaned;
      break;
    }
  }
  const full = sentence || "报告已生成，点击阅读查看全文。";
  const title = full.length > 42 ? `${full.slice(0, 42)}…` : full;
  return { title, sentence: full };
}

// ── 碳交易 ──
const tradingKeyword = ref("全国碳市场");
const tradingLoading = ref(false);
const tradingData = ref(null);
const quickKeywords = ["全国碳市场", "CEA", "CCER", "钢铁纳入碳市场"];

async function loadTradingSnapshot() {
  tradingLoading.value = true;
  try {
    tradingData.value = await fetchTradingSnapshot(tradingKeyword.value.trim());
  } catch {
    ui.error("获取碳交易数据失败");
  } finally {
    tradingLoading.value = false;
  }
}

function selectQuickKeyword(kw) {
  tradingKeyword.value = kw;
  loadTradingSnapshot();
}

function summaryText(block) {
  if (!block) return "暂无数据";
  if (block.ok === false) return block.summary_md || "数据源暂时无法访问";
  return block.summary_md || "暂无摘要";
}

// ── 碳报告 ──
const reportSubject = ref("全国碳市场");
const reportType = ref("market_brief");
const reportContext = ref("");
const reportSubmitting = ref(false);

const reportTypeCards = computed(() => [
  {
    value: "market_brief",
    icon: TrendingUpOutline,
    label: t("carbonAssistant.reportMarket"),
    desc: t("carbonAssistant.reportMarketDesc"),
  },
  {
    value: "policy_digest",
    icon: DocumentTextOutline,
    label: t("carbonAssistant.reportPolicy"),
    desc: t("carbonAssistant.reportPolicyDesc"),
  },
]);

// ── 减碳策略 ──
const strategySubject = ref("钢铁行业减碳路径");
const strategyIndustry = ref("steel");
const strategyRegion = ref("全国");
const strategyYear = ref("2030");
const strategyContext = ref("");
const strategySubmitting = ref(false);

const industryCards = [
  { value: "steel", label: "钢铁" },
  { value: "cement", label: "水泥" },
  { value: "power", label: "电力" },
  { value: "chemical", label: "化工" },
  { value: "building", label: "建筑" },
  { value: "transport", label: "交通" },
];

// ── 任务 / 历史（报告 + 策略共用）──
const runningTasks = ref([]);
const completedReports = ref([]);
const historySearchQuery = ref("");
const historyFilterType = ref(""); // "" | market_brief | policy_digest | strategy
const historyPage = ref(1);
const HISTORY_PAGE_SIZE = 2;
let pollTimer = null;
const POLL_INTERVAL = 5000;

const filteredHistory = computed(() => {
  let list = completedReports.value.filter((r) => r.status !== "cancelled");
  if (historyFilterType.value) {
    list = list.filter((r) => r.report_type === historyFilterType.value);
  }
  const q = historySearchQuery.value.trim().toLowerCase();
  if (q) {
    list = list.filter(
      (r) =>
        (r.subject || "").toLowerCase().includes(q) ||
        (r.report_type || "").toLowerCase().includes(q) ||
        (r.industry || "").toLowerCase().includes(q)
    );
  }
  return list;
});

const pagedHistoryCards = computed(() => {
  const list = filteredHistory.value;
  const start = (historyPage.value - 1) * HISTORY_PAGE_SIZE;
  return list.slice(start, start + HISTORY_PAGE_SIZE).map((report) => ({
    report,
    conclusion:
      report.status === "failed"
        ? { title: "生成失败", sentence: report.error_message || "生成失败" }
        : parseReportConclusion(report.content),
  }));
});

watch(historySearchQuery, () => {
  historyPage.value = 1;
});
watch(filteredHistory, (list) => {
  const maxPage = Math.max(1, Math.ceil(list.length / HISTORY_PAGE_SIZE) || 1);
  if (historyPage.value > maxPage) historyPage.value = maxPage;
});

watch(activeTab, (tab) => {
  if (tab === "reports") historyFilterType.value = "";
  if (tab === "strategy") historyFilterType.value = "strategy";
});

async function handleSubmitReport() {
  const subject = reportSubject.value.trim();
  if (!subject) {
    ui.warning("请填写报告主题");
    return;
  }
  reportSubmitting.value = true;
  try {
    await submitCarbonReport({
      subject,
      report_type: reportType.value,
      ai_context: reportContext.value,
    });
    ui.success("任务已提交，后台分析中");
    await fetchAllReports();
    startPolling();
    boostNotificationPolling(15000);
  } catch {
    ui.error("提交失败");
  } finally {
    reportSubmitting.value = false;
  }
}

async function handleSubmitStrategy() {
  const subject = strategySubject.value.trim();
  if (!subject) {
    ui.warning("请填写策略主题");
    return;
  }
  strategySubmitting.value = true;
  try {
    await submitCarbonReport({
      subject,
      report_type: "strategy",
      industry: strategyIndustry.value,
      region: strategyRegion.value.trim(),
      target_year: strategyYear.value.trim(),
      ai_context: strategyContext.value,
    });
    ui.success("减碳策略任务已提交");
    historyFilterType.value = "strategy";
    await fetchAllReports();
    startPolling();
    boostNotificationPolling(15000);
  } catch {
    ui.error("提交失败");
  } finally {
    strategySubmitting.value = false;
  }
}

async function fetchAllReports() {
  try {
    const items = await fetchCarbonReports({ limit: 200, offset: 0 });
    const arr = Array.isArray(items) ? items : [];
    runningTasks.value = arr.filter(
      (r) => r.status === "pending" || r.status === "running"
    );
    completedReports.value = arr.filter(
      (r) => r.status !== "pending" && r.status !== "running"
    );
  } catch {
    /* silent */
  }
}

async function pollTasks() {
  if (pollTimer === null) return;
  await fetchAllReports();
  if (!runningTasks.value.length) {
    stopPolling();
    return;
  }
  pollTimer = setTimeout(pollTasks, POLL_INTERVAL);
}
function startPolling() {
  stopPolling();
  pollTimer = setTimeout(pollTasks, POLL_INTERVAL);
}
function stopPolling() {
  if (pollTimer !== null) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
}

async function handleCancelTask(taskId) {
  try {
    await cancelCarbonReport(taskId);
    ui.success("任务已取消");
    await fetchAllReports();
  } catch {
    ui.error("取消失败");
  }
}

async function handleDeleteReport(reportId) {
  ui.confirmDelete({
    title: "确认删除",
    content: "确定要删除此报告吗？删除后无法恢复。",
    positiveText: "确定",
    onPositive: async () => {
      await deleteCarbonReport(reportId);
      ui.success("已删除");
      await fetchAllReports();
    },
  });
}

async function handleDownload(reportId) {
  try {
    await downloadCarbonReport(reportId);
  } catch {
    ui.error("下载失败");
  }
}

async function handleViewReport(report) {
  try {
    await viewCarbonReport(report.id, report.share_token);
  } catch {
    ui.error("查看报告失败");
  }
}

async function handleShareReport(report) {
  if (!report?.id || sharingReportId.value) return;
  sharingReportId.value = report.id;
  try {
    let token = report.share_token;
    if (!token) {
      const detail = await fetchCarbonReportDetail(report.id);
      token = detail?.share_token || detail?.data?.share_token;
      if (token) report.share_token = token;
    }
    const url = getCarbonReportShareUrl(token);
    if (!url) throw new Error("暂无分享链接");
    await navigator.clipboard.writeText(url);
    ui.success("分享链接已复制");
  } catch (e) {
    ui.error(e?.message || "分享失败");
  } finally {
    sharingReportId.value = null;
  }
}

function statusLabel(s) {
  const m = {
    pending: "排队中",
    running: "进行中",
    completed: "已完成",
    failed: "失败",
    cancelled: "已取消",
  };
  return m[s] || s;
}

onMounted(() => {
  loadTradingSnapshot();
  fetchAllReports().then(() => {
    if (runningTasks.value.length) startPolling();
  });
});
onUnmounted(() => stopPolling());
</script>

<template>
  <FeatureSubsystemShell fill :show-intro="false">
    <div class="ca-view">
      <n-tabs v-model:value="activeTab" type="line">
        <n-tab-pane
          v-for="tab in tabs"
          :key="tab.value"
          :name="tab.value"
          :tab="tab.label"
        >
          <!-- 碳交易 -->
          <template v-if="tab.value === 'trading'">
            <div class="ca-body ca-body--single">
              <FeatureSection title="行情与政策快照">
                <div class="ca-search-row">
                  <n-input
                    v-model:value="tradingKeyword"
                    placeholder="关键词，如全国碳市场 / CEA / CCER"
                    clearable
                    size="small"
                    @keyup.enter="loadTradingSnapshot"
                  />
                  <n-button
                    size="small"
                    type="primary"
                    :loading="tradingLoading"
                    @click="loadTradingSnapshot"
                  >
                    <template #icon>
                      <n-icon :size="14" :component="RefreshOutline" />
                    </template>
                    刷新
                  </n-button>
                </div>
                <div class="ca-chips">
                  <n-tag
                    v-for="kw in quickKeywords"
                    :key="kw"
                    size="small"
                    round
                    :bordered="false"
                    class="ca-chip"
                    @click="selectQuickKeyword(kw)"
                  >
                    {{ kw }}
                  </n-tag>
                </div>
                <p class="ca-hint">
                  数据来自官方源原子工具（carbon_price / carbon_policy / carbon_data），禁止编造实时行情。
                </p>
              </FeatureSection>

              <div class="ca-snap-grid">
                <FeatureSection title="碳价行情">
                  <pre class="ca-md">{{ summaryText(tradingData?.price) }}</pre>
                </FeatureSection>
                <FeatureSection title="CCER / 市场数据">
                  <pre class="ca-md">{{ summaryText(tradingData?.ccer) }}</pre>
                </FeatureSection>
                <FeatureSection title="政策要点">
                  <pre class="ca-md">{{ summaryText(tradingData?.policy) }}</pre>
                </FeatureSection>
              </div>
            </div>
          </template>

          <!-- 碳报告 -->
          <template v-else-if="tab.value === 'reports'">
            <div class="ca-body">
              <div class="ca-main">
                <FeatureSection title="报告主题">
                  <n-input
                    v-model:value="reportSubject"
                    placeholder="如：全国碳市场 / 广东试点 / 欧盟 EU ETS"
                    size="small"
                    clearable
                  />
                </FeatureSection>
                <FeatureSection title="报告类型">
                  <div class="ca-tiles">
                    <SelectOptionTile
                      v-for="card in reportTypeCards"
                      :key="card.value"
                      :active="reportType === card.value"
                      :icon="card.icon"
                      :title="card.label"
                      :desc="card.desc"
                      @select="reportType = card.value"
                    />
                  </div>
                </FeatureSection>
                <FeatureSection title="补充说明（可选）">
                  <n-input
                    v-model:value="reportContext"
                    type="textarea"
                    :rows="3"
                    placeholder="关注重点、时间范围、行业背景等"
                    size="small"
                  />
                  <div class="ca-action-row">
                    <n-button
                      type="primary"
                      size="small"
                      :loading="reportSubmitting"
                      @click="handleSubmitReport"
                    >
                      <template #icon>
                        <n-icon :size="14" :component="DocumentTextOutline" />
                      </template>
                      生成报告
                    </n-button>
                  </div>
                </FeatureSection>
              </div>
              <aside class="ca-side">
                <FeatureSection v-if="runningTasks.length" title="进行中">
                  <div
                    v-for="task in runningTasks.filter((r) => r.report_type !== 'strategy')"
                    :key="task.id"
                    class="ca-task"
                  >
                    <div class="ca-task-head">
                      <span>{{ task.subject }}</span>
                      <n-tag size="tiny" :bordered="false">{{ statusLabel(task.status) }}</n-tag>
                    </div>
                    <n-progress
                      type="line"
                      :percentage="task.progress || 0"
                      :show-indicator="true"
                      processing
                    />
                    <div class="ca-task-actions">
                      <IconAction
                        :icon="CloseCircleOutline"
                        tip="取消"
                        @click="handleCancelTask(task.id)"
                      />
                    </div>
                  </div>
                </FeatureSection>
                <FeatureSection title="历史报告">
                  <n-input
                    v-model:value="historySearchQuery"
                    size="tiny"
                    clearable
                    placeholder="搜索主题"
                    class="ca-history-search"
                  />
                  <div v-if="!pagedHistoryCards.filter((c) => c.report.report_type !== 'strategy').length" class="ca-empty">
                    暂无报告
                  </div>
                  <div
                    v-for="card in pagedHistoryCards.filter((c) => c.report.report_type !== 'strategy')"
                    :key="card.report.id"
                    class="ca-hist-card"
                  >
                    <div class="ca-hist-title">{{ card.report.subject }}</div>
                    <div class="ca-hist-meta">
                      {{ reportTypeLabel(card.report.report_type) }} ·
                      {{ formatReportTime(card.report.created_at) }}
                    </div>
                    <p class="ca-hist-sentence">{{ card.conclusion.sentence }}</p>
                    <div class="ca-hist-actions">
                      <IconAction
                        :icon="DocumentTextOutline"
                        tip="阅读"
                        :disabled="card.report.status !== 'completed'"
                        @click="handleViewReport(card.report)"
                      />
                      <IconAction
                        :icon="ShareSocialOutline"
                        tip="分享"
                        :disabled="card.report.status !== 'completed'"
                        @click="handleShareReport(card.report)"
                      />
                      <IconAction
                        :icon="DownloadOutline"
                        tip="下载"
                        :disabled="card.report.status !== 'completed'"
                        @click="handleDownload(card.report.id)"
                      />
                      <IconAction
                        :icon="CloseCircleOutline"
                        tip="删除"
                        @click="handleDeleteReport(card.report.id)"
                      />
                    </div>
                  </div>
                </FeatureSection>
              </aside>
            </div>
          </template>

          <!-- 减碳策略 -->
          <template v-else-if="tab.value === 'strategy'">
            <div class="ca-body">
              <div class="ca-main">
                <FeatureSection title="策略主题">
                  <n-input
                    v-model:value="strategySubject"
                    placeholder="如：钢铁行业达峰路径 / 园区零碳改造"
                    size="small"
                    clearable
                  />
                </FeatureSection>
                <FeatureSection title="行业">
                  <div class="ca-industry-chips">
                    <n-tag
                      v-for="item in industryCards"
                      :key="item.value"
                      size="small"
                      round
                      :type="strategyIndustry === item.value ? 'primary' : 'default'"
                      :bordered="false"
                      class="ca-chip"
                      @click="strategyIndustry = item.value"
                    >
                      {{ item.label }}
                    </n-tag>
                  </div>
                </FeatureSection>
                <FeatureSection title="地区与目标年">
                  <div class="ca-form-row">
                    <n-input
                      v-model:value="strategyRegion"
                      placeholder="地区，如全国 / 广东"
                      size="small"
                    />
                    <n-input
                      v-model:value="strategyYear"
                      placeholder="目标年，如 2030"
                      size="small"
                      style="max-width: 120px"
                    />
                  </div>
                </FeatureSection>
                <FeatureSection title="约束与补充（可选）">
                  <n-input
                    v-model:value="strategyContext"
                    type="textarea"
                    :rows="3"
                    placeholder="预算、技术边界、合规要求等"
                    size="small"
                  />
                  <div class="ca-action-row">
                    <n-button
                      type="primary"
                      size="small"
                      :loading="strategySubmitting"
                      @click="handleSubmitStrategy"
                    >
                      <template #icon>
                        <n-icon :size="14" :component="BulbOutline" />
                      </template>
                      生成减碳策略
                    </n-button>
                  </div>
                  <p class="ca-hint">
                    将调用官方政策/排放/地方数据源，结合 AI 输出分阶段行动建议；不构成合规承诺。
                  </p>
                </FeatureSection>
              </div>
              <aside class="ca-side">
                <FeatureSection
                  v-if="runningTasks.filter((r) => r.report_type === 'strategy').length"
                  title="进行中"
                >
                  <div
                    v-for="task in runningTasks.filter((r) => r.report_type === 'strategy')"
                    :key="task.id"
                    class="ca-task"
                  >
                    <div class="ca-task-head">
                      <span>{{ task.subject }}</span>
                      <n-tag size="tiny" :bordered="false">{{ statusLabel(task.status) }}</n-tag>
                    </div>
                    <n-progress
                      type="line"
                      :percentage="task.progress || 0"
                      processing
                    />
                    <div class="ca-task-actions">
                      <IconAction
                        :icon="CloseCircleOutline"
                        tip="取消"
                        @click="handleCancelTask(task.id)"
                      />
                    </div>
                  </div>
                </FeatureSection>
                <FeatureSection title="策略历史">
                  <div
                    v-if="!pagedHistoryCards.filter((c) => c.report.report_type === 'strategy').length"
                    class="ca-empty"
                  >
                    暂无策略报告
                  </div>
                  <div
                    v-for="card in pagedHistoryCards.filter((c) => c.report.report_type === 'strategy')"
                    :key="card.report.id"
                    class="ca-hist-card"
                  >
                    <div class="ca-hist-title">
                      <n-icon :component="LeafOutline" :size="14" />
                      {{ card.report.subject }}
                    </div>
                    <div class="ca-hist-meta">
                      {{ card.report.industry || "—" }} ·
                      {{ card.report.region || "—" }} ·
                      {{ formatReportTime(card.report.created_at) }}
                    </div>
                    <p class="ca-hist-sentence">{{ card.conclusion.sentence }}</p>
                    <div class="ca-hist-actions">
                      <IconAction
                        :icon="DocumentTextOutline"
                        tip="阅读"
                        :disabled="card.report.status !== 'completed'"
                        @click="handleViewReport(card.report)"
                      />
                      <IconAction
                        :icon="ShareSocialOutline"
                        tip="分享"
                        :disabled="card.report.status !== 'completed'"
                        @click="handleShareReport(card.report)"
                      />
                      <IconAction
                        :icon="DownloadOutline"
                        tip="下载"
                        :disabled="card.report.status !== 'completed'"
                        @click="handleDownload(card.report.id)"
                      />
                      <IconAction
                        :icon="CloseCircleOutline"
                        tip="删除"
                        @click="handleDeleteReport(card.report.id)"
                      />
                    </div>
                  </div>
                </FeatureSection>
              </aside>
            </div>
          </template>
        </n-tab-pane>
      </n-tabs>
    </div>
  </FeatureSubsystemShell>
</template>

<style scoped>
.ca-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.ca-view :deep(.n-tabs) {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.ca-view :deep(.n-tabs-nav) {
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--platform-bg, #fff);
  padding: 0 4px;
}
.ca-view :deep(.n-tab-pane) {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 12px 4px 24px;
}
.ca-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 16px;
  align-items: start;
}
.ca-body--single {
  grid-template-columns: 1fr;
}
.ca-main,
.ca-side {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}
.ca-side {
  position: sticky;
  top: 8px;
}
.ca-search-row,
.ca-form-row,
.ca-action-row {
  display: flex;
  gap: 8px;
  align-items: center;
}
.ca-action-row {
  margin-top: 12px;
}
.ca-chips,
.ca-industry-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}
.ca-chip {
  cursor: pointer;
}
.ca-hint {
  margin: 10px 0 0;
  font-size: var(--platform-font-size-sm);
  color: var(--platform-text-tertiary);
  line-height: 1.5;
}
.ca-snap-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px;
}
.ca-md {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  font-size: var(--platform-font-size-sm);
  line-height: 1.55;
  color: var(--platform-text);
  max-height: 360px;
  overflow: auto;
}
.ca-tiles {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.ca-task,
.ca-hist-card {
  padding: 10px 0;
  border-bottom: 1px solid var(--platform-border-strong);
}
.ca-task:last-child,
.ca-hist-card:last-child {
  border-bottom: none;
}
.ca-task-head,
.ca-hist-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: var(--platform-font-size-sm);
  font-weight: 500;
  color: var(--platform-text);
}
.ca-hist-title {
  justify-content: flex-start;
}
.ca-hist-meta {
  margin-top: 4px;
  font-size: 12px;
  color: var(--platform-text-tertiary);
}
.ca-hist-sentence {
  margin: 8px 0;
  font-size: var(--platform-font-size-sm);
  color: var(--platform-text-secondary);
  line-height: 1.45;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.ca-task-actions,
.ca-hist-actions {
  display: flex;
  gap: 4px;
  margin-top: 6px;
}
.ca-history-search {
  margin-bottom: 8px;
}
.ca-empty {
  padding: 16px 0;
  font-size: var(--platform-font-size-sm);
  color: var(--platform-text-tertiary);
  text-align: center;
}
@media (max-width: 960px) {
  .ca-body {
    grid-template-columns: 1fr;
  }
  .ca-side {
    position: static;
  }
}
</style>
