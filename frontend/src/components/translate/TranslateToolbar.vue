<script setup>
import { computed } from "vue";
import { NProgress, NTag, NText } from "naive-ui";
import { useI18n } from "../../composables/useI18n";

const props = defineProps({
  showProgress: { type: Boolean, default: false },
  status: { type: String, default: "idle" },
  statusLabel: { type: String, default: "" },
  statusType: { type: String, default: "default" },
  progress: { type: Number, default: 0 },
  stage: { type: String, default: "" },
  platformJobId: { type: String, default: null },
});

const { t, featureDescription } = useI18n();

const showProgressBar = computed(
  () => props.showProgress && (props.status === "running" || props.status === "done")
);
</script>

<template>
  <div class="translate-actions-bar">
    <div class="translate-actions-toolbar">
      <NText depth="3" class="translate-actions-hint">
        {{ featureDescription("translate") }}
      </NText>

      <div v-if="showProgress" class="translate-toolbar-progress">
        <NTag :type="statusType" round size="small">{{ statusLabel }}</NTag>
        <span
          v-if="status === 'running'"
          class="translate-toolbar-progress__pulse"
          aria-hidden="true"
        />

        <div v-if="showProgressBar" class="translate-toolbar-progress__track">
          <NProgress
            type="line"
            :percentage="Math.round(progress)"
            :show-indicator="false"
            :processing="status === 'running'"
            :status="status === 'done' ? 'success' : 'default'"
            :height="7"
            :border-radius="3"
          />
          <NText strong class="translate-toolbar-progress__pct">
            {{ Math.round(progress) }}%
          </NText>
        </div>

        <NText
          v-if="stage"
          depth="2"
          class="translate-toolbar-progress__stage"
          :title="stage"
        >
          {{ stage }}
        </NText>

        <NTag
          v-if="platformJobId"
          size="tiny"
          round
          type="info"
          :bordered="false"
          class="translate-toolbar-progress__job"
        >
          {{ t("translate.jobTag", { id: platformJobId.slice(0, 8) }) }}
        </NTag>
      </div>
    </div>
  </div>
</template>

<style scoped>
.translate-actions-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
  min-height: 48px;
  width: 100%;
}

.translate-actions-hint {
  flex: 1 1 240px;
  min-width: 0;
  font-size: var(--platform-font-size-sm);
  line-height: 1.45;
}

.translate-toolbar-progress {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1 1 336px;
  justify-content: flex-end;
  min-width: 0;
}

.translate-toolbar-progress__pulse {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--platform-accent);
  flex-shrink: 0;
  animation: translate-toolbar-pulse 1.4s ease-in-out infinite;
}

@keyframes translate-toolbar-pulse {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.45;
    transform: scale(0.85);
  }
}

.translate-toolbar-progress__track {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1 1 192px;
  max-width: 288px;
  min-width: 144px;
}

.translate-toolbar-progress__track :deep(.n-progress) {
  flex: 1;
  min-width: 0;
}

.translate-toolbar-progress__pct {
  flex-shrink: 0;
  font-size: var(--platform-font-size-sm);
  color: var(--platform-accent);
  min-width: 2.5em;
  text-align: right;
}

.translate-toolbar-progress__stage {
  flex: 0 1 auto;
  max-width: min(264px, 32vw);
  font-size: var(--platform-font-size-sm);
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.translate-toolbar-progress__job {
  flex-shrink: 0;
}
</style>
