<script setup>
import { ref, h, computed } from "vue";
import {
  AddOutline,
  DownloadOutline,
  RefreshOutline,
  CreateOutline,
  TrashOutline,
} from "@vicons/ionicons5";
import FeatureSection from "../FeatureSection.vue";
import IconAction from "../IconAction.vue";
import HintTooltip from "../HintTooltip.vue";
import { usePlatformUi } from "../../composables/usePlatformUi";
import { useI18n } from "../../composables/useI18n";
import { useCarbonCrud } from "../../composables/useCarbonCrud";
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
  downloadImportTemplate,
  importEnterpriseExcel,
} from "../../api/carbonCompliance";
import { isRouteAbortError } from "../../api/http.js";

const props = defineProps({
  selectedId: { type: String, default: "" },
  selected: { type: Object, default: null },
  enterpriseLabel: { type: Function, required: true },
  /** 嵌入分步向导时不渲染外层 FeatureSection */
  embedded: { type: Boolean, default: false },
  /**
   * 分步模式下只展示一类台账：emission | cea | ccer；
   * 未指定时展示全部（兼容旧布局）
   */
  assetStep: { type: String, default: "" },
});

const ui = usePlatformUi();
const { t } = useI18n();

function fmtWanCell(v) {
  if (v == null || v === "") return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return n;
}

const emissions = ref([]);
const ceaRows = ref([]);
const ccerRows = ref([]);
const assetsLoading = ref(false);
const assetSaving = ref(false);
const importInput = ref(null);

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

async function loadAssets() {
  if (!props.selectedId) {
    emissions.value = [];
    ceaRows.value = [];
    ccerRows.value = [];
    return;
  }
  assetsLoading.value = true;
  try {
    const id = props.selectedId;
    const [em, cea, ccer] = await Promise.all([
      listEmissions(id),
      listCea(id),
      listCcer(id),
    ]);
    emissions.value = em || [];
    ceaRows.value = cea || [];
    ccerRows.value = ccer || [];
  } catch (e) {
    if (!isRouteAbortError(e)) ui.error(e?.message || t("carbonAssistant.loadAssetsFailed"));
  } finally {
    assetsLoading.value = false;
  }
}

const {
  form: emissionForm,
  modalMode: emissionModalMode,
  showModal: showEmissionModal,
  openCreate: openCreateEmission,
  startEdit: editEmission,
  closeModal: closeEmissionModal,
  confirmDelete: emissionConfirmDelete,
  runSave: emissionRunSave,
  runDelete: emissionRunDelete,
} = useCarbonCrud({
  emptyForm: emptyEmissionForm,
  mapRowToForm: (row) => ({
    year: Number(row.year) || new Date().getFullYear(),
    scope1_process: Number(row.scope1_process) || 0,
    scope1_combustion: Number(row.scope1_combustion) || 0,
    verified_total: row.verified_total == null ? null : Number(row.verified_total),
  }),
  ui,
});

const {
  form: ceaForm,
  modalMode: ceaModalMode,
  showModal: showCeaModal,
  openCreate: openCreateCea,
  startEdit: editCea,
  closeModal: closeCeaModal,
  confirmDelete: ceaConfirmDelete,
  runSave: ceaRunSave,
  runDelete: ceaRunDelete,
} = useCarbonCrud({
  emptyForm: emptyCeaForm,
  mapRowToForm: (row) => ({
    vintage_year: Number(row.vintage_year) || new Date().getFullYear(),
    free_quota: Number(row.free_quota) || 0,
    carry_forward_qty: Number(row.carry_forward_qty) || 0,
    net_sell_qty: Number(row.net_sell_qty) || 0,
    avg_cost: Number(row.avg_cost) || 0,
    sellable_cap: row.sellable_cap == null ? null : Number(row.sellable_cap),
  }),
  ui,
});

const {
  form: ccerForm,
  modalMode: ccerModalMode,
  showModal: showCcerModal,
  openCreate: openCreateCcer,
  startEdit: editCcer,
  closeModal: closeCcerModal,
  confirmDelete: ccerConfirmDelete,
  runSave: ccerRunSave,
  runDelete: ccerRunDelete,
} = useCarbonCrud({
  emptyForm: emptyCcerForm,
  mapRowToForm: (row) => {
    const qty = Number(row.qty) || 0;
    let eligible = Number(row.eligible_qty);
    if (!Number.isFinite(eligible) || (eligible <= 0 && qty > 0)) eligible = qty;
    if (qty > 0) eligible = Math.min(eligible, qty);
    return {
      id: row.id || null,
      project_type: row.project_type || "wind",
      issue_year: Number(row.issue_year) || new Date().getFullYear() - 1,
      expire_at: String(row.expire_at || "2030-12-31").slice(0, 10),
      qty,
      cost: Number(row.cost) || 0,
      eligible_qty: eligible,
    };
  },
  ui,
});

async function saveEmission() {
  if (!props.selectedId) return ui.warning(t("carbonAssistant.selectEnterpriseWarn"));
  await emissionRunSave({
    saving: assetSaving,
    successMessage: t("carbonAssistant.emissionSaved"),
    afterSave: loadAssets,
    saveFn: () =>
      upsertEmission(props.selectedId, {
        year: emissionForm.value.year,
        scope1_combustion: Number(emissionForm.value.scope1_combustion) || 0,
        scope1_process: Number(emissionForm.value.scope1_process) || 0,
        scope2_power: 0,
        purchased_mwh: 0,
        verified_total:
          emissionForm.value.verified_total === "" || emissionForm.value.verified_total == null
            ? null
            : Number(emissionForm.value.verified_total),
      }),
  });
}

function handleDeleteEmission(row) {
  const year = row?.year;
  if (!props.selectedId || year == null) return;
  emissionConfirmDelete({
    title: t("carbonAssistant.deleteEmissionTitle"),
    content: t("carbonAssistant.deleteEmissionConfirm", { year }),
    onPositive: () =>
      emissionRunDelete({
        deleteFn: () => deleteEmission(props.selectedId, year),
        afterDelete: loadAssets,
      }),
  });
}

async function saveCea() {
  if (!props.selectedId) return ui.warning(t("carbonAssistant.selectEnterpriseWarn"));
  await ceaRunSave({
    saving: assetSaving,
    successMessage: t("carbonAssistant.ceaSaved"),
    afterSave: loadAssets,
    saveFn: () =>
      upsertCea(props.selectedId, {
        vintage_year: ceaForm.value.vintage_year,
        free_quota: Number(ceaForm.value.free_quota) || 0,
        carry_forward_qty: Number(ceaForm.value.carry_forward_qty) || 0,
        net_sell_qty: Number(ceaForm.value.net_sell_qty) || 0,
        avg_cost: Number(ceaForm.value.avg_cost) || 0,
        sellable_cap:
          ceaForm.value.sellable_cap === "" || ceaForm.value.sellable_cap == null
            ? null
            : Number(ceaForm.value.sellable_cap),
      }),
  });
}

function handleDeleteCea(row) {
  const year = row?.vintage_year;
  if (!props.selectedId || year == null) return;
  ceaConfirmDelete({
    title: t("carbonAssistant.deleteCeaTitle"),
    content: t("carbonAssistant.deleteCeaConfirm", { year }),
    onPositive: () =>
      ceaRunDelete({
        deleteFn: () => deleteCea(props.selectedId, year),
        afterDelete: loadAssets,
      }),
  });
}

async function saveCcer() {
  if (!props.selectedId) return ui.warning(t("carbonAssistant.selectEnterpriseWarn"));
  await ccerRunSave({
    saving: assetSaving,
    successMessage: t("carbonAssistant.ccerSaved"),
    afterSave: loadAssets,
    saveFn: () => {
      const qty = Number(ccerForm.value.qty) || 0;
      let eligible =
        ccerForm.value.eligible_qty === "" || ccerForm.value.eligible_qty == null
          ? qty
          : Number(ccerForm.value.eligible_qty);
      if (!Number.isFinite(eligible)) eligible = qty;
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
      return upsertCcer(props.selectedId, payload);
    },
  });
}

function handleDeleteCcer(row) {
  const id = row?.id;
  if (!props.selectedId || !id) return;
  const label = `${row.project_type || "CCER"} / ${row.issue_year || "—"}`;
  ccerConfirmDelete({
    title: t("carbonAssistant.deleteCcerTitle"),
    content: t("carbonAssistant.deleteCcerConfirm", { label }),
    onPositive: () =>
      ccerRunDelete({
        deleteFn: () => deleteCcer(props.selectedId, id),
        afterDelete: loadAssets,
      }),
  });
}

const emissionColumns = computed(() => [
  { title: t("carbonAssistant.colYear"), key: "year", width: 64 },
  {
    title: t("carbonAssistant.colS1Process"),
    key: "scope1_process",
    render: (row) => fmtWanCell(row.scope1_process),
  },
  {
    title: t("carbonAssistant.colS1Combustion"),
    key: "scope1_combustion",
    render: (row) => fmtWanCell(row.scope1_combustion),
  },
  {
    title: t("carbonAssistant.colVerifiedTotal"),
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
          label: t("common.edit"),
          icon: CreateOutline,
          variant: "table",
          onClick: () => editEmission(row),
        }),
        h(IconAction, {
          label: t("common.delete"),
          icon: TrashOutline,
          variant: "table",
          type: "error",
          onClick: () => handleDeleteEmission(row),
        }),
      ]);
    },
  },
]);

const ceaColumns = computed(() => [
  { title: t("carbonAssistant.colYearFull"), key: "vintage_year", width: 64 },
  {
    title: t("carbonAssistant.colFreeQuota"),
    key: "free_quota",
    render: (row) => fmtWanCell(row.free_quota),
  },
  {
    title: t("carbonAssistant.colCarryForward"),
    key: "carry_forward_qty",
    render: (row) => fmtWanCell(row.carry_forward_qty),
  },
  {
    title: t("carbonAssistant.colUsableTotal"),
    key: "usable",
    render: (row) =>
      fmtWanCell((Number(row.free_quota) || 0) + (Number(row.carry_forward_qty) || 0)),
  },
  {
    title: t("carbonAssistant.colNetSell"),
    key: "net_sell_qty",
    render: (row) => fmtWanCell(row.net_sell_qty),
  },
  {
    title: t("carbonAssistant.colSellableCap"),
    key: "sellable_cap",
    render: (row) => fmtWanCell(row.sellable_cap),
  },
  {
    title: "",
    key: "actions",
    width: 72,
    render(row) {
      return h("div", { class: "cc-table-actions" }, [
        h(IconAction, {
          label: t("common.edit"),
          icon: CreateOutline,
          variant: "table",
          onClick: () => editCea(row),
        }),
        h(IconAction, {
          label: t("common.delete"),
          icon: TrashOutline,
          variant: "table",
          type: "error",
          onClick: () => handleDeleteCea(row),
        }),
      ]);
    },
  },
]);

const ccerColumns = computed(() => [
  { title: t("carbonAssistant.colType"), key: "project_type" },
  { title: t("carbonAssistant.colIssueYear"), key: "issue_year", width: 64 },
  { title: t("carbonAssistant.colQty"), key: "qty", render: (row) => fmtWanCell(row.qty) },
  {
    title: t("carbonAssistant.colEligible"),
    key: "eligible_qty",
    render: (row) => fmtWanCell(row.eligible_qty),
  },
  {
    title: "",
    key: "actions",
    width: 72,
    render(row) {
      return h("div", { class: "cc-table-actions" }, [
        h(IconAction, {
          label: t("common.edit"),
          icon: CreateOutline,
          variant: "table",
          onClick: () => editCcer(row),
        }),
        h(IconAction, {
          label: t("common.delete"),
          icon: TrashOutline,
          variant: "table",
          type: "error",
          onClick: () => handleDeleteCcer(row),
        }),
      ]);
    },
  },
]);

async function handleDownloadTemplate() {
  if (!props.selectedId) return ui.warning(t("carbonAssistant.selectEnterpriseWarn"));
  try {
    await downloadImportTemplate(props.selectedId);
  } catch (e) {
    ui.error(e?.message || t("carbonAssistant.downloadFailed"));
  }
}

async function handleImportFile(e) {
  const file = e?.target?.files?.[0];
  if (!file || !props.selectedId) return;
  try {
    const counts = await importEnterpriseExcel(props.selectedId, file);
    ui.success(
      t("carbonAssistant.importDone", {
        emissions: counts.emissions,
        cea: counts.cea,
        ccer: counts.ccer,
      })
    );
    await loadAssets();
  } catch (err) {
    ui.error(err?.message || t("carbonAssistant.importFailed"));
  } finally {
    if (importInput.value) importInput.value.value = "";
  }
}

function closeAllModals() {
  closeEmissionModal();
  closeCeaModal();
  closeCcerModal();
}

defineExpose({ loadAssets, closeAllModals });
</script>

<template>
  <component
    :is="embedded ? 'div' : FeatureSection"
    v-bind="embedded ? { class: 'cc-fill-step-body' } : { title: t('carbonAssistant.emissionSectionTitle'), collapsible: true, defaultExpanded: false }"
  >
    <n-alert v-if="!selectedId" type="warning" :bordered="false" :title="t('carbonAssistant.selectEntityAlert')" />
    <template v-else>
      <div class="cc-toolbar">
        <span class="cc-muted">{{ t("carbonAssistant.currentEntity", { name: enterpriseLabel(selected) }) }}</span>
        <n-button size="small" @click="handleDownloadTemplate">
          <template #icon><n-icon :component="DownloadOutline" /></template>
          {{ t("carbonAssistant.downloadTemplate") }}
        </n-button>
        <n-button size="small" @click="importInput?.click()">{{ t("carbonAssistant.excelImport") }}</n-button>
        <input
          ref="importInput"
          type="file"
          accept=".xlsx,.xls"
          class="cc-hidden"
          @change="handleImportFile"
        />
        <n-button size="small" :loading="assetsLoading" @click="loadAssets">
          <template #icon><n-icon :component="RefreshOutline" /></template>
          {{ t("common.refresh") }}
        </n-button>
      </div>

      <div :class="assetStep ? 'cc-fill-asset-single' : 'cc-grid-2'">
        <div v-if="!assetStep || assetStep === 'emission'" class="cc-panel">
          <div class="cc-subhead-row">
            <div class="cc-subhead">{{ t("carbonAssistant.stepEmission") }}</div>
            <n-button size="tiny" type="primary" @click="openCreateEmission">
              <template #icon><n-icon :component="AddOutline" /></template>
              {{ t("common.create") }}
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

        <div v-if="!assetStep || assetStep === 'cea'" class="cc-panel">
          <div class="cc-subhead-row">
            <div class="cc-subhead">{{ t("carbonAssistant.stepCea") }}</div>
            <n-button size="tiny" type="primary" @click="openCreateCea">
              <template #icon><n-icon :component="AddOutline" /></template>
              {{ t("common.create") }}
            </n-button>
          </div>
          <n-data-table
            size="small"
            :bordered="false"
            :columns="ceaColumns"
            :data="ceaRows"
          />
        </div>

        <div v-if="!assetStep || assetStep === 'ccer'" class="cc-panel">
          <div class="cc-subhead-row">
            <div class="cc-subhead">{{ t("carbonAssistant.stepCcer") }}</div>
            <n-button size="tiny" type="primary" @click="openCreateCcer">
              <template #icon><n-icon :component="AddOutline" /></template>
              {{ t("common.create") }}
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
  </component>

  <n-modal
    v-model:show="showEmissionModal"
    preset="card"
    class="cc-asset-modal"
    :title="emissionModalMode === 'edit' ? t('carbonAssistant.emissionEditTitle') : t('carbonAssistant.emissionCreateTitle')"
    :style="{ width: '480px', maxWidth: '92vw' }"
    :mask-closable="false"
    :segmented="{ footer: true }"
  >
    <n-form label-placement="top" size="small">
      <n-form-item>
        <template #label>
          <span class="cc-form-label">
            {{ t("carbonAssistant.fieldComplianceYear") }}
            <HintTooltip variant="field" :tip="t('carbonAssistant.fieldComplianceYearTip')" />
          </span>
        </template>
        <n-input-number
          v-model:value="emissionForm.year"
          size="small"
          :min="2018"
          :placeholder="t('carbonAssistant.complianceYearPlaceholder')"
          style="width: 100%"
        />
      </n-form-item>
      <n-form-item>
        <template #label>
          <span class="cc-form-label">
            {{ t("carbonAssistant.fieldS1Process") }}
            <HintTooltip variant="field" :tip="t('carbonAssistant.fieldS1ProcessTip')" />
          </span>
        </template>
        <n-input-number
          v-model:value="emissionForm.scope1_process"
          size="small"
          :min="0"
          :step="0.01"
          :placeholder="t('carbonAssistant.fieldS1ProcessPlaceholder')"
          style="width: 100%"
        />
      </n-form-item>
      <n-form-item>
        <template #label>
          <span class="cc-form-label">
            {{ t("carbonAssistant.fieldS1Combustion") }}
            <HintTooltip variant="field" :tip="t('carbonAssistant.fieldS1CombustionTip')" />
          </span>
        </template>
        <n-input-number
          v-model:value="emissionForm.scope1_combustion"
          size="small"
          :min="0"
          :step="0.01"
          :placeholder="t('carbonAssistant.fieldS1CombustionPlaceholder')"
          style="width: 100%"
        />
      </n-form-item>
      <n-form-item>
        <template #label>
          <span class="cc-form-label">
            {{ t("carbonAssistant.fieldVerifiedTotal") }}
            <HintTooltip variant="field" :tip="t('carbonAssistant.fieldVerifiedTotalTip')" />
          </span>
        </template>
        <n-input-number
          v-model:value="emissionForm.verified_total"
          size="small"
          :min="0"
          :step="0.01"
          clearable
          :placeholder="t('carbonAssistant.fieldVerifiedTotalPlaceholder')"
          style="width: 100%"
        />
      </n-form-item>
    </n-form>
    <template #footer>
      <div class="cc-modal-footer">
        <n-button size="small" @click="closeEmissionModal()">{{ t("common.cancel") }}</n-button>
        <n-button size="small" type="primary" :loading="assetSaving" @click="saveEmission">
          {{ t("common.save") }}
        </n-button>
      </div>
    </template>
  </n-modal>

  <n-modal
    v-model:show="showCeaModal"
    preset="card"
    class="cc-asset-modal"
    :title="ceaModalMode === 'edit' ? t('carbonAssistant.ceaEditTitle') : t('carbonAssistant.ceaCreateTitle')"
    :style="{ width: '480px', maxWidth: '92vw' }"
    :mask-closable="false"
    :segmented="{ footer: true }"
  >
    <n-form label-placement="top" size="small">
      <n-form-item>
        <template #label>
          <span class="cc-form-label">
            {{ t("carbonAssistant.fieldVintageYear") }}
            <HintTooltip variant="field" :tip="t('carbonAssistant.fieldVintageYearTip')" />
          </span>
        </template>
        <n-input-number
          v-model:value="ceaForm.vintage_year"
          size="small"
          :min="2018"
          :placeholder="t('carbonAssistant.complianceYearPlaceholder')"
          style="width: 100%"
        />
      </n-form-item>
      <n-form-item>
        <template #label>
          <span class="cc-form-label">
            {{ t("carbonAssistant.fieldFreeQuota") }}
            <HintTooltip variant="field" :tip="t('carbonAssistant.fieldFreeQuotaTip')" />
          </span>
        </template>
        <n-input-number
          v-model:value="ceaForm.free_quota"
          size="small"
          :min="0"
          :step="0.01"
          :placeholder="t('carbonAssistant.fieldFreeQuotaPlaceholder')"
          style="width: 100%"
        />
      </n-form-item>
      <n-form-item>
        <template #label>
          <span class="cc-form-label">
            {{ t("carbonAssistant.fieldCarryQty") }}
            <HintTooltip variant="field" :tip="t('carbonAssistant.fieldCarryQtyTip')" />
          </span>
        </template>
        <n-input-number
          v-model:value="ceaForm.carry_forward_qty"
          size="small"
          :min="0"
          :step="0.01"
          :placeholder="t('carbonAssistant.fieldCarryQtyPlaceholder')"
          style="width: 100%"
        />
      </n-form-item>
      <n-form-item>
        <template #label>
          <span class="cc-form-label">
            {{ t("carbonAssistant.fieldNetSell") }}
            <HintTooltip variant="field" :tip="t('carbonAssistant.fieldNetSellTip')" />
          </span>
        </template>
        <n-input-number
          v-model:value="ceaForm.net_sell_qty"
          size="small"
          :step="0.01"
          :placeholder="t('carbonAssistant.fieldNetSellPlaceholder')"
          style="width: 100%"
        />
      </n-form-item>
      <n-form-item>
        <template #label>
          <span class="cc-form-label">
            {{ t("carbonAssistant.fieldSellableCap") }}
            <HintTooltip variant="field" :tip="t('carbonAssistant.fieldSellableCapTip')" />
          </span>
        </template>
        <n-input-number
          v-model:value="ceaForm.sellable_cap"
          size="small"
          :min="0"
          clearable
          :step="0.01"
          :placeholder="t('carbonAssistant.fieldSellableCapPlaceholder')"
          style="width: 100%"
        />
      </n-form-item>
    </n-form>
    <template #footer>
      <div class="cc-modal-footer">
        <n-button size="small" @click="closeCeaModal()">{{ t("common.cancel") }}</n-button>
        <n-button size="small" type="primary" :loading="assetSaving" @click="saveCea">
          {{ t("common.save") }}
        </n-button>
      </div>
    </template>
  </n-modal>

  <n-modal
    v-model:show="showCcerModal"
    preset="card"
    class="cc-asset-modal"
    :title="ccerModalMode === 'edit' ? t('carbonAssistant.ccerEditTitle') : t('carbonAssistant.ccerCreateTitle')"
    :style="{ width: '480px', maxWidth: '92vw' }"
    :mask-closable="false"
    :segmented="{ footer: true }"
  >
    <n-form label-placement="top" size="small">
      <n-form-item>
        <template #label>
          <span class="cc-form-label">
            {{ t("carbonAssistant.fieldProjectType") }}
            <HintTooltip variant="field" :tip="t('carbonAssistant.fieldProjectTypeTip')" />
          </span>
        </template>
        <n-input
          v-model:value="ccerForm.project_type"
          size="small"
          :placeholder="t('carbonAssistant.fieldProjectTypePlaceholder')"
        />
      </n-form-item>
      <n-form-item>
        <template #label>
          <span class="cc-form-label">
            {{ t("carbonAssistant.fieldIssueYear") }}
            <HintTooltip variant="field" :tip="t('carbonAssistant.fieldIssueYearTip')" />
          </span>
        </template>
        <n-input-number
          v-model:value="ccerForm.issue_year"
          size="small"
          :min="2010"
          :placeholder="t('carbonAssistant.fieldIssueYearPlaceholder')"
          style="width: 100%"
        />
      </n-form-item>
      <n-form-item>
        <template #label>
          <span class="cc-form-label">
            {{ t("carbonAssistant.fieldExpireAt") }}
            <HintTooltip variant="field" :tip="t('carbonAssistant.fieldExpireAtTip')" />
          </span>
        </template>
        <n-input
          v-model:value="ccerForm.expire_at"
          size="small"
          :placeholder="t('carbonAssistant.fieldExpireAtPlaceholder')"
        />
      </n-form-item>
      <n-form-item>
        <template #label>
          <span class="cc-form-label">
            {{ t("carbonAssistant.fieldCcerQty") }}
            <HintTooltip variant="field" :tip="t('carbonAssistant.fieldCcerQtyTip')" />
          </span>
        </template>
        <n-input-number
          v-model:value="ccerForm.qty"
          size="small"
          :min="0"
          :step="0.01"
          :placeholder="t('carbonAssistant.fieldCcerQtyPlaceholder')"
          style="width: 100%"
        />
      </n-form-item>
      <n-form-item>
        <template #label>
          <span class="cc-form-label">
            {{ t("carbonAssistant.fieldEligibleQty") }}
            <HintTooltip variant="field" :tip="t('carbonAssistant.fieldEligibleQtyTip')" />
          </span>
        </template>
        <n-input-number
          v-model:value="ccerForm.eligible_qty"
          size="small"
          :min="0"
          :step="0.01"
          :placeholder="t('carbonAssistant.fieldEligibleQtyPlaceholder')"
          style="width: 100%"
        />
      </n-form-item>
    </n-form>
    <template #footer>
      <div class="cc-modal-footer">
        <n-button size="small" @click="closeCcerModal()">{{ t("common.cancel") }}</n-button>
        <n-button size="small" type="primary" :loading="assetSaving" @click="saveCcer">
          {{ t("common.save") }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>
