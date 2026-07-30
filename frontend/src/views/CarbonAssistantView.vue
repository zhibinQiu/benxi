<script setup>
defineOptions({ name: "CarbonAssistantView" });
import { ref, computed, watch, onMounted, onUnmounted, onActivated, onDeactivated, nextTick } from "vue";
import { usePlatformUi } from "../composables/usePlatformUi";
import { useI18n } from "../composables/useI18n";
import { useCarbonEnterprise } from "../composables/useCarbonEnterprise";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import FeatureSection from "../components/FeatureSection.vue";
import HintTooltip from "../components/HintTooltip.vue";
import CarbonMarketPanel from "../components/carbon/CarbonMarketPanel.vue";
import CarbonEnterprisePanel from "../components/carbon/CarbonEnterprisePanel.vue";
import CarbonEmissionPanel from "../components/carbon/CarbonEmissionPanel.vue";
import CarbonSettingsPanel from "../components/carbon/CarbonSettingsPanel.vue";
import CarbonReportSidebar from "../components/carbon/CarbonReportSidebar.vue";
import { isRouteAbortError } from "../api/http.js";

const ui = usePlatformUi();
const { t } = useI18n();
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
const forecastMethod = ref("rule");
const forecastMethodOptions = computed(() => [
  { label: t("carbonAssistant.forecastRule"), value: "rule" },
  { label: t("carbonAssistant.forecastEts"), value: "ets" },
  { label: t("carbonAssistant.forecastSarimax"), value: "sarimax" },
  { label: t("carbonAssistant.forecastProphet"), value: "prophet" },
]);

const marketPanelRef = ref(null);
const enterprisePanelRef = ref(null);
const emissionPanelRef = ref(null);
const settingsPanelRef = ref(null);
const reportSidebarRef = ref(null);

/** 分步填报：1 企业 → 2 排放 → 3 CEA → 4 CCER → 5 策略 → 6 生成报告 */
const FILL_STEPS = computed(() => [
  { key: "enterprise", title: t("carbonAssistant.stepEnterprise"), description: t("carbonAssistant.stepEnterpriseDesc") },
  { key: "emission", title: t("carbonAssistant.stepEmission"), description: t("carbonAssistant.stepEmissionDesc") },
  { key: "cea", title: t("carbonAssistant.stepCea"), description: t("carbonAssistant.stepCeaDesc") },
  { key: "ccer", title: t("carbonAssistant.stepCcer"), description: t("carbonAssistant.stepCcerDesc") },
  { key: "settings", title: t("carbonAssistant.stepSettings"), description: t("carbonAssistant.stepSettingsDesc") },
  { key: "report", title: t("carbonAssistant.stepReport"), description: t("carbonAssistant.stepReportDesc") },
]);

const fillStep = ref(1);
const fillStepCurrent = computed(() => fillStep.value);
const isLastFillStep = computed(() => fillStep.value >= FILL_STEPS.value.length);
const assetStepKey = computed(() => {
  const key = FILL_STEPS.value[fillStep.value - 1]?.key;
  return key === "emission" || key === "cea" || key === "ccer" ? key : "";
});

function goFillStep(step) {
  if (step < 1 || step > FILL_STEPS.value.length) return;
  fillStep.value = step;
}

function nextFillStep() {
  if (fillStep.value === 1 && !selectedId.value) {
    ui.warning(t("carbonAssistant.selectEnterpriseFirst"));
    return;
  }
  if (isLastFillStep.value) return;
  goFillStep(fillStep.value + 1);
}

function prevFillStep() {
  goFillStep(fillStep.value - 1);
}

function handleGenerateReport() {
  reportSidebarRef.value?.startAnalysis?.();
}

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

const settingsForm = ref(emptySettingsForm());

/** 初始化中：避免 selectedId 赋值触发重复拉台账 */
let bootstrapping = false;

function enterpriseLabel(ent) {
  return enterprisePanelRef.value?.enterpriseLabel?.(ent) || "";
}

function handleSettingsLoaded(settings) {
  const toForm = settingsPanelRef.value?.settingsToForm;
  if (toForm) settingsForm.value = toForm(settings);
}

watch(selectedId, async (id, prev) => {
  emissionPanelRef.value?.closeAllModals?.();
  if (bootstrapping || id === prev) return;
  await emissionPanelRef.value?.loadAssets?.();
});

onMounted(async () => {
  bootstrapping = true;
  try {
    await loadMeta();
    await loadEnterprises();
    await marketPanelRef.value?.loadMarket?.({ autoSync: false });
    await emissionPanelRef.value?.loadAssets?.();
    await reportSidebarRef.value?.fetchAllReports?.();
    if (reportSidebarRef.value?.hasRunningTasks?.()) {
      reportSidebarRef.value.startPolling();
    }
    await nextTick();
    marketPanelRef.value?.resizeChart?.();
    setTimeout(() => marketPanelRef.value?.refreshMarketSourceInfo?.(), 800);
  } catch (e) {
    if (!isRouteAbortError(e)) ui.error(e?.message || t("carbonAssistant.initFailed"));
  } finally {
    bootstrapping = false;
  }
});

onActivated(() => {
  if (reportSidebarRef.value?.hasRunningTasks?.()) {
    reportSidebarRef.value.startPolling();
  }
});
onDeactivated(() => {
  reportSidebarRef.value?.stopPolling?.();
});

onUnmounted(() => {
  reportSidebarRef.value?.stopPolling?.();
  emissionPanelRef.value?.closeAllModals?.();
});
</script>

<template>
  <FeatureSubsystemShell fill :show-intro="false">
    <div class="cc-view">
      <div class="cc-body">
        <div class="cc-main">
          <FeatureSection :title="t('carbonAssistant.fillStepsTitle')" collapsible :default-expanded="true">
            <n-steps :current="fillStepCurrent" size="small" class="cc-fill-steps">
              <n-step
                v-for="(s, idx) in FILL_STEPS"
                :key="s.key"
                class="cc-fill-step-item"
                :title="s.title"
                :description="s.description"
                @click="goFillStep(idx + 1)"
              />
            </n-steps>

            <div class="cc-fill-step-panel">
              <CarbonEnterprisePanel
                v-show="fillStep === 1"
                ref="enterprisePanelRef"
                embedded
                v-model:selected-id="selectedId"
                :enterprises="enterprises"
                :meta="meta"
                :save-enterprise="saveEnterprise"
                :remove-enterprise="removeEnterprise"
              />
              <div v-show="fillStep >= 2 && fillStep <= 4">
                <CarbonEmissionPanel
                  ref="emissionPanelRef"
                  embedded
                  :asset-step="assetStepKey"
                  :selected-id="selectedId"
                  :selected="selected"
                  :enterprise-label="enterpriseLabel"
                />
              </div>
              <CarbonSettingsPanel
                v-show="fillStep === 5"
                ref="settingsPanelRef"
                embedded
                v-model:settings-form="settingsForm"
              />
              <div v-show="fillStep === 6" class="cc-fill-step-body">
                <n-alert type="info" :bordered="false" class="cc-fill-step-hint">
                  {{ t("carbonAssistant.stepReportHint") }}
                </n-alert>
                <div v-if="selected" class="cc-side-ent-meta cc-mb">
                  {{ t("carbonAssistant.analyzeCurrentEntity", { name: enterpriseLabel(selected) }) }}
                  <span v-if="selected.industry"> · {{ selected.industry }}</span>
                </div>
                <div v-else class="cc-side-ent-meta cc-mb">{{ t("carbonAssistant.analyzeSelectFirst") }}</div>
                <div class="cc-report-params">
                  <div class="cc-side-analyze-row">
                    <span class="cc-inline-label">
                      {{ t("carbonAssistant.complianceYear") }}
                      <HintTooltip variant="field" :tip="t('carbonAssistant.complianceYearTip')" />
                    </span>
                    <n-input-number
                      v-model:value="complianceYear"
                      size="small"
                      :min="2018"
                      :placeholder="t('carbonAssistant.complianceYearPlaceholder')"
                      style="width: 100%; max-width: 280px"
                    />
                  </div>
                  <div class="cc-side-analyze-row">
                    <span class="cc-inline-label">
                      {{ t("carbonAssistant.forecastMethod") }}
                      <HintTooltip variant="field" :tip="t('carbonAssistant.forecastMethodTip')" />
                    </span>
                    <n-select
                      v-model:value="forecastMethod"
                      size="small"
                      :options="forecastMethodOptions"
                      style="width: 100%; max-width: 280px"
                    />
                  </div>
                </div>
              </div>
            </div>

            <div class="cc-fill-nav">
              <n-button size="small" :disabled="fillStep <= 1" @click="prevFillStep">
                {{ t("carbonAssistant.stepPrev") }}
              </n-button>
              <span class="cc-muted cc-fill-nav-meta">
                {{
                  t("carbonAssistant.stepMeta", {
                    current: fillStep,
                    total: FILL_STEPS.length,
                    title: FILL_STEPS[fillStep - 1]?.title,
                  })
                }}
              </span>
              <n-button
                v-if="!isLastFillStep"
                size="small"
                type="primary"
                @click="nextFillStep"
              >
                {{ t("carbonAssistant.stepNext") }}
              </n-button>
              <n-button
                v-else
                size="small"
                type="primary"
                :loading="!!reportSidebarRef?.submitting"
                :disabled="!selectedId || !!reportSidebarRef?.submitting"
                @click="handleGenerateReport"
              >
                {{
                  (reportSidebarRef?.runningTaskCount || 0) > 0
                    ? t("carbonAssistant.appendReport")
                    : t("carbonAssistant.generateReport")
                }}
              </n-button>
            </div>
          </FeatureSection>

          <CarbonMarketPanel ref="marketPanelRef" @settings-loaded="handleSettingsLoaded" />
        </div>

        <CarbonReportSidebar
          ref="reportSidebarRef"
          v-model:compliance-year="complianceYear"
          v-model:forecast-method="forecastMethod"
          :selected-id="selectedId"
          :selected="selected"
          :enterprise-label="enterpriseLabel"
        />
      </div>
    </div>
  </FeatureSubsystemShell>
</template>

<style src="../styles/pages/carbon-assistant.css"></style>
