<script setup>
defineOptions({ name: "CarbonAssistantView" });
import { ref, watch, onMounted, onUnmounted, onActivated, onDeactivated, computed, nextTick, h } from "vue";
import {
  AddOutline,
  DownloadOutline,
  RefreshOutline,
  CloseCircleOutline,
  BookOutline,
  BulbOutline,
  HelpCircleOutline,
  CreateOutline,
  TrashOutline,
} from "@vicons/ionicons5";
import { usePlatformUi } from "../composables/usePlatformUi";
import { useAuth } from "../composables/useAuth";
import { useCarbonEnterprise, carbonPageCache } from "../composables/useCarbonEnterprise";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import FeatureSection from "../components/FeatureSection.vue";
import IconAction from "../components/IconAction.vue";
import FieldHelp from "../components/FieldHelp.vue";
import CarbonCeaQuoteChart from "../components/CarbonCeaQuoteChart.vue";
import { openExternal } from "../utils/openExternal.js";
import {
  listEmissions,
  upsertEmission,
  deleteEmission,
  listCea,
  upsertCea,
  deleteCea,
  listCcer,
  upsertCcer,
  deleteCcer,
  fetchCarbonSettings,
  updateCarbonSettings,
  downloadImportTemplate,
  importEnterpriseExcel,
  syncMarketQuotes,
} from "../api/carbonCompliance";
import {
  submitCarbonReport,
  fetchCarbonReports,
  cancelCarbonReport,
  deleteCarbonReport,
  viewCarbonReport,
  downloadCarbonReport,
} from "../api/carbonAssistant";
import { isRouteAbortError } from "../api/http.js";

const ui = usePlatformUi();
const { isSystemAdmin } = useAuth();
const marketChartRef = ref(null);
const {
  enterprises,
  selectedId,
  selected,
  meta,
  loadMeta,
  loadEnterprises,
  saveEnterprise,
  removeEnterprise,
} = useCarbonEnterprise();
const complianceYear = ref(new Date().getFullYear());

const form = ref(emptyEnterpriseForm());
const editingId = ref("");
const saving = ref(false);

function emptyEnterpriseForm() {
  return {
    name: "",
    uscc: "",
    industry: "power",
    market_start_year: 2021,
    compliance_cycle: "annual",
    risk_profile: "balanced",
    annual_budget_cap: 5000000,
  };
}

function enterpriseLabel(ent) {
  if (!ent) return "";
  if ((ent.name || "").trim()) return ent.name.trim();
  const ind =
    (meta.value.industries || []).find((x) => x.value === ent.industry)?.label ||
    ent.industry ||
    "主体";
  const risk =
    (meta.value.risk_profiles || []).find((x) => x.value === ent.risk_profile)?.label ||
    ent.risk_profile ||
    "";
  const shortId = String(ent.id || "").slice(0, 8);
  return `${ind} · ${risk} · ${shortId}`;
}

function startCreate() {
  editingId.value = "";
  form.value = emptyEnterpriseForm();
}

function startEdit(ent) {
  editingId.value = ent.id;
  form.value = {
    name: ent.name || "",
    uscc: ent.uscc || "",
    industry: ent.industry,
    market_start_year: ent.market_start_year,
    compliance_cycle: ent.compliance_cycle || "annual",
    risk_profile: ent.risk_profile,
    annual_budget_cap: ent.annual_budget_cap,
  };
}

async function handleSaveEnterprise() {
  if (!(form.value.name || "").trim()) {
    ui.warning("请填写企业名称");
    return;
  }
  if (!form.value.industry) {
    ui.warning("请选择控排行业");
    return;
  }
  saving.value = true;
  try {
    await saveEnterprise(
      { ...form.value, single_trade_limit: 0 },
      editingId.value || null
    );
    ui.success(editingId.value ? "已更新" : "已创建");
    startCreate();
  } catch (e) {
    ui.error(e?.message || "保存失败");
  } finally {
    saving.value = false;
  }
}

async function handleDeleteEnterprise(id) {
  ui.confirmDelete({
    title: "删除企业",
    content: "确定删除该企业及其台账数据？",
    onPositive: async () => {
      await removeEnterprise(id);
      ui.success("已删除");
    },
  });
}

// ── 排放与资产（数量单位：万吨，与库内一致）──
function fmtWanCell(v) {
  if (v == null || v === "") return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return n;
}

const emissions = ref([]);
const ceaRows = ref([]);
const ccerRows = ref([]);

function emptyEmissionForm() {
  return {
    year: new Date().getFullYear(),
    scope1_process: 0,
    scope1_combustion: 0,
    verified_total: null,
  };
}
function emptyCeaForm() {
  return {
    vintage_year: new Date().getFullYear(),
    free_quota: 0,
    carry_forward_qty: 0,
    net_sell_qty: 0,
    avg_cost: 0,
    sellable_cap: null,
  };
}
function emptyCcerForm() {
  return {
    id: null,
    project_type: "wind",
    issue_year: new Date().getFullYear() - 1,
    expire_at: "2030-12-31",
    qty: 0,
    cost: 0,
    eligible_qty: null,
  };
}

const emissionForm = ref(emptyEmissionForm());
const ceaForm = ref(emptyCeaForm());
const ccerForm = ref(emptyCcerForm());
const showEmissionModal = ref(false);
const showCeaModal = ref(false);
const showCcerModal = ref(false);
const emissionModalMode = ref("create"); // create | edit
const ceaModalMode = ref("create");
const ccerModalMode = ref("create");
const assetSaving = ref(false);
const assetsLoading = ref(false);
const importInput = ref(null);

async function loadAssets() {
  if (!selectedId.value) {
    emissions.value = [];
    ceaRows.value = [];
    ccerRows.value = [];
    return;
  }
  assetsLoading.value = true;
  try {
    const id = selectedId.value;
    const [em, cea, ccer] = await Promise.all([
      listEmissions(id),
      listCea(id),
      listCcer(id),
    ]);
    emissions.value = em || [];
    ceaRows.value = cea || [];
    ccerRows.value = ccer || [];
  } catch (e) {
    if (!isRouteAbortError(e)) ui.error(e?.message || "加载台账失败");
  } finally {
    assetsLoading.value = false;
  }
}

function openCreateEmission() {
  emissionModalMode.value = "create";
  emissionForm.value = emptyEmissionForm();
  showEmissionModal.value = true;
}

function editEmission(row) {
  emissionModalMode.value = "edit";
  emissionForm.value = {
    year: Number(row.year) || new Date().getFullYear(),
    scope1_process: Number(row.scope1_process) || 0,
    scope1_combustion: Number(row.scope1_combustion) || 0,
    verified_total: row.verified_total == null ? null : Number(row.verified_total),
  };
  showEmissionModal.value = true;
}

async function saveEmission() {
  if (!selectedId.value) return ui.warning("请先选择企业");
  assetSaving.value = true;
  try {
    await upsertEmission(selectedId.value, {
      year: emissionForm.value.year,
      scope1_combustion: Number(emissionForm.value.scope1_combustion) || 0,
      scope1_process: Number(emissionForm.value.scope1_process) || 0,
      // 履约核查仅 Scope1；Scope2 字段保留兼容，入库清零
      scope2_power: 0,
      purchased_mwh: 0,
      verified_total:
        emissionForm.value.verified_total === "" || emissionForm.value.verified_total == null
          ? null
          : Number(emissionForm.value.verified_total),
    });
    ui.success("排放数据已保存");
    showEmissionModal.value = false;
    await loadAssets();
  } catch (e) {
    ui.error(e?.message || "保存失败");
  } finally {
    assetSaving.value = false;
  }
}

async function handleDeleteEmission(row) {
  const year = row?.year;
  if (!selectedId.value || year == null) return;
  ui.confirmDelete({
    title: "删除核查排放",
    content: `确定删除 ${year} 年核查排放记录？删除后无法恢复。`,
    onPositive: async () => {
      try {
        await deleteEmission(selectedId.value, year);
        ui.success("已删除");
        await loadAssets();
      } catch (e) {
        ui.error(e?.message || "删除失败");
      }
    },
  });
}

const emissionColumns = [
  { title: "年", key: "year", width: 64 },
  {
    title: "S1工艺",
    key: "scope1_process",
    render: (row) => fmtWanCell(row.scope1_process),
  },
  {
    title: "S1燃烧",
    key: "scope1_combustion",
    render: (row) => fmtWanCell(row.scope1_combustion),
  },
  {
    title: "核查总量",
    key: "verified_total",
    render: (row) => fmtWanCell(row.verified_total),
  },
  {
    title: "",
    key: "actions",
    width: 72,
    render(row) {
      return h("div", { class: "cc-table-actions" }, [
        h(IconAction, {
          label: "编辑",
          icon: CreateOutline,
          variant: "table",
          onClick: () => editEmission(row),
        }),
        h(IconAction, {
          label: "删除",
          icon: TrashOutline,
          variant: "table",
          type: "error",
          onClick: () => handleDeleteEmission(row),
        }),
      ]);
    },
  },
];

function openCreateCea() {
  ceaModalMode.value = "create";
  ceaForm.value = emptyCeaForm();
  showCeaModal.value = true;
}

function editCea(row) {
  ceaModalMode.value = "edit";
  ceaForm.value = {
    vintage_year: Number(row.vintage_year) || new Date().getFullYear(),
    free_quota: Number(row.free_quota) || 0,
    carry_forward_qty: Number(row.carry_forward_qty) || 0,
    net_sell_qty: Number(row.net_sell_qty) || 0,
    avg_cost: Number(row.avg_cost) || 0,
    sellable_cap: row.sellable_cap == null ? null : Number(row.sellable_cap),
  };
  showCeaModal.value = true;
}

async function saveCea() {
  if (!selectedId.value) return ui.warning("请先选择企业");
  assetSaving.value = true;
  try {
    await upsertCea(selectedId.value, {
      vintage_year: ceaForm.value.vintage_year,
      free_quota: Number(ceaForm.value.free_quota) || 0,
      carry_forward_qty: Number(ceaForm.value.carry_forward_qty) || 0,
      net_sell_qty: Number(ceaForm.value.net_sell_qty) || 0,
      avg_cost: Number(ceaForm.value.avg_cost) || 0,
      sellable_cap:
        ceaForm.value.sellable_cap === "" || ceaForm.value.sellable_cap == null
          ? null
          : Number(ceaForm.value.sellable_cap),
    });
    ui.success("CEA 台账已保存");
    showCeaModal.value = false;
    await loadAssets();
  } catch (e) {
    ui.error(e?.message || "保存失败");
  } finally {
    assetSaving.value = false;
  }
}

async function handleDeleteCea(row) {
  const year = row?.vintage_year;
  if (!selectedId.value || year == null) return;
  ui.confirmDelete({
    title: "删除 CEA 台账",
    content: `确定删除 ${year} 年 CEA 配额记录？删除后无法恢复。`,
    onPositive: async () => {
      try {
        await deleteCea(selectedId.value, year);
        ui.success("已删除");
        await loadAssets();
      } catch (e) {
        ui.error(e?.message || "删除失败");
      }
    },
  });
}

const ceaColumns = [
  { title: "年度", key: "vintage_year", width: 64 },
  { title: "免费配额", key: "free_quota", render: (row) => fmtWanCell(row.free_quota) },
  { title: "结转量", key: "carry_forward_qty", render: (row) => fmtWanCell(row.carry_forward_qty) },
  {
    title: "可用合计",
    key: "usable",
    render: (row) =>
      fmtWanCell((Number(row.free_quota) || 0) + (Number(row.carry_forward_qty) || 0)),
  },
  { title: "净卖出", key: "net_sell_qty", render: (row) => fmtWanCell(row.net_sell_qty) },
  { title: "可售上限", key: "sellable_cap", render: (row) => fmtWanCell(row.sellable_cap) },
  {
    title: "",
    key: "actions",
    width: 72,
    render(row) {
      return h("div", { class: "cc-table-actions" }, [
        h(IconAction, {
          label: "编辑",
          icon: CreateOutline,
          variant: "table",
          onClick: () => editCea(row),
        }),
        h(IconAction, {
          label: "删除",
          icon: TrashOutline,
          variant: "table",
          type: "error",
          onClick: () => handleDeleteCea(row),
        }),
      ]);
    },
  },
];

function openCreateCcer() {
  ccerModalMode.value = "create";
  ccerForm.value = emptyCcerForm();
  showCcerModal.value = true;
}

function editCcer(row) {
  const qty = Number(row.qty) || 0;
  let eligible = Number(row.eligible_qty);
  if (!Number.isFinite(eligible) || (eligible <= 0 && qty > 0)) eligible = qty;
  if (qty > 0) eligible = Math.min(eligible, qty);
  ccerModalMode.value = "edit";
  ccerForm.value = {
    id: row.id || null,
    project_type: row.project_type || "wind",
    issue_year: Number(row.issue_year) || new Date().getFullYear() - 1,
    expire_at: String(row.expire_at || "2030-12-31").slice(0, 10),
    qty,
    cost: Number(row.cost) || 0,
    eligible_qty: eligible,
  };
  showCcerModal.value = true;
}

async function saveCcer() {
  if (!selectedId.value) return ui.warning("请先选择企业");
  assetSaving.value = true;
  try {
    const qty = Number(ccerForm.value.qty) || 0;
    let eligible =
      ccerForm.value.eligible_qty === "" || ccerForm.value.eligible_qty == null
        ? qty
        : Number(ccerForm.value.eligible_qty);
    if (!Number.isFinite(eligible)) eligible = qty;
    // 可抵扣未填或为 0 时回退持有量；且不得超过持有存量
    if (eligible <= 0 && qty > 0) eligible = qty;
    eligible = Math.min(Math.max(0, eligible), qty || eligible);
    const payload = {
      project_type: ccerForm.value.project_type,
      issue_year: ccerForm.value.issue_year,
      expire_at: ccerForm.value.expire_at,
      qty,
      cost: Number(ccerForm.value.cost) || 0,
      eligible_qty: eligible,
      linked_green_cert: false,
    };
    if (ccerForm.value.id) payload.id = ccerForm.value.id;
    await upsertCcer(selectedId.value, payload);
    ui.success("CCER 台账已保存");
    showCcerModal.value = false;
    await loadAssets();
  } catch (e) {
    ui.error(e?.message || "保存失败");
  } finally {
    assetSaving.value = false;
  }
}

async function handleDeleteCcer(row) {
  const id = row?.id;
  if (!selectedId.value || !id) return;
  const label = `${row.project_type || "CCER"} / ${row.issue_year || "—"}`;
  ui.confirmDelete({
    title: "删除 CCER 台账",
    content: `确定删除「${label}」记录？删除后无法恢复。`,
    onPositive: async () => {
      try {
        await deleteCcer(selectedId.value, id);
        ui.success("已删除");
        await loadAssets();
      } catch (e) {
        ui.error(e?.message || "删除失败");
      }
    },
  });
}

const ccerColumns = [
  { title: "类型", key: "project_type" },
  { title: "签发年", key: "issue_year", width: 64 },
  { title: "存量", key: "qty", render: (row) => fmtWanCell(row.qty) },
  { title: "可抵扣", key: "eligible_qty", render: (row) => fmtWanCell(row.eligible_qty) },
  {
    title: "",
    key: "actions",
    width: 72,
    render(row) {
      return h("div", { class: "cc-table-actions" }, [
        h(IconAction, {
          label: "编辑",
          icon: CreateOutline,
          variant: "table",
          onClick: () => editCcer(row),
        }),
        h(IconAction, {
          label: "删除",
          icon: TrashOutline,
          variant: "table",
          type: "error",
          onClick: () => handleDeleteCcer(row),
        }),
      ]);
    },
  },
];

async function handleDownloadTemplate() {
  if (!selectedId.value) return ui.warning("请先选择企业");
  try {
    await downloadImportTemplate(selectedId.value);
  } catch (e) {
    ui.error(e?.message || "下载失败");
  }
}

async function handleImportFile(e) {
  const file = e?.target?.files?.[0];
  if (!file || !selectedId.value) return;
  try {
    const counts = await importEnterpriseExcel(selectedId.value, file);
    ui.success(
      `导入完成：排放 ${counts.emissions} / CEA ${counts.cea} / CCER ${counts.ccer}`
    );
    await loadAssets();
  } catch (err) {
    ui.error(err?.message || "导入失败");
  } finally {
    if (importInput.value) importInput.value.value = "";
  }
}

// ── 市场与规则 ──
const settingsForm = ref(emptySettingsForm());
const settingsSaving = ref(false);
const lastSyncInfo = ref("");
const profileKeys = [
  { key: "conservative", label: "保守" },
  { key: "balanced", label: "平衡" },
  { key: "aggressive", label: "进取" },
];

function emptySettingsForm() {
  return {
    ccer_max_ratio: 0.05,
    price_low_percentile: 0.3,
    price_mid_percentile: 0.7,
    clearance_warn_days: "90,30,15",
    carry_forward_deadline_md: "06-10",
    carry_base_qty: 0,
    carry_net_sell_multiplier: 1.5,
    prefer_offline: true,
    offline_discount_vs_listed: 0.03,
    listing_fee_rate: 0,
    block_fee_rate: 0,
    overdue_penalty_per_t: 200,
    profiles: {
      conservative: {
        allow_stockpile: false,
        allow_sell_surplus: false,
        allow_buy_external_ccer: false,
      },
      balanced: {
        allow_stockpile: false,
        allow_sell_surplus: true,
        allow_buy_external_ccer: true,
      },
      aggressive: {
        allow_stockpile: true,
        allow_sell_surplus: true,
        allow_buy_external_ccer: true,
      },
    },
  };
}

function settingsToForm(settings) {
  const s = settings || {};
  const c = s.compliance || {};
  const ch = s.channel || {};
  const cost = s.cost || {};
  const profiles = s.strategy_profiles || {};
  const base = emptySettingsForm();
  const mergeProfile = (key) => ({
    ...base.profiles[key],
    ...(profiles[key] || {}),
  });
  return {
    ccer_max_ratio: Number(c.ccer_max_ratio ?? base.ccer_max_ratio),
    price_low_percentile: Number(c.price_low_percentile ?? base.price_low_percentile),
    price_mid_percentile: Number(c.price_mid_percentile ?? base.price_mid_percentile),
    clearance_warn_days: Array.isArray(c.clearance_warn_days)
      ? c.clearance_warn_days.join(",")
      : String(c.clearance_warn_days || base.clearance_warn_days),
    carry_forward_deadline_md: String(
      c.carry_forward_deadline_md || base.carry_forward_deadline_md
    ),
    carry_base_qty: Number(c.carry_base_qty ?? base.carry_base_qty),
    carry_net_sell_multiplier: Number(
      c.carry_net_sell_multiplier ?? base.carry_net_sell_multiplier
    ),
    prefer_offline: ch.prefer_offline !== false,
    offline_discount_vs_listed: Number(
      ch.offline_discount_vs_listed ?? base.offline_discount_vs_listed
    ),
    listing_fee_rate: Number(
      cost.listing_fee_rate ?? cost.trade_fee_rate ?? base.listing_fee_rate
    ),
    block_fee_rate: Number(
      cost.block_fee_rate ?? cost.trade_fee_rate ?? base.block_fee_rate
    ),
    overdue_penalty_per_t: Number(cost.overdue_penalty_per_t ?? base.overdue_penalty_per_t),
    profiles: {
      conservative: mergeProfile("conservative"),
      balanced: mergeProfile("balanced"),
      aggressive: mergeProfile("aggressive"),
    },
  };
}

function formToSettingsPayload(form) {
  const warnDays = String(form.clearance_warn_days || "")
    .split(/[,，\s]+/)
    .map((x) => Number(x))
    .filter((n) => Number.isFinite(n) && n > 0);
  return {
    compliance: {
      ccer_max_ratio: Number(form.ccer_max_ratio),
      price_low_percentile: Number(form.price_low_percentile),
      price_mid_percentile: Number(form.price_mid_percentile),
      clearance_warn_days: warnDays.length ? warnDays : [90, 30, 15],
      carry_forward_deadline_md: String(form.carry_forward_deadline_md || "06-10"),
      carry_base_qty: Number(form.carry_base_qty) || 0,
      carry_net_sell_multiplier: Number(form.carry_net_sell_multiplier) || 1.5,
    },
    channel: {
      prefer_offline: !!form.prefer_offline,
      offline_discount_vs_listed: Number(form.offline_discount_vs_listed),
    },
    cost: {
      listing_fee_rate: Number(form.listing_fee_rate),
      block_fee_rate: Number(form.block_fee_rate),
      overdue_penalty_per_t: Number(form.overdue_penalty_per_t),
    },
    strategy_profiles: {
      conservative: { ...form.profiles.conservative },
      balanced: { ...form.profiles.balanced },
      aggressive: { ...form.profiles.aggressive },
    },
  };
}

const marketSourceTick = ref(0);
const marketSourceLines = computed(() => {
  marketSourceTick.value;
  return marketChartRef.value?.getSourceLines?.() || [];
});

/** 初始化中：避免 selectedId 赋值触发重复拉台账 */
let bootstrapping = false;

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

async function loadMarket({ autoSync = false, force = false } = {}) {
  try {
    let settings = carbonPageCache.settings;
    if (!settings || force) {
      settings = await fetchCarbonSettings();
      carbonPageCache.settings = settings;
    }
    settingsForm.value = settingsToForm(settings);
    const syncMeta = settings?.integrations || {};
    lastSyncInfo.value = syncMeta.last_sync_at
      ? `上次同步：${syncMeta.last_sync_at}${syncMeta.last_sync_ok === false ? "（部分失败）" : ""}`
      : "尚未自动同步";
    if (autoSync && !syncMeta.last_sync_at) {
      await handleSyncMarket({ silent: true });
    }
    await refreshCharts();
  } catch (e) {
    if (!isRouteAbortError(e)) ui.error(e?.message || "加载市场数据失败");
  }
}

async function onMarketSynced() {
  try {
    const settings = await fetchCarbonSettings();
    carbonPageCache.settings = settings;
    const syncMeta = settings?.integrations || {};
    lastSyncInfo.value = syncMeta.last_sync_at
      ? `上次同步：${syncMeta.last_sync_at}${syncMeta.last_sync_ok === false ? "（部分失败）" : ""}`
      : "已刷新行情";
  } catch {
    lastSyncInfo.value = "已刷新行情";
  }
}

async function handleSyncMarket({ silent = false } = {}) {
  try {
    const data = await syncMarketQuotes();
    if (!data?.ok && !silent) {
      ui.warning("未能解析到有效行情，请稍后重试");
    } else if (!silent) {
      ui.success("行情已更新");
    }
    await onMarketSynced();
    await marketChartRef.value?.reloadLocal?.();
    await refreshCharts();
  } catch (e) {
    if (!silent && !isRouteAbortError(e)) ui.error(e?.message || "同步失败");
  }
}

async function saveSettings() {
  settingsSaving.value = true;
  try {
    const payload = formToSettingsPayload(settingsForm.value);
    const next = await updateCarbonSettings(payload);
    carbonPageCache.settings = next;
    settingsForm.value = settingsToForm(next);
    ui.success("约束配置已保存");
  } catch (e) {
    ui.error(e?.message || "保存失败（需管理员权限）");
  } finally {
    settingsSaving.value = false;
  }
}

// ── 综合 AI 分析 + 历史报告（参照理财助手侧栏）──
const CONCLUSION_TAGS = ["履约缺口", "策略建议", "分析预警", "政策要点"];
const forecastMethod = ref("rule");
const forecastMethodOptions = [
  { label: "规则启发式（快）", value: "rule" },
  { label: "ETS 指数平滑", value: "ets" },
  { label: "SARIMAX", value: "sarimax" },
  { label: "Prophet", value: "prophet" },
];
const submitting = ref(false);
const runningTasks = ref([]);
const completedReports = ref([]);
const historySearchQuery = ref("");
const historyPage = ref(1);
const HISTORY_PAGE_SIZE = 1;
const POLL_INTERVAL = 3000;
let pollTimer = null;

function reportTypeLabel(report) {
  const map = {
    compliance_analysis: "履约综合分析",
    market_brief: "碳交易简报",
    policy_digest: "政策摘要",
  };
  return map[report?.report_type] || report?.report_type || "报告";
}

function reportCardTitle(report) {
  const subject = (report?.subject || "").trim() || "控排企业";
  const year = report?.target_year ? `${report.target_year}年` : "";
  return year ? `${subject} · ${year}履约分析` : `${subject}履约分析`;
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
      pending: "排队中",
      running: "分析中",
      completed: "已完成",
      failed: "失败",
      cancelled: "已取消",
    }[s] || s || "—"
  );
}

/** 结论卡片为纯文本，去掉行内 Markdown 标记以免露出 **加粗** 等。 */
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
  const empty = { tags: [...CONCLUSION_TAGS], title: "", sentence: "" };
  const raw = String(content || "").trim();
  if (!raw) return empty;
  const sectionMatch = raw.match(
    /(?:^|\n)#{1,3}\s*先看结论\s*\n([\s\S]*?)(?=\n#{1,3}\s|\n---\s*$|$)/
  );
  let block = (sectionMatch?.[1] || raw).trim();
  block = block.replace(/^(?:#{1,3}\s*先看结论\s*\n+)+/i, "").trim();
  if (/正在生成 AI|结论将在/.test(block)) {
    return {
      tags: [...CONCLUSION_TAGS],
      title: "",
      sentence: "综合分析进行中，完成后可在此查看摘要。",
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
    for (const label of CONCLUSION_TAGS) {
      if (label === "履约缺口" && /无缺口|无履约缺口/.test(item)) continue;
      if (item.includes(label) && !foundTags.includes(label)) foundTags.push(label);
    }
    if (!sentence && item.length >= 10 && !/^\|/.test(item)) sentence = item;
  }
  const full = sentence || "报告已生成，点击阅读查看完整分析结论。";
  let tags = foundTags;
  if (!tags.length) {
    if (/配额盈余|无缺口|盈余企业/.test(full)) {
      tags = ["配额盈余", "策略建议", "结转风险"];
    } else {
      tags = [...CONCLUSION_TAGS];
    }
  }
  // 只保留完整结论；title 留空避免与 sentence 重复截断展示
  return {
    tags,
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
            tags: [...CONCLUSION_TAGS],
            title: "生成失败",
            sentence: report.error_message || "生成失败",
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
    // 并行任务：任一任务结束即提示，不等到全部跑完
    for (const id of prevRunningIds) {
      if (runningTasks.value.some((r) => r.id === id)) continue;
      const done = completedReports.value.find((r) => r.id === id);
      if (!done) continue;
      const title = reportCardTitle(done);
      if (done.status === "completed") {
        ui.success(`「${title}」已生成`);
      } else if (done.status === "failed") {
        ui.error(done.error_message || `「${title}」分析失败`);
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

async function handleStartAnalysis() {
  if (!selectedId.value) return ui.warning("请先选择企业");
  if (submitting.value) return;
  submitting.value = true;
  try {
    const subject = enterpriseLabel(selected.value) || "控排企业";
    await submitCarbonReport({
      subject: subject.slice(0, 120),
      report_type: "compliance_analysis",
      industry: selected.value?.industry || "",
      target_year: String(complianceYear.value),
      ai_context: JSON.stringify({
        enterprise_id: selectedId.value,
        compliance_year: Number(complianceYear.value),
        forecast_method: forecastMethod.value || "rule",
      }),
    });
    ui.success(
      runningTasks.value.length
        ? "已追加分析任务，可与进行中的任务并行"
        : "任务已提交，后台分析中"
    );
    await fetchAllReports();
    startPolling();
  } catch (e) {
    ui.error(e?.message || "提交分析失败");
  } finally {
    submitting.value = false;
  }
}

async function handleCancelTask(taskId) {
  try {
    await cancelCarbonReport(taskId);
    ui.success("任务已取消");
    await fetchAllReports();
  } catch (e) {
    ui.error(e?.message || "取消失败");
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

async function handleViewReport(report) {
  try {
    await viewCarbonReport(report.id, report.share_token);
  } catch (e) {
    ui.error(e?.message || "打开报告失败");
  }
}

async function handleDownloadReport(reportId) {
  try {
    await downloadCarbonReport(reportId);
  } catch (e) {
    ui.error(e?.message || "下载失败");
  }
}

watch(selectedId, async (id, prev) => {
  showEmissionModal.value = false;
  showCeaModal.value = false;
  showCcerModal.value = false;
  if (bootstrapping || id === prev) return;
  await loadAssets();
});

onMounted(async () => {
  bootstrapping = true;
  try {
    await loadMeta();
    await loadEnterprises();
    await loadMarket({ autoSync: false });
    await loadAssets();
    await fetchAllReports();
    if (runningTasks.value.length) startPolling();
    await nextTick();
    marketChartRef.value?.resize?.();
    setTimeout(() => refreshMarketSourceInfo(), 800);
  } catch (e) {
    if (!isRouteAbortError(e)) ui.error(e?.message || "初始化失败");
  } finally {
    bootstrapping = false;
  }
});

onActivated(() => {
  if (runningTasks.value.length) startPolling();
});
onDeactivated(() => {
  stopPolling();
});

onUnmounted(() => {
  stopPolling();
  showEmissionModal.value = false;
  showCeaModal.value = false;
  showCcerModal.value = false;
});
</script>

<template>
  <FeatureSubsystemShell fill :show-intro="false">
    <div class="cc-view">
      <div class="cc-body">
        <div class="cc-main">
          <!-- 1. 市场行情 -->
          <FeatureSection title="市场行情">
            <template #extra>
              <n-popover trigger="click" placement="bottom-end" style="max-width: 320px">
                <template #trigger>
                  <n-button quaternary circle size="tiny" @click.stop>
                    <template #icon><n-icon :component="HelpCircleOutline" :size="14" /></template>
                  </n-button>
                </template>
                <div class="cc-help-pop">
                  <div class="cc-help-pop-title">数据来源与同步</div>
                  <p v-if="lastSyncInfo">{{ lastSyncInfo }}</p>
                  <p v-else>尚未同步入库；可点击图表右上角「刷新」拉取并更新本地日线。</p>
                  <div v-for="(s, i) in marketSourceLines" :key="i" class="cc-help-source">
                    <div>{{ s.name }}</div>
                    <div class="cc-field-hint">
                      <span v-if="s.queried">拉取 {{ s.queried }}</span>
                      <span v-if="s.latest != null"> · 最新 {{ s.latest }} 元/吨</span>
                    </div>
                    <n-button size="tiny" tertiary @click="openExternal(s.page)">打开来源页</n-button>
                  </div>
                  <p v-if="!marketSourceLines.length" class="cc-field-hint">图表加载后可在此查看拉取时间与最新价。</p>
                </div>
              </n-popover>
            </template>
            <div class="cc-charts">
              <CarbonCeaQuoteChart ref="marketChartRef" @market-synced="onMarketSynced" />
            </div>
          </FeatureSection>

          <!-- 2. 企业基本信息填报 -->
          <FeatureSection title="企业基本信息填报" collapsible :default-expanded="false">
            <div class="cc-toolbar">
              <n-button size="small" @click="startCreate">新建</n-button>
            </div>

            <div class="cc-grid-2">
              <div>
                <n-empty v-if="!enterprises.length" description="暂无履约主体，请先创建" />
                <div v-for="ent in enterprises" :key="ent.id" class="cc-ent-card">
                  <div class="cc-ent-head">
                    <strong>{{ enterpriseLabel(ent) }}</strong>
                    <n-tag size="tiny" :bordered="false">{{ ent.industry }}</n-tag>
                  </div>
                  <div class="cc-muted">
                    纳入 {{ ent.market_start_year }} · 预算 {{ ent.annual_budget_cap }}
                  </div>
                  <div class="cc-row-actions">
                    <n-button size="tiny" @click="selectedId = ent.id; startEdit(ent)">编辑</n-button>
                    <n-button size="tiny" type="error" quaternary @click="handleDeleteEnterprise(ent.id)">
                      删除
                    </n-button>
                  </div>
                </div>
              </div>

              <div>
                <div class="cc-subhead">{{ editingId ? "编辑履约参数" : "新建履约主体" }}</div>
                <n-form label-placement="left" label-width="108" size="small">
                  <n-form-item>
                    <template #label>
                      <span class="cc-form-label">企业名称<FieldHelp tip="履约主体显示名称，便于区分多家企业" /></span>
                    </template>
                    <n-input
                      v-model:value="form.name"
                      size="small"
                      placeholder="如 XX 发电有限公司"
                      maxlength="128"
                      show-count
                    />
                  </n-form-item>
                  <n-form-item>
                    <template #label>
                      <span class="cc-form-label">控排行业<FieldHelp tip="火电/钢铁/水泥/电解铝；决定行业参数与策略口径" /></span>
                    </template>
                    <n-select
                      v-model:value="form.industry"
                      size="small"
                      :options="meta.industries || []"
                      label-field="label"
                      value-field="value"
                      placeholder="选择纳入全国碳市场的行业"
                    />
                  </n-form-item>
                  <n-form-item>
                    <template #label>
                      <span class="cc-form-label">纳入起始年<FieldHelp tip="该主体纳入全国碳市场的首个履约年份" /></span>
                    </template>
                    <n-input-number
                      v-model:value="form.market_start_year"
                      size="small"
                      :min="2013"
                      placeholder="如 2021"
                    />
                  </n-form-item>
                  <n-form-item>
                    <template #label>
                      <span class="cc-form-label">风险偏好<FieldHelp tip="影响策略允许的动作：外购 CCER、出售盈余、低位囤存" /></span>
                    </template>
                    <n-select
                      v-model:value="form.risk_profile"
                      size="small"
                      :options="meta.risk_profiles || []"
                      label-field="label"
                      value-field="value"
                      placeholder="保守 / 平衡 / 进取"
                    />
                  </n-form-item>
                  <n-form-item>
                    <template #label>
                      <span class="cc-form-label">年度预算<FieldHelp tip="本年度计划用于买 CEA/CCER 的总资金上限（元）。策略总成本超过此值会提示超预算" /></span>
                    </template>
                    <n-input-number
                      v-model:value="form.annual_budget_cap"
                      size="small"
                      :min="0"
                      placeholder="元，如 5000000"
                    />
                  </n-form-item>
                  <n-button type="primary" size="small" :loading="saving" @click="handleSaveEnterprise">
                    保存
                  </n-button>
                </n-form>
              </div>
            </div>
          </FeatureSection>

          <!-- 3. 排放与资产台账 -->
          <FeatureSection title="排放与资产台账" collapsible :default-expanded="false">
            <n-alert v-if="!selectedId" type="warning" :bordered="false" title="请先选择履约主体" />
            <template v-else>
              <div class="cc-toolbar">
                <span class="cc-muted">当前：{{ enterpriseLabel(selected) }}</span>
                <n-button size="small" @click="handleDownloadTemplate">
                  <template #icon><n-icon :component="DownloadOutline" /></template>
                  下载模板
                </n-button>
                <n-button size="small" @click="importInput?.click()">Excel 导入</n-button>
                <input
                  ref="importInput"
                  type="file"
                  accept=".xlsx,.xls"
                  class="cc-hidden"
                  @change="handleImportFile"
                />
                <n-button size="small" :loading="assetsLoading" @click="loadAssets">
                  <template #icon><n-icon :component="RefreshOutline" /></template>
                  刷新
                </n-button>
              </div>

              <div class="cc-grid-2">
                <div class="cc-panel">
                  <div class="cc-subhead-row">
                    <div class="cc-subhead">核查排放</div>
                    <n-button size="tiny" type="primary" @click="openCreateEmission">
                      <template #icon><n-icon :component="AddOutline" /></template>
                      新建
                    </n-button>
                  </div>
                  <n-data-table
                    size="small"
                    :bordered="false"
                    :columns="emissionColumns"
                    :data="emissions"
                    :pagination="false"
                  />
                </div>

                <div class="cc-panel">
                  <div class="cc-subhead-row">
                    <div class="cc-subhead">CEA 配额</div>
                    <n-button size="tiny" type="primary" @click="openCreateCea">
                      <template #icon><n-icon :component="AddOutline" /></template>
                      新建
                    </n-button>
                  </div>
                  <n-data-table
                    size="small"
                    :bordered="false"
                    :columns="ceaColumns"
                    :data="ceaRows"
                  />
                </div>

                <div class="cc-panel">
                  <div class="cc-subhead-row">
                    <div class="cc-subhead">CCER</div>
                    <n-button size="tiny" type="primary" @click="openCreateCcer">
                      <template #icon><n-icon :component="AddOutline" /></template>
                      新建
                    </n-button>
                  </div>
                  <n-data-table
                    size="small"
                    :bordered="false"
                    :columns="ccerColumns"
                    :data="ccerRows"
                  />
                </div>
              </div>
            </template>
          </FeatureSection>

          <!-- 4. 策略约束配置 -->
          <FeatureSection title="策略约束配置" collapsible :default-expanded="false">
            <template #extra>
              <n-popover trigger="click" placement="bottom-end" style="max-width: 340px">
                <template #trigger>
                  <n-button quaternary circle size="tiny" @click.stop>
                    <template #icon><n-icon :component="HelpCircleOutline" :size="14" /></template>
                  </n-button>
                </template>
                <div class="cc-help-pop">
                  <div class="cc-help-pop-title">交易手续费说明</div>
                  <p>手续费 = 成交总额 × 单边费率；买入应付 = 总额 + 手续费，卖出实收 = 总额 − 手续费。</p>
                  <p>请分别填写挂牌与大宗费率。CEA 指导价上限：挂牌双向各 6‰、大宗双向各 5‰；CCER 挂牌多为双向各 6‰。</p>
                  <p>策略估算：线上挂牌用「挂牌手续费率」；优先线下撮合按「大宗手续费率」计。</p>
                </div>
              </n-popover>
            </template>
            <n-form label-placement="left" label-width="128" size="small" class="cc-settings-form">
              <div class="cc-subhead">合规上限</div>
              <div class="cc-grid-2">
                <n-form-item>
                  <template #label>
                    <span class="cc-form-label">CCER 抵扣比例<FieldHelp tip="相对核查排放的最高抵扣比例。0.05 = 最多抵扣 5%" /></span>
                  </template>
                  <n-input-number
                    v-model:value="settingsForm.ccer_max_ratio"
                    size="small"
                    :min="0"
                    :max="1"
                    :step="0.01"
                    :precision="2"
                    placeholder="如 0.05"
                    style="width: 100%"
                  />
                </n-form-item>
                <n-form-item>
                  <template #label>
                    <span class="cc-form-label">低价分位<FieldHelp tip="现价低于该历史分位视为「低位」（常用 0.25–0.35）" /></span>
                  </template>
                  <n-input-number
                    v-model:value="settingsForm.price_low_percentile"
                    size="small"
                    :min="0.05"
                    :max="0.5"
                    :step="0.05"
                    :precision="2"
                    placeholder="如 0.30"
                    style="width: 100%"
                  />
                </n-form-item>
                <n-form-item>
                  <template #label>
                    <span class="cc-form-label">中高价分位<FieldHelp tip="现价高于该分位视为偏贵（常用 0.65–0.80）" /></span>
                  </template>
                  <n-input-number
                    v-model:value="settingsForm.price_mid_percentile"
                    size="small"
                    :min="0.5"
                    :max="0.95"
                    :step="0.05"
                    :precision="2"
                    placeholder="如 0.70"
                    style="width: 100%"
                  />
                </n-form-item>
                <n-form-item>
                  <template #label>
                    <span class="cc-form-label">清缴预警天数<FieldHelp tip="距清缴截止的提前提醒节点，逗号分隔" /></span>
                  </template>
                  <n-input
                    v-model:value="settingsForm.clearance_warn_days"
                    size="small"
                    placeholder="如 90,30,15"
                  />
                </n-form-item>
                <n-form-item>
                  <template #label>
                    <span class="cc-form-label">结转日(月-日)<FieldHelp tip="超额配额须在此日（含）前处置；政策可能调整，默认 06-10" /></span>
                  </template>
                  <n-input
                    v-model:value="settingsForm.carry_forward_deadline_md"
                    size="small"
                    placeholder="06-10"
                  />
                </n-form-item>
                <n-form-item>
                  <template #label>
                    <span class="cc-form-label">结转基础额度(万吨)<FieldHelp tip="最大可结转=min(基础+净卖出×倍数, 年末持仓)。填 0 时策略用当年免费配额作基础" /></span>
                  </template>
                  <n-input-number
                    v-model:value="settingsForm.carry_base_qty"
                    size="small"
                    :min="0"
                    :step="0.01"
                    placeholder="0=用当年免费配额"
                    style="width: 100%"
                  />
                </n-form-item>
                <n-form-item>
                  <template #label>
                    <span class="cc-form-label">净卖出结转倍数<FieldHelp tip="公式中「净卖出 × 倍数」的倍数，默认 1.5" /></span>
                  </template>
                  <n-input-number
                    v-model:value="settingsForm.carry_net_sell_multiplier"
                    size="small"
                    :min="0"
                    :step="0.1"
                    :precision="2"
                    placeholder="1.5"
                    style="width: 100%"
                  />
                </n-form-item>
              </div>

              <div class="cc-subhead">交易渠道与成本</div>
              <div class="cc-grid-2">
                <n-form-item>
                  <template #label>
                    <span class="cc-form-label">优先线下撮合<FieldHelp tip="开启后采购默认按线下议价路径估算成本" /></span>
                  </template>
                  <n-switch v-model:value="settingsForm.prefer_offline" size="small" />
                </n-form-item>
                <n-form-item>
                  <template #label>
                    <span class="cc-form-label">线下假定折扣<FieldHelp tip="相对公开参考价的假定便宜幅度；0.03 ≈ 97 折" /></span>
                  </template>
                  <n-input-number
                    v-model:value="settingsForm.offline_discount_vs_listed"
                    size="small"
                    :min="0"
                    :max="0.3"
                    :step="0.01"
                    :precision="2"
                    placeholder="如 0.03"
                    style="width: 100%"
                    :disabled="!settingsForm.prefer_offline"
                  />
                </n-form-item>
                <n-form-item>
                  <template #label>
                    <span class="cc-form-label">挂牌手续费率<FieldHelp tip="单边；手续费=成交总额×费率。指导价参考 0.006（6‰）" /></span>
                  </template>
                  <n-input-number
                    v-model:value="settingsForm.listing_fee_rate"
                    size="small"
                    :min="0"
                    :max="0.05"
                    :step="0.0001"
                    :precision="4"
                    placeholder="单边，如 0.006"
                    style="width: 100%"
                  />
                </n-form-item>
                <n-form-item>
                  <template #label>
                    <span class="cc-form-label">大宗手续费率<FieldHelp tip="单边；线下/大宗路径用此费率。指导价参考 0.005（5‰）" /></span>
                  </template>
                  <n-input-number
                    v-model:value="settingsForm.block_fee_rate"
                    size="small"
                    :min="0"
                    :max="0.05"
                    :step="0.0001"
                    :precision="4"
                    placeholder="单边，如 0.005"
                    style="width: 100%"
                  />
                </n-form-item>
                <n-form-item>
                  <template #label>
                    <span class="cc-form-label">逾期罚款(元/吨)<FieldHelp tip="未足额清缴的单位罚款假设，用于风险成本估算" /></span>
                  </template>
                  <n-input-number
                    v-model:value="settingsForm.overdue_penalty_per_t"
                    size="small"
                    :min="0"
                    :step="10"
                    placeholder="如 200"
                    style="width: 100%"
                  />
                </n-form-item>
              </div>

              <div class="cc-subhead">
                风险画像动作开关
                <FieldHelp tip="保守偏覆盖缺口、平衡可外购 CCER/出售盈余、进取允许低位囤存。" />
              </div>
              <div class="cc-profile-grid">
                <div v-for="p in profileKeys" :key="p.key" class="cc-profile-card">
                  <div class="cc-profile-title">{{ p.label }}</div>
                  <n-space vertical :size="6">
                    <n-checkbox v-model:checked="settingsForm.profiles[p.key].allow_buy_external_ccer">
                      允许外购 CCER
                    </n-checkbox>
                    <n-checkbox v-model:checked="settingsForm.profiles[p.key].allow_sell_surplus">
                      允许出售盈余 CEA
                    </n-checkbox>
                    <n-checkbox v-model:checked="settingsForm.profiles[p.key].allow_stockpile">
                      允许低位囤存
                    </n-checkbox>
                  </n-space>
                </div>
              </div>

              <div class="cc-toolbar cc-mt">
                <n-button type="primary" size="small" :loading="settingsSaving" @click="saveSettings">
                  保存约束
                </n-button>
              </div>
            </n-form>
          </FeatureSection>
        </div>

        <div class="cc-side">
          <FeatureSection title="选择企业" dense>
            <n-select
              v-model:value="selectedId"
              size="small"
              :options="enterprises.map((e) => ({ label: enterpriseLabel(e), value: e.id }))"
              placeholder="选择当前履约主体"
              clearable
              filterable
            />
            <div v-if="selected" class="cc-side-ent-meta">
              {{ selected.industry }} · 纳入 {{ selected.market_start_year }}
            </div>
          </FeatureSection>

          <FeatureSection title="AI智能分析与策略推荐" dense>
            <template #extra>
              <FieldHelp tip="结合台账、策略约束、行情预测与联网政策，生成含三档策略与分析预警的综合报告；完成后会出现在下方历史报告中。" />
            </template>
            <div class="cc-side-analyze">
              <div class="cc-side-analyze-row">
                <span class="cc-inline-label">
                  履约年
                  <FieldHelp tip="用于核算履约缺口的目标年份" />
                </span>
                <n-input-number
                  v-model:value="complianceYear"
                  size="small"
                  :min="2018"
                  placeholder="如 2025"
                  style="width: 100%"
                />
              </div>
              <div class="cc-side-analyze-row">
                <span class="cc-inline-label">
                  预测算法
                  <FieldHelp tip="用于至年底碳价情景；规则启发式更快，统计模型更细" />
                </span>
                <n-select
                  v-model:value="forecastMethod"
                  size="small"
                  :options="forecastMethodOptions"
                  style="width: 100%"
                />
              </div>
              <n-button
                type="primary"
                size="small"
                block
                :loading="submitting"
                :disabled="!selectedId || submitting"
                @click="handleStartAnalysis"
              >
                {{ runningTasks.length ? "追加综合分析" : "开始综合分析" }}
              </n-button>
            </div>
          </FeatureSection>

          <FeatureSection title="进行中的任务" dense>
            <template #extra>
              <n-tag v-if="runningTasks.length" size="tiny" :bordered="false" round>
                {{ runningTasks.length }}
              </n-tag>
            </template>
            <div v-if="!runningTasks.length" class="cc-empty">暂无进行中的任务</div>
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
                    :size="18"
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

          <FeatureSection title="历史报告" dense>
            <template v-if="isSystemAdmin" #extra>
              <n-tag size="tiny" :bordered="false" type="info">全员</n-tag>
            </template>
            <div class="cc-history-search">
              <n-input
                v-model:value="historySearchQuery"
                :placeholder="isSystemAdmin ? '搜索（主体/年份/用户）' : '搜索报告（主体/年份/类型）'"
                size="tiny"
                clearable
              />
            </div>
            <div v-if="!filteredHistory.length" class="cc-empty">暂无历史报告</div>
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
                  <span>分析结论</span>
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
                阅读报告
              </n-button>

              <div class="cc-history-actions-row">
                <IconAction
                  v-if="report.status === 'completed'"
                  label="下载"
                  :icon="DownloadOutline"
                  size="tiny"
                  @click="handleDownloadReport(report.id)"
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
      </div>
    </div>

    <n-modal
      v-model:show="showEmissionModal"
      preset="card"
      class="cc-asset-modal"
      :title="emissionModalMode === 'edit' ? '编辑核查排放' : '新建核查排放'"
      :style="{ width: '480px', maxWidth: '92vw' }"
      :mask-closable="false"
      :segmented="{ footer: true }"
    >
      <n-form label-placement="top" size="small">
        <n-form-item>
          <template #label>
            <span class="cc-form-label">履约年份<FieldHelp tip="对应哪一年度的排放与履约核算" /></span>
          </template>
          <n-input-number
            v-model:value="emissionForm.year"
            size="small"
            :min="2018"
            placeholder="如 2025"
            style="width: 100%"
          />
        </n-form-item>
        <n-form-item>
          <template #label>
            <span class="cc-form-label">Scope1 工艺过程（万吨 CO₂）<FieldHelp tip="生产工艺过程直接排放（如水泥熟料煅烧等），单位万吨" /></span>
          </template>
          <n-input-number
            v-model:value="emissionForm.scope1_process"
            size="small"
            :min="0"
            :step="0.01"
            placeholder="工艺排放量，万吨"
            style="width: 100%"
          />
        </n-form-item>
        <n-form-item>
          <template #label>
            <span class="cc-form-label">Scope1 化石燃料（万吨 CO₂）<FieldHelp tip="化石燃料燃烧直接排放；有官方核查总量时可只填核查总量。单位万吨" /></span>
          </template>
          <n-input-number
            v-model:value="emissionForm.scope1_combustion"
            size="small"
            :min="0"
            :step="0.01"
            placeholder="燃烧排放量，万吨"
            style="width: 100%"
          />
        </n-form-item>
        <n-form-item>
          <template #label>
            <span class="cc-form-label">官方核查总量（万吨，可选）<FieldHelp tip="有第三方/官方核查报告时优先填此项，将覆盖 Scope1 分项合计。单位万吨" /></span>
          </template>
          <n-input-number
            v-model:value="emissionForm.verified_total"
            size="small"
            :min="0"
            :step="0.01"
            clearable
            placeholder="核查报告盖章总量，万吨"
            style="width: 100%"
          />
        </n-form-item>
      </n-form>
      <template #footer>
        <div class="cc-modal-footer">
          <n-button size="small" @click="showEmissionModal = false">取消</n-button>
          <n-button size="small" type="primary" :loading="assetSaving" @click="saveEmission">保存</n-button>
        </div>
      </template>
    </n-modal>

    <n-modal
      v-model:show="showCeaModal"
      preset="card"
      class="cc-asset-modal"
      :title="ceaModalMode === 'edit' ? '编辑 CEA 配额' : '新建 CEA 配额'"
      :style="{ width: '480px', maxWidth: '92vw' }"
      :mask-closable="false"
      :segmented="{ footer: true }"
    >
      <n-form label-placement="top" size="small">
        <n-form-item>
          <template #label>
            <span class="cc-form-label">配额年度（vintage）<FieldHelp tip="免费配额所属履约年度" /></span>
          </template>
          <n-input-number
            v-model:value="ceaForm.vintage_year"
            size="small"
            :min="2018"
            placeholder="如 2025"
            style="width: 100%"
          />
        </n-form-item>
        <n-form-item>
          <template #label>
            <span class="cc-form-label">免费配额（万吨）<FieldHelp tip="当年新分配到账的免费碳配额（CEA），单位万吨" /></span>
          </template>
          <n-input-number
            v-model:value="ceaForm.free_quota"
            size="small"
            :min="0"
            :step="0.01"
            placeholder="当年新分配的 CEA，万吨"
            style="width: 100%"
          />
        </n-form-item>
        <n-form-item>
          <template #label>
            <span class="cc-form-label">结转量（万吨）<FieldHelp tip="往年剩下来结转至本年度的碳配额额度；结转量 + 当年免费配额 = 本年可用总额度" /></span>
          </template>
          <n-input-number
            v-model:value="ceaForm.carry_forward_qty"
            size="small"
            :min="0"
            :step="0.01"
            placeholder="往年结转额度，万吨"
            style="width: 100%"
          />
        </n-form-item>
        <n-form-item>
          <template #label>
            <span class="cc-form-label">当前净卖出（万吨）<FieldHelp tip="累计卖出 − 买入。最大可结转 = min(基础额度 + 净卖出 × 倍数, 年末持仓)；综合分析报告按此测算" /></span>
          </template>
          <n-input-number
            v-model:value="ceaForm.net_sell_qty"
            size="small"
            :step="0.01"
            placeholder="卖出减买入，可为负；万吨"
            style="width: 100%"
          />
        </n-form-item>
        <n-form-item>
          <template #label>
            <span class="cc-form-label">可出售上限（万吨，可选）<FieldHelp tip="内部风控对可卖出盈余配额的上限；不填则按可用量估算。单位万吨" /></span>
          </template>
          <n-input-number
            v-model:value="ceaForm.sellable_cap"
            size="small"
            :min="0"
            clearable
            :step="0.01"
            placeholder="可售上限，万吨"
            style="width: 100%"
          />
        </n-form-item>
      </n-form>
      <template #footer>
        <div class="cc-modal-footer">
          <n-button size="small" @click="showCeaModal = false">取消</n-button>
          <n-button size="small" type="primary" :loading="assetSaving" @click="saveCea">保存</n-button>
        </div>
      </template>
    </n-modal>

    <n-modal
      v-model:show="showCcerModal"
      preset="card"
      class="cc-asset-modal"
      :title="ccerModalMode === 'edit' ? '编辑 CCER' : '新建 CCER'"
      :style="{ width: '480px', maxWidth: '92vw' }"
      :mask-closable="false"
      :segmented="{ footer: true }"
    >
      <n-form label-placement="top" size="small">
        <n-form-item>
          <template #label>
            <span class="cc-form-label">项目类型<FieldHelp tip="核证自愿减排项目类别，便于台账区分" /></span>
          </template>
          <n-input
            v-model:value="ccerForm.project_type"
            size="small"
            placeholder="如 可再生能源 / 林业碳汇"
          />
        </n-form-item>
        <n-form-item>
          <template #label>
            <span class="cc-form-label">签发年份<FieldHelp tip="CCER 签发或登记年份" /></span>
          </template>
          <n-input-number
            v-model:value="ccerForm.issue_year"
            size="small"
            :min="2010"
            placeholder="如 2024"
            style="width: 100%"
          />
        </n-form-item>
        <n-form-item>
          <template #label>
            <span class="cc-form-label">有效期至<FieldHelp tip="超过该日期通常不可再用于履约抵扣" /></span>
          </template>
          <n-input
            v-model:value="ccerForm.expire_at"
            size="small"
            placeholder="YYYY-MM-DD，如 2030-12-31"
          />
        </n-form-item>
        <n-form-item>
          <template #label>
            <span class="cc-form-label">持有存量（万吨）<FieldHelp tip="当前账户持有的 CCER 数量，单位万吨" /></span>
          </template>
          <n-input-number
            v-model:value="ccerForm.qty"
            size="small"
            :min="0"
            :step="0.01"
            placeholder="账户中的 CCER 总量，万吨"
            style="width: 100%"
          />
        </n-form-item>
        <n-form-item>
          <template #label>
            <span class="cc-form-label">可抵扣量（万吨）<FieldHelp tip="满足方法学与时效要求、可用于抵扣的部分；不填默认等于存量。单位万吨" /></span>
          </template>
          <n-input-number
            v-model:value="ccerForm.eligible_qty"
            size="small"
            :min="0"
            :step="0.01"
            placeholder="符合抵扣条件的数量，万吨"
            style="width: 100%"
          />
        </n-form-item>
      </n-form>
      <template #footer>
        <div class="cc-modal-footer">
          <n-button size="small" @click="showCcerModal = false">取消</n-button>
          <n-button size="small" type="primary" :loading="assetSaving" @click="saveCcer">保存</n-button>
        </div>
      </template>
    </n-modal>
  </FeatureSubsystemShell>
</template>

<style scoped>
.cc-view {
  --cc-1: 4px;
  --cc-2: 8px;
  --cc-3: 12px;
  --cc-4: 16px;
  --cc-5: 20px;
  --cc-radius: 6px;
  padding: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex: 1;
  height: 100%;
  font-size: 11px;
  color: var(--platform-text);
}
.cc-body {
  display: flex;
  gap: var(--cc-3);
  align-items: flex-start;
  min-height: 0;
}
.cc-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--cc-3);
}
.cc-side {
  width: 300px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: var(--cc-3);
  position: sticky;
  top: 0;
}
@media (max-width: 1100px) {
  .cc-body {
    flex-direction: column;
  }
  .cc-side {
    width: 100%;
    position: static;
  }
}
.cc-grid-2 {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: var(--cc-2);
}
.cc-charts :deep(.cea-quote__chart) {
  height: 420px;
}
.cc-charts :deep(.cea-quote__chart--tall) {
  height: 560px;
}
.cc-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--cc-2);
  align-items: center;
}
.cc-subhead-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--cc-2);
  margin: var(--cc-1) 0 var(--cc-2);
}
.cc-subhead-row .cc-subhead {
  margin: 0;
}
.cc-subhead {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 11px;
  font-weight: 500;
  color: var(--platform-text);
  margin: var(--cc-1) 0 var(--cc-2);
}
.cc-modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--cc-2);
}
.cc-asset-modal :deep(.n-form-item) {
  margin-bottom: 8px;
}
.cc-asset-modal :deep(.n-form-item-feedback-wrapper) {
  display: none;
  min-height: 0 !important;
}
.cc-form-label {
  display: inline-flex;
  align-items: center;
  gap: 0;
  font-size: 11px;
  font-weight: 400;
  color: var(--platform-text-secondary);
}
.cc-inline-label {
  display: inline-flex;
  align-items: center;
  gap: 0;
  font-size: 11px;
  color: var(--platform-text-secondary);
}
.cc-field-hint {
  font-size: 10px;
  color: var(--platform-text-tertiary);
  line-height: 1.35;
}
.cc-muted {
  color: var(--platform-text-tertiary);
  font-size: 10px;
  line-height: 1.4;
  margin: 0 0 var(--cc-2);
}
.cc-view :deep(.n-form-item) {
  margin-bottom: 8px;
}
.cc-view :deep(.n-form-item-label) {
  font-size: 11px !important;
  color: var(--platform-text-secondary) !important;
}
.cc-view :deep(.n-form-item-feedback-wrapper) {
  display: none;
  min-height: 0 !important;
}
.cc-view :deep(.n-input),
.cc-view :deep(.n-input-number),
.cc-view :deep(.n-base-selection),
.cc-view :deep(.n-button) {
  font-size: 11px;
}
.cc-view :deep(.n-data-table) {
  font-size: 11px;
}
.cc-table-actions {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}
.cc-ent-card,
.cc-panel,
.cc-profile-card {
  border: 1px solid var(--platform-border);
  border-radius: var(--cc-radius);
  padding: var(--cc-2) var(--cc-3);
  background: transparent;
}
.cc-action-bar {
  display: flex;
  justify-content: flex-start;
  margin-top: var(--cc-2);
}
.cc-action-btn {
  min-width: 120px;
}
.cc-side-analyze {
  display: flex;
  flex-direction: column;
  gap: var(--cc-2);
}
.cc-side-analyze-row {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.cc-help-pop {
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 11px;
  color: var(--platform-text-secondary);
  line-height: 1.45;
}
.cc-help-pop p {
  margin: 0;
}
.cc-help-pop-title {
  font-size: 11px;
  font-weight: 500;
  color: var(--platform-text);
}
.cc-help-source {
  padding-top: 6px;
  border-top: 1px solid var(--platform-border);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.cc-ent-head {
  display: flex;
  gap: var(--cc-2);
  align-items: center;
  font-size: 11px;
}
.cc-row-actions {
  margin-top: var(--cc-2);
  display: flex;
  gap: var(--cc-2);
}
.cc-profile-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: var(--cc-2);
}
.cc-profile-title {
  font-size: 11px;
  font-weight: 500;
  margin-bottom: var(--cc-2);
}
.cc-fee-note p {
  margin: 0 0 6px;
  font-size: 11px;
  line-height: 1.45;
  color: var(--platform-text-secondary);
}
.cc-fee-note p:last-child {
  margin-bottom: 0;
}
.cc-mt {
  margin-top: var(--cc-2);
}
.cc-mb {
  margin-bottom: var(--cc-2);
}
.cc-hidden {
  display: none;
}

.cc-empty {
  padding: var(--cc-4) 0;
  text-align: center;
  font-size: 11px;
  color: var(--platform-text-tertiary);
}
.cc-task-item {
  padding: var(--cc-2) 0;
  display: flex;
  flex-direction: column;
  gap: var(--cc-2);
}
.cc-task-item + .cc-task-item {
  border-top: 1px solid var(--platform-border);
}
.cc-task-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--cc-2);
}
.cc-task-info {
  display: flex;
  align-items: center;
  gap: var(--cc-2);
  min-width: 0;
  flex-wrap: wrap;
}
.cc-task-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--platform-text);
}
.cc-task-actions {
  display: flex;
  align-items: center;
  gap: var(--cc-2);
  flex-shrink: 0;
}
.cc-progress-circle {
  width: 18px;
  height: 18px;
}
.cc-task-actions :deep(.n-progress-text) {
  font-size: 0;
}
.cc-task-bottom {
  display: flex;
  align-items: center;
  gap: var(--cc-2);
  flex-wrap: wrap;
}
.cc-task-status {
  font-size: 11px;
  color: var(--platform-text-tertiary);
}
.cc-task-step {
  font-size: 11px;
  color: var(--platform-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 180px;
}
.cc-history-search {
  padding: 0 0 var(--cc-1);
}
.cc-history-card {
  display: flex;
  flex-direction: column;
  gap: var(--cc-3);
  padding: var(--cc-3);
  border-radius: var(--cc-radius);
  border: 1px solid var(--platform-border-strong);
  background: var(--platform-bg-elevated-solid, #fff);
}
.cc-history-card-hd {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--cc-2);
}
.cc-history-title {
  font-size: 12px;
  font-weight: 500;
  color: var(--platform-text);
  line-height: 1.35;
}
.cc-history-type-tag {
  font-size: 11px;
  height: auto;
  line-height: 1.35;
  padding: 2px var(--cc-2);
}
.cc-history-meta-line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--cc-1);
  font-size: 11px;
  color: var(--platform-text-tertiary);
}
.cc-history-meta-sep {
  opacity: 0.55;
}
.cc-conclusion {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--cc-2);
  padding: var(--cc-3);
  border-radius: var(--cc-radius);
  background: var(--platform-card-bg, #fcfcfc);
  border: 1px solid var(--platform-border);
}
.cc-conclusion-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--cc-1);
  padding: 2px var(--cc-2);
  border: 1px solid var(--platform-border-strong);
  border-radius: 4px;
  background: var(--platform-accent-soft);
  color: var(--platform-accent);
  font-size: 11px;
  font-weight: 500;
}
.cc-conclusion-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--cc-1);
}
.cc-conclusion-tags :deep(.n-tag) {
  font-size: 10px;
  height: 20px;
}
.cc-conclusion-divider {
  width: 100%;
  height: 1px;
  background: var(--platform-border-strong);
}
.cc-side-ent-meta {
  margin-top: var(--cc-2);
  font-size: 10px;
  color: var(--platform-text-tertiary);
  line-height: 1.4;
}
.cc-task-owner {
  font-size: 10px;
  color: var(--platform-text-tertiary);
}
.cc-conclusion-sentence {
  width: 100%;
  font-size: 11px;
  font-weight: 400;
  line-height: 1.5;
  color: var(--platform-text-secondary);
  white-space: normal;
  word-break: break-word;
}
.cc-conclusion-sentence--error {
  color: var(--platform-danger, #d03050);
}
.cc-read-btn {
  width: 100%;
}
.cc-history-actions-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--cc-1);
}
.cc-history-pager {
  display: flex;
  justify-content: center;
  padding-top: var(--cc-2);
}
</style>
