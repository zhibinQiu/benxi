<script setup>
import { ref, computed } from "vue";
import { HelpCircleOutline } from "@vicons/ionicons5";
import FeatureSection from "../FeatureSection.vue";
import HintTooltip from "../HintTooltip.vue";
import { usePlatformUi } from "../../composables/usePlatformUi";
import { useI18n } from "../../composables/useI18n";
import { updateCarbonSettings } from "../../api/carbonCompliance";
import { carbonPageCache } from "../../composables/useCarbonEnterprise";

defineProps({
  /** 嵌入分步向导时不渲染外层 FeatureSection */
  embedded: { type: Boolean, default: false },
});

const settingsForm = defineModel("settingsForm", { type: Object, required: true });

const ui = usePlatformUi();
const { t } = useI18n();
const settingsSaving = ref(false);

const profileKeys = computed(() => [
  { key: "conservative", label: t("carbonAssistant.profileConservative") },
  { key: "balanced", label: t("carbonAssistant.profileBalanced") },
  { key: "aggressive", label: t("carbonAssistant.profileAggressive") },
]);

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

async function saveSettings() {
  settingsSaving.value = true;
  try {
    const payload = formToSettingsPayload(settingsForm.value);
    const next = await updateCarbonSettings(payload);
    carbonPageCache.settings = next;
    settingsForm.value = settingsToForm(next);
    ui.success(t("carbonAssistant.settingsSaved"));
  } catch (e) {
    ui.error(e?.message || t("carbonAssistant.settingsSaveFailed"));
  } finally {
    settingsSaving.value = false;
  }
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

defineExpose({ settingsToForm });
</script>

<template>
  <component
    :is="embedded ? 'div' : FeatureSection"
    v-bind="
      embedded
        ? { class: 'cc-fill-step-body' }
        : { title: t('carbonAssistant.settingsSectionTitle'), collapsible: true, defaultExpanded: false }
    "
  >
    <div class="cc-fill-step-hint">
      <n-popover trigger="click" placement="bottom-start" style="max-width: 340px">
        <template #trigger>
          <n-button quaternary size="tiny">
            <template #icon><n-icon :component="HelpCircleOutline" :size="14" /></template>
            {{ t("carbonAssistant.feeHelpBtn") }}
          </n-button>
        </template>
        <div class="cc-help-pop">
          <div class="cc-help-pop-title">{{ t("carbonAssistant.feeHelpTitle") }}</div>
          <p>{{ t("carbonAssistant.feeHelpP1") }}</p>
          <p>{{ t("carbonAssistant.feeHelpP2") }}</p>
          <p>{{ t("carbonAssistant.feeHelpP3") }}</p>
        </div>
      </n-popover>
    </div>
    <n-form label-placement="left" label-width="128" size="small" class="cc-settings-form">
      <div class="cc-subhead">{{ t("carbonAssistant.settingsComplianceHead") }}</div>
      <div class="cc-grid-2">
        <n-form-item>
          <template #label>
            <span class="cc-form-label">
              {{ t("carbonAssistant.fieldCcerRatio") }}
              <HintTooltip variant="field" :tip="t('carbonAssistant.fieldCcerRatioTip')" />
            </span>
          </template>
          <n-input-number
            v-model:value="settingsForm.ccer_max_ratio"
            size="small"
            :min="0"
            :max="1"
            :step="0.01"
            :precision="2"
            :placeholder="t('carbonAssistant.fieldCcerRatioPlaceholder')"
            style="width: 100%"
          />
        </n-form-item>
        <n-form-item>
          <template #label>
            <span class="cc-form-label">
              {{ t("carbonAssistant.fieldPriceLow") }}
              <HintTooltip variant="field" :tip="t('carbonAssistant.fieldPriceLowTip')" />
            </span>
          </template>
          <n-input-number
            v-model:value="settingsForm.price_low_percentile"
            size="small"
            :min="0.05"
            :max="0.5"
            :step="0.05"
            :precision="2"
            :placeholder="t('carbonAssistant.fieldPriceLowPlaceholder')"
            style="width: 100%"
          />
        </n-form-item>
        <n-form-item>
          <template #label>
            <span class="cc-form-label">
              {{ t("carbonAssistant.fieldPriceMid") }}
              <HintTooltip variant="field" :tip="t('carbonAssistant.fieldPriceMidTip')" />
            </span>
          </template>
          <n-input-number
            v-model:value="settingsForm.price_mid_percentile"
            size="small"
            :min="0.5"
            :max="0.95"
            :step="0.05"
            :precision="2"
            :placeholder="t('carbonAssistant.fieldPriceMidPlaceholder')"
            style="width: 100%"
          />
        </n-form-item>
        <n-form-item>
          <template #label>
            <span class="cc-form-label">
              {{ t("carbonAssistant.fieldWarnDays") }}
              <HintTooltip variant="field" :tip="t('carbonAssistant.fieldWarnDaysTip')" />
            </span>
          </template>
          <n-input
            v-model:value="settingsForm.clearance_warn_days"
            size="small"
            :placeholder="t('carbonAssistant.fieldWarnDaysPlaceholder')"
          />
        </n-form-item>
        <n-form-item>
          <template #label>
            <span class="cc-form-label">
              {{ t("carbonAssistant.fieldCarryDeadline") }}
              <HintTooltip variant="field" :tip="t('carbonAssistant.fieldCarryDeadlineTip')" />
            </span>
          </template>
          <n-input
            v-model:value="settingsForm.carry_forward_deadline_md"
            size="small"
            placeholder="06-10"
          />
        </n-form-item>
        <n-form-item>
          <template #label>
            <span class="cc-form-label">
              {{ t("carbonAssistant.fieldCarryBase") }}
              <HintTooltip variant="field" :tip="t('carbonAssistant.fieldCarryBaseTip')" />
            </span>
          </template>
          <n-input-number
            v-model:value="settingsForm.carry_base_qty"
            size="small"
            :min="0"
            :step="0.01"
            :placeholder="t('carbonAssistant.fieldCarryBasePlaceholder')"
            style="width: 100%"
          />
        </n-form-item>
        <n-form-item>
          <template #label>
            <span class="cc-form-label">
              {{ t("carbonAssistant.fieldCarryMultiplier") }}
              <HintTooltip variant="field" :tip="t('carbonAssistant.fieldCarryMultiplierTip')" />
            </span>
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

      <div class="cc-subhead">{{ t("carbonAssistant.settingsChannelHead") }}</div>
      <div class="cc-grid-2">
        <n-form-item>
          <template #label>
            <span class="cc-form-label">
              {{ t("carbonAssistant.fieldPreferOffline") }}
              <HintTooltip variant="field" :tip="t('carbonAssistant.fieldPreferOfflineTip')" />
            </span>
          </template>
          <n-switch v-model:value="settingsForm.prefer_offline" size="small" />
        </n-form-item>
        <n-form-item>
          <template #label>
            <span class="cc-form-label">
              {{ t("carbonAssistant.fieldOfflineDiscount") }}
              <HintTooltip variant="field" :tip="t('carbonAssistant.fieldOfflineDiscountTip')" />
            </span>
          </template>
          <n-input-number
            v-model:value="settingsForm.offline_discount_vs_listed"
            size="small"
            :min="0"
            :max="0.3"
            :step="0.01"
            :precision="2"
            :placeholder="t('carbonAssistant.fieldOfflineDiscountPlaceholder')"
            style="width: 100%"
            :disabled="!settingsForm.prefer_offline"
          />
        </n-form-item>
        <n-form-item>
          <template #label>
            <span class="cc-form-label">
              {{ t("carbonAssistant.fieldListingFee") }}
              <HintTooltip variant="field" :tip="t('carbonAssistant.fieldListingFeeTip')" />
            </span>
          </template>
          <n-input-number
            v-model:value="settingsForm.listing_fee_rate"
            size="small"
            :min="0"
            :max="0.05"
            :step="0.0001"
            :precision="4"
            :placeholder="t('carbonAssistant.fieldListingFeePlaceholder')"
            style="width: 100%"
          />
        </n-form-item>
        <n-form-item>
          <template #label>
            <span class="cc-form-label">
              {{ t("carbonAssistant.fieldBlockFee") }}
              <HintTooltip variant="field" :tip="t('carbonAssistant.fieldBlockFeeTip')" />
            </span>
          </template>
          <n-input-number
            v-model:value="settingsForm.block_fee_rate"
            size="small"
            :min="0"
            :max="0.05"
            :step="0.0001"
            :precision="4"
            :placeholder="t('carbonAssistant.fieldBlockFeePlaceholder')"
            style="width: 100%"
          />
        </n-form-item>
        <n-form-item>
          <template #label>
            <span class="cc-form-label">
              {{ t("carbonAssistant.fieldOverduePenalty") }}
              <HintTooltip variant="field" :tip="t('carbonAssistant.fieldOverduePenaltyTip')" />
            </span>
          </template>
          <n-input-number
            v-model:value="settingsForm.overdue_penalty_per_t"
            size="small"
            :min="0"
            :step="10"
            :placeholder="t('carbonAssistant.fieldOverduePenaltyPlaceholder')"
            style="width: 100%"
          />
        </n-form-item>
      </div>

      <div class="cc-subhead">
        {{ t("carbonAssistant.settingsProfileHead") }}
        <HintTooltip variant="field" :tip="t('carbonAssistant.settingsProfileTip')" />
      </div>
      <div class="cc-profile-grid">
        <div v-for="p in profileKeys" :key="p.key" class="cc-profile-card">
          <div class="cc-profile-title">{{ p.label }}</div>
          <n-space vertical :size="6">
            <n-checkbox v-model:checked="settingsForm.profiles[p.key].allow_buy_external_ccer">
              {{ t("carbonAssistant.allowBuyCcer") }}
            </n-checkbox>
            <n-checkbox v-model:checked="settingsForm.profiles[p.key].allow_sell_surplus">
              {{ t("carbonAssistant.allowSellSurplus") }}
            </n-checkbox>
            <n-checkbox v-model:checked="settingsForm.profiles[p.key].allow_stockpile">
              {{ t("carbonAssistant.allowStockpile") }}
            </n-checkbox>
          </n-space>
        </div>
      </div>

      <div class="cc-toolbar cc-mt">
        <n-button type="primary" size="small" :loading="settingsSaving" @click="saveSettings">
          {{ t("carbonAssistant.saveConstraints") }}
        </n-button>
      </div>
    </n-form>
  </component>
</template>
