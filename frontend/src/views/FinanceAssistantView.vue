<script setup>
defineOptions({ name: "FinanceAssistantView" });
import { ref, computed, watch, onMounted, onUnmounted } from "vue";
import {
  SearchOutline,
  DocumentTextOutline,
  ChatbubblesOutline,
  StatsChartOutline,
  BulbOutline,
  TrendingUpOutline,
  CloseCircleOutline,
  DownloadOutline,
  SpeedometerOutline,
  GitBranchOutline,
  AnalyticsOutline,
  CompassOutline,
  BookOutline,
  FolderOpenOutline,
  ShareSocialOutline,
} from "@vicons/ionicons5";
import { useI18n } from "../composables/useI18n";
import { usePlatformUi } from "../composables/usePlatformUi";
import {
  searchStocks,
  submitReport,
  fetchReports,
  downloadReport,
  cancelReport,
  viewReport,
  deleteReport,
  importReportToLibrary,
  getReportShareUrl,
  shareReport,
  unshareReport,
} from "../api/finance";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import FeatureSection from "../components/FeatureSection.vue";
import SelectOptionTile from "../components/SelectOptionTile.vue";
import IconAction from "../components/IconAction.vue";
import ShareLinkModal from "../components/ShareLinkModal.vue";
import { formatStockCode } from "../utils/stockCode";
import { boostNotificationPolling } from "../composables/useNotificationAlerts";

const ui = usePlatformUi();
const { t } = useI18n();
const importingLibraryId = ref(null);
const sharingReportId = ref(null);
const showShareModal = ref(false);
const shareTargetReport = ref(null);
const shareModalUrl = ref("");

const CONCLUSION_TAGS = ["价值线索", "风险压力", "跟踪优先级"];

/** 报告类型中文（含生成前选择的圆桌子类型 / 方向） */
function reportTypeLabel(report) {
  const type = report?.report_type;
  if (type === "ai") return "AI 解读";
  if (type === "vpa") return "量价会诊";
  if (type === "roundtable") {
    const kind = report.roundtable_type === "research" ? "专业研究" : "辩论圆桌";
    const dir = report.research_direction === "shortterm" ? "短线" : "基本面";
    return `圆桌报告 · ${kind} · ${dir}`;
  }
  return type || "报告";
}

function reportCardTitle(report) {
  const name = (report?.stock_name || "").trim() || report?.stock_code || "股票";
  return `${name}研究报告`;
}

function formatReportTime(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return String(iso);
  }
}

/** 从长结论压成更短的标题句 */
function shortenConclusion(text, maxLen = 42) {
  const s = String(text || "").replace(/\s+/g, " ").trim();
  if (!s) return "";
  const clause = s.split(/[。！？；\n]/)[0]?.trim() || s;
  const cut = clause.split(/[，、：:]/)[0]?.trim() || clause;
  const base = cut.length >= 8 ? cut : clause;
  if (base.length <= maxLen) return base;
  return `${base.slice(0, maxLen).replace(/[，、：:.\s]+$/, "")}…`;
}

/** 从报告 Markdown 抽取短结论标题、一句话结论与三个结论标签 */
function parseReportConclusion(content) {
  const empty = { tags: [...CONCLUSION_TAGS], title: "", sentence: "" };
  const raw = String(content || "").trim();
  if (!raw) return empty;

  const sectionMatch = raw.match(
    /(?:^|\n)#{1,3}\s*先看结论\s*\n([\s\S]*?)(?=\n#{1,3}\s*(?:研究问题|事实底稿|圆桌参与者|研究参与者|第\s*\d\s*轮)|$)/
  );
  let block = (sectionMatch?.[1] || raw).trim();
  // 去掉重复的「先看结论」标题与占位
  block = block.replace(/^#{1,3}\s*先看结论\s*\n+/i, "").trim();

  const placeholder = /最终研究报告结论将在辩论结束后生成|结论将在/.test(block);
  if (placeholder) {
    const sentence = "结论生成中，完成后可在此查看摘要。";
    return { tags: [...CONCLUSION_TAGS], title: "结论生成中", sentence };
  }

  const lines = block.split(/\n+/).map((l) => l.trim()).filter(Boolean);
  let sentence = "";
  for (const line of lines) {
    if (/^#{1,3}\s/.test(line)) continue;
    if (/^[-*•]\s/.test(line)) continue;
    if (/^三条要点/.test(line)) break;
    const cleaned = line.replace(/^>\s*/, "").replace(/^\*+|\*+$/g, "").trim();
    if (cleaned.length >= 12) {
      sentence = cleaned;
      break;
    }
  }

  const full = sentence || "报告已生成，点击阅读查看完整研究结论。";
  return {
    tags: [...CONCLUSION_TAGS],
    title: shortenConclusion(full),
    sentence: full,
  };
}

// ── Tab ──
const activeTab = ref("ai-research");
const tabs = [
  { value: "ai-research", label: "AI 研究" },
  { value: "strategy", label: "实战策略" },
  { value: "factors", label: "因子配置" },
  { value: "gap", label: "断层研究" },
];

// ── 快捷股票（展示码带交易所后缀，如 000682.sz）──
const quickStocks = [
  { name: "东方电子", code: "000682" },
  { name: "中际旭创", code: "300308" },
  { name: "宁德时代", code: "300750" },
];

// ── 量价会诊分析框架 ──
const vpaFramework = [
  { title: "指标", icon: SpeedometerOutline, items: "强弱评分、量比、换手率、资金流向与市场温度" },
  { title: "形态", icon: GitBranchOutline, items: "K线结构、经典形态、放量/缩量关键位置" },
  { title: "趋势", icon: AnalyticsOutline, items: "均线位置、近期涨跌幅、波段强度与背离风险" },
  { title: "决策", icon: CompassOutline, items: "输出观察清单和风险边界，不给买卖指令" },
];

// ── 股票搜索状态 ──
const stockQuery = ref("");
const stockSearchResults = ref([]);
const stockSearching = ref(false);
const selectedStock = ref(null);
const showDropdown = ref(false);

// ── AI 研究状态 ──
const reportType = ref("ai");
const aiContext = ref("");
const roundtableType = ref("debate");
const researchDirection = ref("fundamental");
const submitting = ref(false);

const skillCards = computed(() => [
  { value: "ai", icon: DocumentTextOutline, label: t("financeAssistant.reportAi"), desc: t("financeAssistant.reportAiDesc") },
  { value: "roundtable", icon: ChatbubblesOutline, label: t("financeAssistant.reportRoundtable"), desc: t("financeAssistant.reportRoundtableDesc") },
  { value: "vpa", icon: StatsChartOutline, label: t("financeAssistant.reportVpa"), desc: t("financeAssistant.reportVpaDesc") },
]);

const roundtableTypeCards = computed(() => [
  { value: "debate", icon: ChatbubblesOutline, label: t("financeAssistant.roundtableDebate"), desc: t("financeAssistant.roundtableDebateDesc") },
  { value: "research", icon: BulbOutline, label: t("financeAssistant.roundtableResearch"), desc: t("financeAssistant.roundtableResearchDesc") },
]);

const directionCards = computed(() => [
  { value: "fundamental", icon: BulbOutline, label: t("financeAssistant.directionFundamental"), desc: t("financeAssistant.directionFundamentalDesc") },
  { value: "shortterm", icon: TrendingUpOutline, label: t("financeAssistant.directionShortterm"), desc: t("financeAssistant.directionShorttermDesc") },
]);

const card3Title = computed(() => {
  if (reportType.value === "ai" || reportType.value === "roundtable") return "配置";
  return "分析框架";
});

const showAiContext = computed(() => reportType.value === "ai");
const showRoundtableConfig = computed(() => reportType.value === "roundtable");
const showVpaHint = computed(() => reportType.value === "vpa");

const actionLabel = computed(() => {
  if (reportType.value === "ai") return "生成解读";
  if (reportType.value === "roundtable") return "生成专业圆桌";
  return "运行量价会诊";
});
const actionDisabled = computed(() => !selectedStock.value || submitting.value);

// ── 右侧任务 / 历史 ──
const runningTasks = ref([]);
const completedReports = ref([]);
const historySearchQuery = ref("");
const historyPage = ref(1);
const HISTORY_PAGE_SIZE = 1;
let pollTimer = null;
const POLL_INTERVAL = 5000;

// 过滤历史报告：不显示已取消 + 按搜索词过滤
const filteredHistory = computed(() => {
  let list = completedReports.value.filter(r => r.status !== "cancelled");
  const q = historySearchQuery.value.trim().toLowerCase();
  if (q) {
    list = list.filter(r =>
      (r.stock_code || "").toLowerCase().includes(q) ||
      (r.stock_name || "").toLowerCase().includes(q) ||
      (r.report_type || "").toLowerCase().includes(q)
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
        ? {
            tags: [...CONCLUSION_TAGS],
            title: "生成失败",
            sentence: report.error_message || "生成失败",
          }
        : parseReportConclusion(report.content),
  }));
});

watch(historySearchQuery, () => { historyPage.value = 1; });
watch(filteredHistory, (list) => {
  const maxPage = Math.max(1, Math.ceil(list.length / HISTORY_PAGE_SIZE) || 1);
  if (historyPage.value > maxPage) historyPage.value = maxPage;
});

// ── 搜索 ──
async function doSearch() {
  const q = stockQuery.value.trim();
  if (!q) return;
  stockSearching.value = true;
  stockSearchResults.value = [];
  try {
    const results = await searchStocks(q);
    stockSearchResults.value = results || [];
    showDropdown.value = true;
    if (!stockSearchResults.value.length) ui.warning("未找到匹配结果");
  } catch {
    stockSearchResults.value = [];
    ui.error("搜索失败");
  } finally {
    stockSearching.value = false;
  }
}

function selectStock(stock) {
  selectedStock.value = stock;
  stockQuery.value = stock.code;
  stockSearchResults.value = [];
  showDropdown.value = false;
}

function selectQuickStock(s) {
  selectedStock.value = { code: s.code, name: s.name };
  stockQuery.value = s.code;
  showDropdown.value = false;
  stockSearchResults.value = [];
}

function clearSelection() { selectedStock.value = null; stockQuery.value = ""; }

async function handleAction() {
  if (!selectedStock.value) return;
  submitting.value = true;
  try {
    const payload = {
      stock_code: selectedStock.value.code,
      stock_name: selectedStock.value.name,
      report_type: reportType.value,
      ai_context: aiContext.value,
    };
    if (reportType.value === "roundtable") {
      payload.roundtable_type = roundtableType.value;
      payload.research_direction = researchDirection.value;
    }
    await submitReport(payload);
    ui.success("任务已提交，后台分析中");
    await fetchAllReports();
    startPolling();
    boostNotificationPolling(15000);
  } catch {
    ui.error("提交失败");
  } finally {
    submitting.value = false;
  }
}

// ── 合并数据获取（减少一次后端调用）──
async function fetchAllReports() {
  try {
    const items = await fetchReports("", 200, 0);
    const list = items || [];
    runningTasks.value = list.filter(r => r.status === "pending" || r.status === "running");
    completedReports.value = list.filter(r => r.status !== "pending" && r.status !== "running");
  } catch { /* silent */ }
}

async function pollTasks() {
  if (pollTimer === null) return;
  await fetchAllReports();
  if (!runningTasks.value.length) { stopPolling(); return; }
  pollTimer = setTimeout(pollTasks, POLL_INTERVAL);
}
function startPolling() { stopPolling(); pollTimer = setTimeout(pollTasks, POLL_INTERVAL); }
function stopPolling() { if (pollTimer !== null) { clearTimeout(pollTimer); pollTimer = null; } }

async function handleCancelTask(taskId) {
  try {
    await cancelReport(taskId);
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
      await deleteReport(reportId);
      ui.success("已删除");
      await fetchAllReports();
    },
  });
}

async function handleDownload(reportId, fmt = "md") {
  try { await downloadReport(reportId, fmt); }
  catch { ui.error("下载失败"); }
}

async function handleViewReport(report) {
  try { await viewReport(report.id, report.share_token); }
  catch { ui.error("查看报告失败"); }
}

async function handleImportLibrary(report) {
  if (!report?.id || importingLibraryId.value) return;
  importingLibraryId.value = report.id;
  try {
    const res = await importReportToLibrary(report.id);
    ui.success(res?.message || "已加入个人文档库（未分类）");
  } catch (e) {
    ui.error(e?.message || "加入文档库失败");
  } finally {
    importingLibraryId.value = null;
  }
}

async function handleShareReport(report) {
  if (!report?.id) return;
  shareTargetReport.value = report;
  shareModalUrl.value = report.share_token ? getReportShareUrl(report.share_token) : "";
  showShareModal.value = true;
  if (!shareModalUrl.value) {
    await generateOrRefreshReportShare(report, { regenerate: true });
  }
}

async function generateOrRefreshReportShare(report, { regenerate = true } = {}) {
  const target = report || shareTargetReport.value;
  if (!target?.id || sharingReportId.value) return;
  sharingReportId.value = target.id;
  try {
    const res = await shareReport(target.id, { regenerate });
    const token = res?.share_token;
    if (!token) throw new Error("未返回分享令牌");
    target.share_token = token;
    const url = getReportShareUrl(token);
    shareModalUrl.value = url;
    try {
      await navigator.clipboard.writeText(url);
      ui.success(regenerate ? "已重新分享，链接已复制" : "链接已复制");
    } catch {
      ui.success(regenerate ? "已重新分享" : "分享链接已生成");
    }
  } catch (e) {
    ui.error(e?.message || "分享失败");
  } finally {
    sharingReportId.value = null;
  }
}

async function unshareCurrentReport() {
  const target = shareTargetReport.value;
  if (!target?.id || sharingReportId.value) return;
  sharingReportId.value = target.id;
  try {
    await unshareReport(target.id);
    target.share_token = null;
    shareModalUrl.value = "";
    ui.success("已取消分享");
  } catch (e) {
    ui.error(e?.message || "取消分享失败");
  } finally {
    sharingReportId.value = null;
  }
}

async function copyShareModalUrl() {
  const url = shareModalUrl.value;
  if (!url) return;
  try {
    await navigator.clipboard.writeText(url);
    ui.success("链接已复制");
  } catch {
    ui.error("复制失败");
  }
}

onMounted(() => {
  fetchAllReports();
  if (runningTasks.value.length) startPolling();
});
onUnmounted(() => stopPolling());

function statusLabel(s) {
  const m = { pending: "排队中", running: "进行中", completed: "已完成", failed: "失败", cancelled: "已取消" };
  return m[s] || s;
}

// ── 占位数据 ──
const strategyPlans = [
  { name: "均线低吸策略", desc: "5/10/20 日均线金叉买入，死叉卖出", interval: "日线", perf: "+12.3%" },
  { name: "放量突破策略", desc: "成交量放大 2 倍 + 突破前高入场", interval: "60分钟", perf: "+8.7%" },
  { name: "MACD 底背离", desc: "价格新低而 MACD 不创新低时买入", interval: "日线", perf: "+15.1%" },
];

const factorGroups = [
  { name: "动量因子", desc: "过去 20 日收益率排名", enabled: true },
  { name: "估值因子", desc: "PE / PB 历史分位数", enabled: true },
  { name: "资金因子", desc: "主力净流入 / 大单占比", enabled: true },
  { name: "情绪因子", desc: "换手率 / 融资余额变化", enabled: false },
  { name: "波动因子", desc: "ATR / 振幅波动率", enabled: false },
  { name: "质量因子", desc: "ROE / 毛利率 / 负债率", enabled: false },
];
</script>

<template>
  <FeatureSubsystemShell fill :show-intro="false">
    <div class="fa-view">
      <n-tabs v-model:value="activeTab" type="line">
        <n-tab-pane
          v-for="tab in tabs"
          :key="tab.value"
          :name="tab.value"
          :tab="tab.label"
        >
          <template #tab>{{ tab.label }}</template>

          <!-- ── AI 研究 ── -->
          <template v-if="tab.value === 'ai-research'">
            <div class="fa-body">
              <div class="fa-main">
                <FeatureSection :title="t('financeAssistant.searchStockLabel')">
                  <div class="fa-search-wrap">
                    <div class="fa-search-row">
                      <n-input
                        v-model:value="stockQuery"
                        :placeholder="t('financeAssistant.searchPlaceholder')"
                        :loading="stockSearching"
                        clearable
                        size="small"
                        @keyup.enter="doSearch"
                        @clear="clearSelection"
                        @focus="showDropdown = stockSearchResults.length > 0"
                        @blur="setTimeout(() => (showDropdown = false), 200)"
                      />
                      <n-button size="small" tertiary @click="doSearch">
                        <template #icon><n-icon :size="14" :component="SearchOutline" /></template>
                        搜索
                      </n-button>
                    </div>
                    <div v-if="showDropdown && stockSearchResults.length" class="fa-dropdown">
                      <div
                        v-for="s in stockSearchResults"
                        :key="s.code"
                        class="fa-dropdown-item"
                        @mousedown.prevent="selectStock(s)"
                      >
                        <span class="fa-dd-code">{{ formatStockCode(s.code) }}</span>
                        <span class="fa-dd-name">{{ s.name }}</span>
                      </div>
                    </div>
                  </div>
                  <div class="fa-quick-grid">
                    <button
                      v-for="s in quickStocks"
                      :key="s.code"
                      type="button"
                      class="fa-quick-chip"
                      :class="{ 'fa-quick-chip--active': selectedStock?.code === s.code }"
                      @click="selectQuickStock(s)"
                    >
                      <span class="fa-quick-name">{{ s.name }}</span>
                      <span class="fa-quick-code">{{ formatStockCode(s.code) }}</span>
                    </button>
                  </div>
                  <div v-if="selectedStock" class="fa-selected">
                    <n-tag
                      closable
                      size="tiny"
                      :bordered="false"
                      class="fa-selected-tag"
                      @close="clearSelection"
                    >
                      {{ formatStockCode(selectedStock.code) }} {{ selectedStock.name }}
                    </n-tag>
                  </div>
                </FeatureSection>

                <FeatureSection :title="t('financeAssistant.reportTypeLabel')">
                  <div class="fa-grid-3">
                    <SelectOptionTile
                      v-for="card in skillCards"
                      :key="card.value"
                      :active="reportType === card.value"
                      :icon="card.icon"
                      :icon-size="16"
                      :title="card.label"
                      :desc="card.desc"
                      @select="reportType = card.value"
                    />
                  </div>
                </FeatureSection>

                <FeatureSection :title="card3Title">
                  <div v-if="showAiContext" class="fa-config-section">
                    <n-input
                      v-model:value="aiContext"
                      type="textarea"
                      :placeholder="t('financeAssistant.aiContextPlaceholder')"
                      :rows="2"
                      :maxlength="500"
                      show-count
                      size="small"
                    />
                  </div>
                  <div v-if="showRoundtableConfig" class="fa-config-section">
                    <div class="fa-config-row">
                      <span class="fa-config-label">{{ t("financeAssistant.roundtableType") }}</span>
                      <div class="fa-grid-2">
                        <SelectOptionTile
                          v-for="card in roundtableTypeCards"
                          :key="card.value"
                          :active="roundtableType === card.value"
                          :icon="card.icon"
                          :title="card.label"
                          :desc="card.desc"
                          @select="roundtableType = card.value"
                        />
                      </div>
                    </div>
                    <div class="fa-config-row">
                      <span class="fa-config-label">{{ t("financeAssistant.researchDirection") }}</span>
                      <div class="fa-grid-2">
                        <SelectOptionTile
                          v-for="card in directionCards"
                          :key="card.value"
                          :active="researchDirection === card.value"
                          :icon="card.icon"
                          :title="card.label"
                          :desc="card.desc"
                          @select="researchDirection = card.value"
                        />
                      </div>
                    </div>
                  </div>
                  <div v-if="showVpaHint" class="fa-vpa-section">
                    <div class="fa-vpa-intro">围绕指标、形态、趋势、决策四个层面，快速生成可复核的短线检查单。</div>
                    <div class="fa-vpa-grid">
                      <div v-for="f in vpaFramework" :key="f.title" class="fa-vpa-card">
                        <div class="fa-vpa-card-icon"><n-icon :size="14" :component="f.icon" /></div>
                        <div class="fa-vpa-card-body">
                          <div class="fa-vpa-card-title">{{ f.title }}</div>
                          <div class="fa-vpa-card-items">{{ f.items }}</div>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div class="fa-action-bar">
                    <n-button
                      secondary
                      size="small"
                      :loading="submitting"
                      :disabled="actionDisabled"
                      class="fa-action-btn"
                      @click="handleAction"
                    >{{ actionLabel }}</n-button>
                  </div>
                </FeatureSection>
              </div>

              <div class="fa-side">
                <FeatureSection title="进行中的任务" dense>
                  <template #extra>
                    <n-tag v-if="runningTasks.length" size="tiny" :bordered="false" round>{{ runningTasks.length }}</n-tag>
                  </template>
                  <div v-if="!runningTasks.length" class="fa-empty">暂无进行中的任务</div>
                  <div v-for="task in runningTasks" :key="task.id" class="fa-task-item">
                    <div class="fa-task-top">
                      <div class="fa-task-info">
                        <span class="fa-task-name">{{ task.stock_name }}({{ formatStockCode(task.stock_code) }})</span>
                        <n-tag size="tiny" :bordered="false">{{ reportTypeLabel(task) }}</n-tag>
                      </div>
                      <div class="fa-task-actions">
                        <n-progress
                          type="circle"
                          status="default"
                          :percentage="task.progress"
                          :stroke-width="8"
                          :size="18"
                          class="fa-progress-circle"
                        />
                        <n-button size="small" quaternary circle type="error" @click="handleCancelTask(task.id)">
                          <template #icon><n-icon :component="CloseCircleOutline" :size="14" /></template>
                        </n-button>
                      </div>
                    </div>
                    <div class="fa-task-bottom">
                      <span class="fa-task-status">{{ statusLabel(task.status) }}</span>
                      <span v-if="task.error_message && task.status === 'running'" class="fa-task-step">{{ task.error_message }}</span>
                    </div>
                  </div>
                </FeatureSection>

                <FeatureSection title="历史报告" dense>
                  <div class="fa-history-search">
                    <n-input v-model:value="historySearchQuery" placeholder="搜索报告（代码/名称/类型）" size="tiny" clearable />
                  </div>
                  <div v-if="!filteredHistory.length" class="fa-empty">暂无历史报告</div>
                  <div v-for="{ report, conclusion } in pagedHistoryCards" :key="report.id" class="fa-history-card">
                    <div class="fa-history-card-hd">
                      <div class="fa-history-title">{{ reportCardTitle(report) }}</div>
                      <n-tag size="tiny" :bordered="false" class="fa-history-type-tag">{{ reportTypeLabel(report) }}</n-tag>
                      <div class="fa-history-meta-line">
                        <span>{{ formatReportTime(report.completed_at || report.created_at) }}</span>
                        <span class="fa-history-meta-sep">·</span>
                        <span class="fa-history-code">{{ formatStockCode(report.stock_code) }}</span>
                      </div>
                    </div>

                    <div class="fa-conclusion">
                      <span class="fa-conclusion-badge">
                        <n-icon :size="12" :component="BulbOutline" />
                        <span>研究结论</span>
                      </span>
                      <div class="fa-conclusion-title">{{ conclusion.title || conclusion.sentence }}</div>
                      <div class="fa-conclusion-tags">
                        <n-tag
                          v-for="tag in conclusion.tags"
                          :key="tag"
                          size="tiny"
                          :bordered="false"
                          :type="report.status === 'failed' ? 'error' : 'default'"
                        >{{ tag }}</n-tag>
                      </div>
                      <div class="fa-conclusion-divider" />
                      <div
                        class="fa-conclusion-sentence"
                        :class="{ 'fa-conclusion-sentence--error': report.status === 'failed' }"
                      >{{ conclusion.sentence }}</div>
                    </div>

                    <n-button
                      v-if="report.status === 'completed'"
                      tertiary
                      size="small"
                      class="fa-read-btn"
                      @click="handleViewReport(report)"
                    >
                      <template #icon><n-icon :component="BookOutline" /></template>
                      阅读报告
                    </n-button>

                    <div class="fa-history-actions-row">
                      <IconAction
                        v-if="report.status === 'completed'"
                        label="加入文档库"
                        :icon="FolderOpenOutline"
                        size="tiny"
                        :loading="importingLibraryId === report.id"
                        @click="handleImportLibrary(report)"
                      />
                      <IconAction
                        v-if="report.status === 'completed'"
                        label="分享"
                        :icon="ShareSocialOutline"
                        size="tiny"
                        :active="!!report.share_token"
                        :loading="sharingReportId === report.id"
                        @click="handleShareReport(report)"
                      />
                      <IconAction
                        v-if="report.status === 'completed'"
                        label="下载"
                        :icon="DownloadOutline"
                        size="tiny"
                        @click="handleDownload(report.id, 'md')"
                      />
                      <IconAction
                        label="删除"
                        :icon="CloseCircleOutline"
                        size="tiny"
                        type="error"
                        @click="handleDeleteReport(report.id)"
                      />
                    </div>
                  </div>
                  <div v-if="filteredHistory.length > 1" class="fa-history-pager">
                    <n-pagination
                      v-model:page="historyPage"
                      :page-size="HISTORY_PAGE_SIZE"
                      :item-count="filteredHistory.length"
                      size="small"
                      simple
                    />
                  </div>
                </FeatureSection>
              </div>
            </div>
          </template>

          <!-- ── 实战策略 ── -->
          <template v-if="tab.value === 'strategy'">
            <div class="fa-body fa-body--single">
              <div class="fa-main">
                <FeatureSection title="策略监控">
                  <div class="fa-strategy-grid">
                    <div v-for="plan in strategyPlans" :key="plan.name" class="fa-strategy-card">
                      <div class="fa-strategy-hd">
                        <span class="fa-strategy-name">{{ plan.name }}</span>
                        <span class="fa-strategy-perf">{{ plan.perf }}</span>
                      </div>
                      <div class="fa-strategy-desc">{{ plan.desc }}</div>
                      <div class="fa-strategy-meta">
                        <n-tag size="tiny" :bordered="false">{{ plan.interval }}</n-tag>
                        <n-button size="small" quaternary>运行回测</n-button>
                      </div>
                    </div>
                  </div>
                </FeatureSection>
                <FeatureSection title="持仓监控">
                  <n-empty description="暂无持仓数据" />
                </FeatureSection>
              </div>
            </div>
          </template>

          <!-- ── 因子配置 ── -->
          <template v-if="tab.value === 'factors'">
            <div class="fa-body fa-body--single">
              <div class="fa-main">
                <FeatureSection title="因子开关">
                  <div class="fa-factor-grid">
                    <div v-for="f in factorGroups" :key="f.name" class="fa-factor-card" :class="{ 'fa-factor-card--on': f.enabled }">
                      <div class="fa-factor-top">
                        <span class="fa-factor-name">{{ f.name }}</span>
                        <n-switch :value="f.enabled" size="small" />
                      </div>
                      <div class="fa-factor-desc">{{ f.desc }}</div>
                    </div>
                  </div>
                </FeatureSection>
                <FeatureSection title="组合权重">
                  <div class="fa-factor-weights">
                    <div class="fa-factor-weight-row">
                      <span>动量 30%</span><div class="fa-bar"><div class="fa-bar-fill" style="width:30%" /></div>
                    </div>
                    <div class="fa-factor-weight-row">
                      <span>估值 25%</span><div class="fa-bar"><div class="fa-bar-fill" style="width:25%" /></div>
                    </div>
                    <div class="fa-factor-weight-row">
                      <span>资金 20%</span><div class="fa-bar"><div class="fa-bar-fill" style="width:20%" /></div>
                    </div>
                    <div class="fa-factor-weight-row">
                      <span>情绪 15%</span><div class="fa-bar"><div class="fa-bar-fill" style="width:15%" /></div>
                    </div>
                    <div class="fa-factor-weight-row">
                      <span>波动 10%</span><div class="fa-bar"><div class="fa-bar-fill" style="width:10%" /></div>
                    </div>
                  </div>
                </FeatureSection>
              </div>
            </div>
          </template>

          <!-- ── 断层研究 ── -->
          <template v-if="tab.value === 'gap'">
            <div class="fa-body fa-body--single">
              <div class="fa-main">
                <FeatureSection title="业绩断层扫描">
                  <n-empty description="暂无断层信号">
                    <template #extra>
                      <n-button size="small" tertiary>开始扫描</n-button>
                    </template>
                  </n-empty>
                  <p class="fa-hint">业绩断层指财报发布后跳空缺口不回补。此处将扫描全市场业绩预告/财报并标记跳空缺口。</p>
                </FeatureSection>
                <FeatureSection title="缺口回补跟踪">
                  <n-empty description="暂无跟踪数据" />
                </FeatureSection>
              </div>
            </div>
          </template>
        </n-tab-pane>
      </n-tabs>
    </div>
  </FeatureSubsystemShell>

  <ShareLinkModal
    v-model:show="showShareModal"
    title="分享报告"
    :url="shareModalUrl"
    :shared="!!shareModalUrl"
    :loading="!!sharingReportId"
    hint="链接可公开访问报告内容；重新分享将更新链接，旧链接失效。"
    @generate="generateOrRefreshReportShare(null, { regenerate: true })"
    @reshare="generateOrRefreshReportShare(null, { regenerate: true })"
    @unshare="unshareCurrentReport"
    @copy="copyShareModalUrl"
  />
</template>

<style scoped>
/* 4px 等比间距：1=4 2=8 3=12 4=16 5=20 */
.fa-view {
  --fa-1: 4px;
  --fa-2: 8px;
  --fa-3: 12px;
  --fa-4: 16px;
  --fa-5: 20px;
  --fa-radius: 6px;
  padding: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex: 1;
  height: 100%;
}
.fa-view :deep(.n-tabs) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: visible;
}
.fa-view :deep(.n-tabs-nav) {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--platform-bg);
}
.fa-view :deep(.n-tabs-tab--active),
.fa-view :deep(.n-tabs-tab):hover {
  color: var(--n-tab-text-color);
}
.fa-view :deep(.n-tabs-bar) {
  display: none;
}
.fa-view :deep(.n-tabs .n-tabs-tab-panes) {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.fa-view :deep(.n-tab-pane) {
  height: auto;
  min-height: 100%;
}

.fa-body {
  display: flex;
  gap: var(--fa-4);
  align-items: flex-start;
  min-height: 0;
}
.fa-body--single .fa-side {
  display: none;
}
.fa-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--fa-4);
}
.fa-side {
  width: 320px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: var(--fa-4);
  position: sticky;
  top: 0;
}

.fa-search-wrap {
  position: relative;
}
.fa-search-row {
  display: flex;
  gap: var(--fa-2);
}
.fa-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  margin-top: var(--fa-1);
  background: var(--platform-bg-elevated-solid, #fff);
  border: 1px solid var(--platform-border-strong);
  border-radius: var(--fa-radius);
  max-height: 200px;
  overflow-y: auto;
  z-index: 20;
}
.fa-dropdown-item {
  display: flex;
  align-items: center;
  gap: var(--fa-2);
  padding: var(--fa-2) var(--fa-3);
  cursor: pointer;
}
.fa-dropdown-item:hover {
  background: var(--platform-bg-secondary);
}
.fa-dd-code {
  font-size: 12px;
  color: var(--platform-accent);
  min-width: 72px;
}
.fa-dd-name {
  font-size: 12px;
  color: var(--platform-text);
}

.fa-quick-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--fa-2);
}
.fa-quick-chip {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--fa-1);
  margin: 0;
  padding: var(--fa-2) var(--fa-1);
  border-radius: var(--fa-radius);
  border: 1px solid var(--platform-border-strong);
  background: var(--platform-bg-elevated-solid, #fff);
  cursor: pointer;
  font: inherit;
  color: inherit;
}
.fa-quick-chip:hover,
.fa-quick-chip--active {
  border-color: var(--platform-accent);
  background: var(--platform-accent-soft);
}
.fa-quick-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--platform-text);
  line-height: 1.3;
}
.fa-quick-code {
  font-size: 11px;
  color: var(--platform-text-secondary);
}

.fa-selected-tag {
  font-size: 11px;
  height: 22px;
  line-height: 22px;
  padding: 0 var(--fa-2);
}

.fa-grid-3,
.fa-grid-2 {
  display: grid;
  gap: var(--fa-2);
}
.fa-grid-3 {
  grid-template-columns: repeat(3, 1fr);
}
.fa-grid-2 {
  grid-template-columns: repeat(2, 1fr);
}

.fa-config-section {
  display: flex;
  flex-direction: column;
  gap: var(--fa-3);
}
.fa-config-row {
  display: flex;
  flex-direction: column;
  gap: var(--fa-2);
}
.fa-config-label {
  font-size: 12px;
  color: var(--platform-text-tertiary);
}

.fa-vpa-section {
  display: flex;
  flex-direction: column;
  gap: var(--fa-3);
}
.fa-vpa-intro,
.fa-hint {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--platform-text-secondary);
}
.fa-hint {
  font-size: 11px;
  color: var(--platform-text-tertiary);
}
.fa-vpa-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--fa-2);
}
.fa-vpa-card {
  display: flex;
  gap: var(--fa-2);
  padding: var(--fa-3);
  border-radius: var(--fa-radius);
  border: 1px solid var(--platform-border-strong);
  background: var(--platform-bg-elevated-solid, #fff);
}
.fa-vpa-card-icon {
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--fa-radius);
  color: var(--platform-accent);
  background: var(--platform-accent-soft);
}
.fa-vpa-card-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--fa-1);
}
.fa-vpa-card-title {
  font-size: 12px;
  font-weight: 500;
  color: var(--platform-text);
}
.fa-vpa-card-items {
  font-size: 11px;
  color: var(--platform-text-tertiary);
  line-height: 1.4;
}

.fa-action-bar {
  padding-top: var(--fa-1);
}
.fa-action-btn {
  width: 100%;
}

.fa-strategy-grid {
  display: flex;
  flex-direction: column;
  gap: var(--fa-2);
}
.fa-strategy-card {
  padding: var(--fa-3);
  border-radius: var(--fa-radius);
  border: 1px solid var(--platform-border-strong);
  display: flex;
  flex-direction: column;
  gap: var(--fa-2);
  background: var(--platform-bg-elevated-solid, #fff);
}
.fa-strategy-hd {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.fa-strategy-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--platform-text);
}
.fa-strategy-perf {
  font-size: 12px;
  font-weight: 500;
  color: var(--platform-text-secondary);
}
.fa-strategy-desc {
  font-size: 12px;
  color: var(--platform-text-tertiary);
  line-height: 1.4;
}
.fa-strategy-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.fa-factor-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--fa-2);
}
.fa-factor-card {
  padding: var(--fa-3);
  border-radius: var(--fa-radius);
  border: 1px solid var(--platform-border-strong);
  display: flex;
  flex-direction: column;
  gap: var(--fa-1);
  background: var(--platform-bg-elevated-solid, #fff);
}
.fa-factor-card--on {
  border-color: var(--platform-accent);
  background: var(--platform-accent-soft);
}
.fa-factor-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.fa-factor-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--platform-text);
}
.fa-factor-desc {
  font-size: 11px;
  color: var(--platform-text-tertiary);
}
.fa-factor-weights {
  display: flex;
  flex-direction: column;
  gap: var(--fa-2);
}
.fa-factor-weight-row {
  display: flex;
  align-items: center;
  gap: var(--fa-3);
  font-size: 12px;
  color: var(--platform-text);
}
.fa-bar {
  flex: 1;
  height: 6px;
  border-radius: 3px;
  background: var(--platform-bg-secondary);
  overflow: hidden;
}
.fa-bar-fill {
  height: 100%;
  border-radius: 3px;
  background: var(--platform-accent);
}

.fa-empty {
  padding: var(--fa-5) 0;
  text-align: center;
  font-size: var(--platform-font-size-sm, 12px);
  color: var(--platform-text-tertiary);
}

.fa-task-item {
  padding: var(--fa-2) 0;
  display: flex;
  flex-direction: column;
  gap: var(--fa-2);
}
.fa-task-item + .fa-task-item {
  border-top: 1px solid var(--platform-border);
}
.fa-task-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--fa-2);
}
.fa-task-info {
  display: flex;
  align-items: center;
  gap: var(--fa-2);
  min-width: 0;
  flex-wrap: wrap;
}
.fa-task-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--platform-text);
}
.fa-task-actions {
  display: flex;
  align-items: center;
  gap: var(--fa-2);
  flex-shrink: 0;
}
.fa-progress-circle {
  width: 18px;
  height: 18px;
}
.fa-task-actions :deep(.n-progress-text) {
  font-size: 0;
}
.fa-task-bottom {
  display: flex;
  align-items: center;
  gap: var(--fa-2);
  flex-wrap: wrap;
}
.fa-task-status {
  font-size: 11px;
  color: var(--platform-text-tertiary);
}
.fa-task-step {
  font-size: 11px;
  color: var(--platform-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 180px;
}

.fa-history-search {
  padding: 0 0 var(--fa-1);
}
.fa-history-card {
  display: flex;
  flex-direction: column;
  gap: var(--fa-3);
  padding: var(--fa-3);
  border-radius: var(--fa-radius);
  border: 1px solid var(--platform-border-strong);
  background: var(--platform-bg-elevated-solid, #fff);
}
.fa-history-card-hd {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--fa-2);
}
.fa-history-title {
  font-size: var(--platform-font-size-sm, 12px);
  font-weight: 500;
  color: var(--platform-text);
  line-height: 1.35;
}
.fa-history-type-tag {
  font-size: 11px;
  height: auto;
  line-height: 1.35;
  padding: 2px var(--fa-2);
}
.fa-history-meta-line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--fa-1);
  font-size: 11px;
  color: var(--platform-text-tertiary);
  line-height: 1.4;
}
.fa-history-meta-sep {
  opacity: 0.55;
}
.fa-history-code {
  color: var(--platform-text-secondary);
}

.fa-conclusion {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--fa-2);
  padding: var(--fa-3);
  border-radius: var(--fa-radius);
  background: var(--platform-card-bg, #fcfcfc);
  border: 1px solid var(--platform-border);
}
.fa-conclusion-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--fa-1);
  padding: 2px var(--fa-2);
  border: 1px solid var(--platform-border-strong);
  border-radius: 4px;
  background: var(--platform-accent-soft);
  color: var(--platform-accent);
  font-size: 11px;
  font-weight: 500;
  line-height: 1.3;
}
.fa-conclusion-title {
  font-size: 12px;
  font-weight: 500;
  color: var(--platform-text);
  line-height: 1.45;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.fa-conclusion-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--fa-1);
}
.fa-conclusion-tags :deep(.n-tag) {
  font-size: 10px;
  height: 20px;
}
.fa-conclusion-divider {
  width: 100%;
  height: 1px;
  background: var(--platform-border-strong);
}
.fa-conclusion-sentence {
  width: 100%;
  font-size: 12px;
  line-height: 1.55;
  color: var(--platform-text-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.fa-conclusion-sentence--error {
  color: var(--platform-danger);
}

.fa-read-btn {
  width: 100%;
}
.fa-history-actions-row {
  display: flex;
  align-items: center;
  justify-content: space-around;
  width: 100%;
  max-width: 100%;
  min-width: 0;
  box-sizing: border-box;
  overflow: hidden;
}
.fa-history-actions-row :deep(.n-tooltip) {
  flex: 0 0 auto;
  max-width: 100%;
}
.fa-history-actions-row :deep(.icon-action) {
  width: 28px !important;
  height: 28px !important;
  flex-shrink: 0;
}
.fa-history-pager {
  display: flex;
  justify-content: center;
  padding-top: var(--fa-2);
  border-top: 1px solid var(--platform-border);
  margin-top: var(--fa-1);
}

@media (max-width: 820px) {
  .fa-body {
    flex-direction: column;
  }
  .fa-side {
    width: auto;
    position: static;
  }
  .fa-factor-grid {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 600px) {
  .fa-grid-3 {
    grid-template-columns: 1fr;
  }
  .fa-vpa-grid {
    grid-template-columns: 1fr;
  }
}
</style>
