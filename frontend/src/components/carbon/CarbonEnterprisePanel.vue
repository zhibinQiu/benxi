<script setup>
import { ref } from "vue";
import FeatureSection from "../FeatureSection.vue";
import HintTooltip from "../HintTooltip.vue";
import { usePlatformUi } from "../../composables/usePlatformUi";
import { useI18n } from "../../composables/useI18n";

const props = defineProps({
  enterprises: { type: Array, default: () => [] },
  meta: { type: Object, default: () => ({}) },
  selectedId: { type: String, default: "" },
  saveEnterprise: { type: Function, required: true },
  removeEnterprise: { type: Function, required: true },
  /** 嵌入分步向导时不渲染外层 FeatureSection */
  embedded: { type: Boolean, default: false },
});

const emit = defineEmits(["update:selectedId"]);

const ui = usePlatformUi();
const { t } = useI18n();

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

const form = ref(emptyEnterpriseForm());
const editingId = ref("");
const saving = ref(false);

function enterpriseLabel(ent) {
  if (!ent) return "";
  if ((ent.name || "").trim()) return ent.name.trim();
  const ind =
    (props.meta.industries || []).find((x) => x.value === ent.industry)?.label ||
    ent.industry ||
    t("carbonAssistant.enterpriseFallback");
  const risk =
    (props.meta.risk_profiles || []).find((x) => x.value === ent.risk_profile)?.label ||
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

function selectAndEdit(ent) {
  emit("update:selectedId", ent.id);
  startEdit(ent);
}

function selectOnly(ent) {
  emit("update:selectedId", ent.id);
}

async function handleSaveEnterprise() {
  if (!(form.value.name || "").trim()) {
    ui.warning(t("carbonAssistant.enterpriseNameRequired"));
    return;
  }
  if (!form.value.industry) {
    ui.warning(t("carbonAssistant.enterpriseIndustryRequired"));
    return;
  }
  saving.value = true;
  try {
    await props.saveEnterprise({ ...form.value, single_trade_limit: 0 }, editingId.value || null);
    ui.success(editingId.value ? t("carbonAssistant.enterpriseUpdated") : t("carbonAssistant.enterpriseCreated"));
    startCreate();
  } catch (e) {
    ui.error(e?.message || t("carbonAssistant.enterpriseSaveFailed"));
  } finally {
    saving.value = false;
  }
}

async function handleDeleteEnterprise(id) {
  ui.confirmDelete({
    title: t("carbonAssistant.enterpriseDeleteTitle"),
    content: t("carbonAssistant.enterpriseDeleteConfirm"),
    onPositive: async () => {
      await props.removeEnterprise(id);
      ui.success(t("carbonAssistant.enterpriseDeleted"));
    },
  });
}

defineExpose({ enterpriseLabel, startCreate });
</script>

<template>
  <component
    :is="embedded ? 'div' : FeatureSection"
    v-bind="embedded ? { class: 'cc-fill-step-body' } : { title: t('carbonAssistant.enterpriseSectionTitle'), collapsible: true, defaultExpanded: false }"
  >
    <div class="cc-toolbar">
      <n-button size="small" @click="startCreate">{{ t("carbonAssistant.enterpriseCreate") }}</n-button>
      <span v-if="selectedId" class="cc-muted" style="margin: 0">
        {{
          t("carbonAssistant.enterpriseSelected", {
            name: enterpriseLabel(enterprises.find((e) => e.id === selectedId)) || selectedId,
          })
        }}
      </span>
      <span v-else class="cc-muted" style="margin: 0">{{ t("carbonAssistant.enterpriseSelectHint") }}</span>
    </div>

    <div class="cc-grid-2">
      <div>
        <n-empty v-if="!enterprises.length" :description="t('carbonAssistant.enterpriseEmpty')" />
        <div
          v-for="ent in enterprises"
          :key="ent.id"
          class="cc-ent-card"
          :class="{ 'cc-ent-card--selected': ent.id === selectedId }"
          @click="selectOnly(ent)"
        >
          <div class="cc-ent-head">
            <strong>{{ enterpriseLabel(ent) }}</strong>
            <n-tag v-if="ent.id === selectedId" size="tiny" type="success" :bordered="false">
              {{ t("carbonAssistant.enterpriseSelectedTag") }}
            </n-tag>
            <n-tag size="tiny" :bordered="false">{{ ent.industry }}</n-tag>
          </div>
          <div class="cc-muted">
            {{
              t("carbonAssistant.enterpriseMeta", {
                year: ent.market_start_year,
                budget: ent.annual_budget_cap,
              })
            }}
          </div>
          <div class="cc-row-actions" @click.stop>
            <n-button size="tiny" @click="selectAndEdit(ent)">{{ t("carbonAssistant.enterpriseEdit") }}</n-button>
            <n-button size="tiny" type="error" quaternary @click="handleDeleteEnterprise(ent.id)">
              {{ t("carbonAssistant.enterpriseDelete") }}
            </n-button>
          </div>
        </div>
      </div>

      <div>
        <div class="cc-subhead">
          {{ editingId ? t("carbonAssistant.enterpriseFormEdit") : t("carbonAssistant.enterpriseFormCreate") }}
        </div>
        <n-form label-placement="left" label-width="108" size="small">
          <n-form-item>
            <template #label>
              <span class="cc-form-label">
                {{ t("carbonAssistant.enterpriseName") }}
                <HintTooltip variant="field" :tip="t('carbonAssistant.enterpriseNameTip')" />
              </span>
            </template>
            <n-input
              v-model:value="form.name"
              size="small"
              :placeholder="t('carbonAssistant.enterpriseNamePlaceholder')"
              maxlength="128"
              show-count
            />
          </n-form-item>
          <n-form-item>
            <template #label>
              <span class="cc-form-label">
                {{ t("carbonAssistant.enterpriseIndustry") }}
                <HintTooltip variant="field" :tip="t('carbonAssistant.enterpriseIndustryTip')" />
              </span>
            </template>
            <n-select
              v-model:value="form.industry"
              size="small"
              :options="meta.industries || []"
              label-field="label"
              value-field="value"
              :placeholder="t('carbonAssistant.enterpriseIndustryPlaceholder')"
            />
          </n-form-item>
          <n-form-item>
            <template #label>
              <span class="cc-form-label">
                {{ t("carbonAssistant.enterpriseStartYear") }}
                <HintTooltip variant="field" :tip="t('carbonAssistant.enterpriseStartYearTip')" />
              </span>
            </template>
            <n-input-number
              v-model:value="form.market_start_year"
              size="small"
              :min="2013"
              :placeholder="t('carbonAssistant.enterpriseStartYearPlaceholder')"
            />
          </n-form-item>
          <n-form-item>
            <template #label>
              <span class="cc-form-label">
                {{ t("carbonAssistant.enterpriseRisk") }}
                <HintTooltip variant="field" :tip="t('carbonAssistant.enterpriseRiskTip')" />
              </span>
            </template>
            <n-select
              v-model:value="form.risk_profile"
              size="small"
              :options="meta.risk_profiles || []"
              label-field="label"
              value-field="value"
              :placeholder="t('carbonAssistant.enterpriseRiskPlaceholder')"
            />
          </n-form-item>
          <n-form-item>
            <template #label>
              <span class="cc-form-label">
                {{ t("carbonAssistant.enterpriseBudget") }}
                <HintTooltip variant="field" :tip="t('carbonAssistant.enterpriseBudgetTip')" />
              </span>
            </template>
            <n-input-number
              v-model:value="form.annual_budget_cap"
              size="small"
              :min="0"
              :placeholder="t('carbonAssistant.enterpriseBudgetPlaceholder')"
            />
          </n-form-item>
          <n-button type="primary" size="small" :loading="saving" @click="handleSaveEnterprise">
            {{ t("carbonAssistant.enterpriseSave") }}
          </n-button>
        </n-form>
      </div>
    </div>
  </component>
</template>
