<script setup>
import { ref, computed, watch } from "vue";
import {
  DownloadOutline,
  CloseCircleOutline,
  BookOutline,
  BulbOutline,
} from "@vicons/ionicons5";
import FeatureSection from "../FeatureSection.vue";
import IconAction from "../IconAction.vue";
import { usePlatformUi } from "../../composables/usePlatformUi";
import { useI18n } from "../../composables/useI18n";
import { useAuth } from "../../composables/useAuth";
import {
  submitCarbonReport,
  fetchCarbonReports,
  cancelCarbonReport,
  deleteCarbonReport,
  viewCarbonReport,
  downloadCarbonReport,
} from "../../api/carbonAssistant";

const props = defineProps({
  selectedId: { type: String, default: "" },
  selected: { type: Object, default: null },
  enterpriseLabel: { type: Function, required: true },
});

const complianceYear = defineModel("complianceYear", { type: Number, required: true });
const forecastMethod = defineModel("forecastMethod", { type: String, default: "rule" });

const ui = usePlatformUi();
const { t } = useI18n();
const { isSystemAdmin } = useAuth();

/** 与后端报告 Markdown 结构对齐的中文标签（仅用于解析匹配） */
const CONCLUSION_MATCH_TAGS = ["履约缺口", "策略建议", "分析预警", "政策要点"];
const TAG_I18N = {
  履约缺口: "carbonAssistant.tagGap",
  策略建议: "carbonAssistant.tagStrategy",
  分析预警: "carbonAssistant.tagAlert",
  政策要点: "carbonAssistant.tagPolicy",
  配额盈余: "carbonAssistant.tagSurplus",
  结转风险: "carbonAssistant.tagCarryRisk",
};

const submitting = ref(false);
const runningTasks = ref([]);
const completedReports = ref([]);
const historySearchQuery = ref("");
const historyPage = ref(1);
const HISTORY_PAGE_SIZE = 1;
const POLL_INTERVAL = 3000;
let pollTimer = null;

function displayTag(tag) {
  const key = TAG_I18N[tag];
  return key ? t(key) : tag;
}

function defaultConclusionTags() {
  return CONCLUSION_MATCH_TAGS.map(displayTag);
}

function reportTypeLabel(report) {
  const map = {
    compliance_analysis: t("carbonAssistant.reportTypeCompliance"),
    market_brief: t("carbonAssistant.reportTypeMarket"),
    policy_digest: t("carbonAssistant.reportTypePolicy"),
  };
  return map[report?.report_type] || report?.report_type || t("carbonAssistant.reportFallback");
}

function reportCardTitle(report) {
  const subject = (report?.subject || "").trim() || t("carbonAssistant.entityFallback");
  if (report?.target_year) {
    return t("carbonAssistant.reportCardTitle", { subject, year: report.target_year });
  }
  return t("carbonAssistant.reportCardTitleNoYear", { subject });
}

function formatReportTime(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return String(iso);
  }
}

function statusLabel(s) {
  return (
    {
      pending: t("carbonAssistant.statusPending"),
      running: t("carbonAssistant.statusRunning"),
      completed: t("carbonAssistant.statusCompleted"),
      failed: t("carbonAssistant.statusFailed"),
      cancelled: t("carbonAssistant.statusCancelled"),
    }[s] || s || "—"
  );
}

function stripInlineMarkdown(text) {
  return String(text || "")
    .replace(/!\[[^\]]*]\([^)]*\)/g, "")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/__([^_]+)__/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/_([^_]+)_/g, "$1")
    .replace(/~~([^~]+)~~/g, "$1")
    .replace(/^\s{0,3}#{1,6}\s+/gm, "")
    .replace(/\s+/g, " ")
    .trim();
}

function parseReportConclusion(content) {
  const empty = { tags: defaultConclusionTags(), title: "", sentence: "" };
  const raw = String(content || "").trim();
  if (!raw) return empty;
  const sectionMatch = raw.match(
    /(?:^|\n)#{1,3}\s*先看结论\s*\n([\s\S]*?)(?=\n#{1,3}\s|\n---\s*$|$)/
  );
  let block = (sectionMatch?.[1] || raw).trim();
  block = block.replace(/^(?:#{1,3}\s*先看结论\s*\n+)+/i, "").trim();
  if (/正在生成 AI|结论将在/.test(block)) {
    return {
      tags: defaultConclusionTags(),
      title: "",
      sentence: t("carbonAssistant.conclusionGenerating"),
    };
  }
  const lines = block.split(/\n+/).map((l) => l.trim()).filter(Boolean);
  let sentence = "";
  const foundTags = [];
  for (const line of lines) {
    if (/^#{1,3}\s/.test(line)) continue;
    const bullet = line.match(/^[-*•]\s*(.+)$/);
    const item = stripInlineMarkdown(
      bullet ? bullet[1] : line.replace(/^>\s*/, "")
    );
    if (!item) continue;
    for (const label of CONCLUSION_MATCH_TAGS) {
      if (label === "履约缺口" && /无缺口|无履约缺口/.test(item)) continue;
      if (item.includes(label) && !foundTags.includes(label)) foundTags.push(label);
    }
    if (!sentence && item.length >= 10 && !/^\|/.test(item)) sentence = item;
  }
  const full = sentence || t("carbonAssistant.conclusionReady");
  let tags = foundTags;
  if (!tags.length) {
    if (/配额盈余|无缺口|盈余企业/.test(full)) {
      tags = ["配额盈余", "策略建议", "结转风险"];
    } else {
      tags = [...CONCLUSION_MATCH_TAGS];
    }
  }
  return {
    tags: tags.map(displayTag),
    title: "",
    sentence: full,
  };
}

const filteredHistory = computed(() => {
  let list = completedReports.value.filter((r) => r.status !== "cancelled");
  const q = historySearchQuery.value.trim().toLowerCase();
  if (q) {
    list = list.filter(
      (r) =>
        (r.subject || "").toLowerCase().includes(q) ||
        (r.target_year || "").toLowerCase().includes(q) ||
        (r.report_type || "").toLowerCase().includes(q) ||
        (r.industry || "").toLowerCase().includes(q) ||
        (r.owner_name || "").toLowerCase().includes(q)
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
            tags: defaultConclusionTags(),
            title: t("carbonAssistant.taskFailed"),
            sentence: report.error_message || t("carbonAssistant.taskFailed"),
          }
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

function stopPolling() {
  if (pollTimer != null) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
}

function startPolling() {
  stopPolling();
  pollTimer = setTimeout(pollTasks, POLL_INTERVAL);
}

async function fetchAllReports() {
  try {
    const items = (await fetchCarbonReports({ reportType: "compliance_analysis", limit: 100 })) || [];
    const prevRunningIds = new Set(runningTasks.value.map((r) => r.id));
    runningTasks.value = items.filter((r) => r.status === "pending" || r.status === "running");
    completedReports.value = items.filter((r) => r.status !== "pending" && r.status !== "running");
    for (const id of prevRunningIds) {
      if (runningTasks.value.some((r) => r.id === id)) continue;
      const done = completedReports.value.find((r) => r.id === id);
      if (!done) continue;
      const title = reportCardTitle(done);
      if (done.status === "completed") {
        ui.success(t("carbonAssistant.reportGenerated", { title }));
      } else if (done.status === "failed") {
        ui.error(done.error_message || t("carbonAssistant.reportFailed", { title }));
      }
    }
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

async function startAnalysis() {
  if (!props.selectedId) return ui.warning(t("carbonAssistant.selectEntityWarn"));
  if (submitting.value) return;
  submitting.value = true;
  try {
    const subject = props.enterpriseLabel(props.selected) || t("carbonAssistant.entityFallback");
    await submitCarbonReport({
      subject: subject.slice(0, 120),
      report_type: "compliance_analysis",
      industry: props.selected?.industry || "",
      target_year: String(complianceYear.value),
      ai_context: JSON.stringify({
        enterprise_id: props.selectedId,
        compliance_year: Number(complianceYear.value),
        forecast_method: forecastMethod.value || "rule",
      }),
    });
    ui.success(
      runningTasks.value.length
        ? t("carbonAssistant.taskAppended")
        : t("carbonAssistant.taskSubmitted")
    );
    await fetchAllReports();
    startPolling();
  } catch (e) {
    ui.error(e?.message || t("carbonAssistant.submitFailed"));
  } finally {
    submitting.value = false;
  }
}

async function handleCancelTask(taskId) {
  try {
    await cancelCarbonReport(taskId);
    ui.success(t("carbonAssistant.cancelOk"));
    await fetchAllReports();
  } catch (e) {
    ui.error(e?.message || t("carbonAssistant.cancelFailed"));
  }
}

async function handleDeleteReport(reportId) {
  ui.confirmDelete({
    title: t("carbonAssistant.deleteConfirmTitle"),
    content: t("carbonAssistant.deleteConfirmContent"),
    positiveText: t("carbonAssistant.deleteConfirmOk"),
    onPositive: async () => {
      await deleteCarbonReport(reportId);
      ui.success(t("carbonAssistant.deleted"));
      await fetchAllReports();
    },
  });
}

async function handleViewReport(report) {
  try {
    await viewCarbonReport(report.id, report.share_token);
  } catch (e) {
    ui.error(e?.message || t("carbonAssistant.openReportFailed"));
  }
}

async function handleDownloadReport(reportId) {
  try {
    await downloadCarbonReport(reportId);
  } catch (e) {
    ui.error(e?.message || t("carbonAssistant.downloadFailed"));
  }
}

defineExpose({
  fetchAllReports,
  startPolling,
  stopPolling,
  startAnalysis,
  submitting,
  runningTaskCount: computed(() => runningTasks.value.length),
  hasRunningTasks: () => runningTasks.value.length > 0,
});
</script>

<template>
  <div class="cc-side">
    <FeatureSection :title="t('carbonAssistant.runningTasks')" dense>
      <template #extra>
        <n-tag v-if="runningTasks.length" size="tiny" :bordered="false" round>
          {{ runningTasks.length }}
        </n-tag>
      </template>
      <div v-if="!runningTasks.length" class="cc-empty">{{ t("carbonAssistant.noRunningTasks") }}</div>
      <div v-for="task in runningTasks" :key="task.id" class="cc-task-item">
        <div class="cc-task-top">
          <div class="cc-task-info">
            <span class="cc-task-name">{{ task.subject }}</span>
            <n-tag size="tiny" :bordered="false">{{ reportTypeLabel(task) }}</n-tag>
          </div>
          <div class="cc-task-actions">
            <n-progress
              type="circle"
              status="default"
              :percentage="task.progress || 0"
              :stroke-width="8"
              :show-indicator="false"
              class="cc-progress-circle"
            />
            <n-button size="small" quaternary circle type="error" @click="handleCancelTask(task.id)">
              <template #icon><n-icon :component="CloseCircleOutline" :size="14" /></template>
            </n-button>
          </div>
        </div>
        <div class="cc-task-bottom">
          <span class="cc-task-status">{{ statusLabel(task.status) }}</span>
          <span v-if="isSystemAdmin && task.owner_name" class="cc-task-owner">{{ task.owner_name }}</span>
          <span v-if="task.error_message && task.status === 'running'" class="cc-task-step">
            {{ task.error_message }}
          </span>
        </div>
      </div>
    </FeatureSection>

    <FeatureSection :title="t('carbonAssistant.historyReports')" dense>
      <template v-if="isSystemAdmin" #extra>
        <n-tag size="tiny" :bordered="false" type="info">{{ t("carbonAssistant.historyAllUsers") }}</n-tag>
      </template>
      <div class="cc-history-search">
        <n-input
          v-model:value="historySearchQuery"
          :placeholder="isSystemAdmin ? t('carbonAssistant.historySearchAdmin') : t('carbonAssistant.historySearch')"
          size="tiny"
          clearable
        />
      </div>
      <div v-if="!filteredHistory.length" class="cc-empty">{{ t("carbonAssistant.noHistoryReports") }}</div>
      <div v-for="{ report, conclusion } in pagedHistoryCards" :key="report.id" class="cc-history-card">
        <div class="cc-history-card-hd">
          <div class="cc-history-title">{{ reportCardTitle(report) }}</div>
          <n-tag size="tiny" :bordered="false" class="cc-history-type-tag">
            {{ reportTypeLabel(report) }}
          </n-tag>
          <div class="cc-history-meta-line">
            <span>{{ formatReportTime(report.completed_at || report.created_at) }}</span>
            <span class="cc-history-meta-sep">·</span>
            <span>{{ report.target_year || "—" }}</span>
            <template v-if="isSystemAdmin && report.owner_name">
              <span class="cc-history-meta-sep">·</span>
              <span>{{ report.owner_name }}</span>
            </template>
          </div>
        </div>

        <div class="cc-conclusion">
          <span class="cc-conclusion-badge">
            <n-icon :size="12" :component="BulbOutline" />
            <span>{{ t("carbonAssistant.conclusionBadge") }}</span>
          </span>
          <div class="cc-conclusion-tags">
            <n-tag
              v-for="tag in conclusion.tags"
              :key="tag"
              size="tiny"
              :bordered="false"
              :type="report.status === 'failed' ? 'error' : 'default'"
            >
              {{ tag }}
            </n-tag>
          </div>
          <div class="cc-conclusion-divider" />
          <div
            class="cc-conclusion-sentence"
            :class="{ 'cc-conclusion-sentence--error': report.status === 'failed' }"
          >
            {{ conclusion.sentence }}
          </div>
        </div>

        <n-button
          v-if="report.status === 'completed'"
          tertiary
          size="small"
          class="cc-read-btn"
          @click="handleViewReport(report)"
        >
          <template #icon><n-icon :component="BookOutline" /></template>
          {{ t("carbonAssistant.readReport") }}
        </n-button>

        <div class="cc-history-actions-row">
          <IconAction
            v-if="report.status === 'completed'"
            :label="t('carbonAssistant.download')"
            :icon="DownloadOutline"
            size="tiny"
            @click="handleDownloadReport(report.id)"
          />
          <IconAction
            :label="t('carbonAssistant.delete')"
            :icon="CloseCircleOutline"
            size="tiny"
            type="error"
            @click="handleDeleteReport(report.id)"
          />
        </div>
      </div>
      <div v-if="filteredHistory.length > HISTORY_PAGE_SIZE" class="cc-history-pager">
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
</template>
