<script setup>
defineOptions({ name: "AutoMlView" });
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import {
  NAlert,
  NButton,
  NCheckbox,
  NCheckboxGroup,
  NDataTable,
  NFormItem,
  NIcon,
  NInputNumber,
  NProgress,
  NRadio,
  NRadioGroup,
  NSelect,
  NSpace,
  NSpin,
  NSwitch,
  NTag,
  NUpload,
  NUploadDragger,
} from "naive-ui";
import { CloudUploadOutline } from "@vicons/ionicons5";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import { usePlatformUi } from "../composables/usePlatformUi";
import {
  createAutoMlRun,
  downloadAutoMlModel,
  downloadAutoMlPredictions,
  fetchAutoMlMeta,
  fetchAutoMlModels,
  fetchAutoMlRun,
  uploadAutoMlDataset,
} from "../api/automl.js";

const ui = usePlatformUi();

const loadingMeta = ref(true);
const meta = ref(null);
const uploading = ref(false);
const datasetId = ref("");
const profile = ref(null);

const task = ref("classification");
const target = ref(null);
const dateColumn = ref(null);
const featureColumns = ref([]);
const ignoreFeatures = ref([]);
const normalize = ref(true);
const fh = ref(3);

const compare = ref(true);
const modelIds = ref([]);
const modelOptions = ref([]);
const loadingModels = ref(false);

const submitting = ref(false);
const runId = ref("");
const run = ref(null);
let pollTimer = null;

const configured = computed(() => Boolean(meta.value?.configured));
const acceptedFormats = computed(() =>
  (meta.value?.accepted_extensions || [".csv"]).join(",")
);
const maxMb = computed(() => meta.value?.max_file_mb || 50);

const taskOptions = computed(() =>
  (meta.value?.task_types || []).map((t) => ({
    label: t.label,
    value: t.id,
  }))
);

const selectedTaskMeta = computed(() =>
  (meta.value?.task_types || []).find((t) => t.id === task.value)
);

const needsTarget = computed(() => Boolean(selectedTaskMeta.value?.needs_target));
const supportsCompare = computed(() =>
  selectedTaskMeta.value?.supports_compare !== false
);
const isTimeSeries = computed(() => task.value === "time_series");
const isUnsupervised = computed(() =>
  task.value === "clustering" || task.value === "anomaly"
);

const columnOptions = computed(() =>
  (profile.value?.column_profiles || []).map((c) => ({
    label: `${c.name} (${c.dtype})`,
    value: c.name,
  }))
);

const canGoStep2 = computed(() => Boolean(datasetId.value && profile.value));
const canGoStep3 = computed(() => {
  if (!canGoStep2.value) return false;
  if (needsTarget.value && !target.value) return false;
  if (isTimeSeries.value && fh.value < 1) return false;
  return true;
});
const canGoStep4 = computed(() => {
  if (!canGoStep3.value) return false;
  if (isUnsupervised.value) return modelIds.value.length > 0 || Boolean(selectedTaskMeta.value?.default_model);
  if (compare.value) return true;
  return modelIds.value.length > 0;
});

const runDone = computed(() => run.value?.status === "done");
const runFailed = computed(() => run.value?.status === "failed");
const runBusy = computed(() =>
  ["pending", "running"].includes(String(run.value?.status || ""))
);

const metricsColumns = computed(() => {
  const rows = run.value?.metrics || [];
  if (!rows.length) return [];
  const keys = Object.keys(rows[0]);
  return keys.map((k) => ({
    title: k,
    key: k,
    ellipsis: { tooltip: true },
    minWidth: 100,
  }));
});

const previewColumns = computed(() =>
  (run.value?.prediction_columns || []).map((k) => ({
    title: k,
    key: k,
    ellipsis: { tooltip: true },
    minWidth: 90,
  }))
);

const sampleTableColumns = computed(() =>
  (profile.value?.column_profiles || []).map((c) => ({
    title: c.name,
    key: c.name,
    ellipsis: { tooltip: true },
    minWidth: 90,
  }))
);

const sampleTableData = computed(() => {
  const cols = profile.value?.column_profiles || [];
  const rows = profile.value?.sample_rows || [];
  return rows.map((row) => {
    const obj = {};
    cols.forEach((c, i) => {
      obj[c.name] = row[i] ?? "";
    });
    return obj;
  });
});

function stopPoll() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function loadMeta() {
  loadingMeta.value = true;
  try {
    meta.value = await fetchAutoMlMeta();
  } catch (e) {
    meta.value = {
      configured: false,
      service_hint: e?.message || "无法加载配置",
      max_file_mb: 50,
      accepted_extensions: [".csv"],
      task_types: [],
    };
  } finally {
    loadingMeta.value = false;
  }
}

async function loadModels() {
  if (!task.value) return;
  loadingModels.value = true;
  try {
    const data = await fetchAutoMlModels(task.value);
    modelOptions.value = (data?.models || []).map((m) => ({
      label: `${m.name} (${m.id})`,
      value: m.id,
    }));
    const def = selectedTaskMeta.value?.default_model;
    if (isUnsupervised.value && def && !modelIds.value.length) {
      modelIds.value = [def];
    }
  } catch (e) {
    modelOptions.value = [];
    ui.error(e?.message || "加载模型列表失败");
  } finally {
    loadingModels.value = false;
  }
}

watch(task, () => {
  target.value = null;
  dateColumn.value = null;
  modelIds.value = [];
  compare.value = supportsCompare.value;
  loadModels();
});

watch(supportsCompare, (ok) => {
  if (!ok) compare.value = false;
});

async function onUploadChange({ file }) {
  const raw = file?.file;
  if (!raw) return;
  if (!String(raw.name || "").toLowerCase().endsWith(".csv")) {
    ui.warning("仅支持 CSV 文件");
    return;
  }
  uploading.value = true;
  try {
    const data = await uploadAutoMlDataset(raw);
    datasetId.value = data.dataset_id;
    profile.value = data.profile;
    featureColumns.value = (data.profile?.column_profiles || []).map((c) => c.name);
    ignoreFeatures.value = [];
    target.value = null;
    dateColumn.value = null;
    runId.value = "";
    run.value = null;
    ui.success("数据集已上传");
    loadModels();
  } catch (e) {
    ui.error(e?.message || "上传失败");
  } finally {
    uploading.value = false;
  }
}

async function startRun() {
  if (!canGoStep2.value) {
    ui.warning("请先上传 CSV");
    return;
  }
  if (!canGoStep3.value) {
    ui.warning(needsTarget.value ? "请选择目标列" : "请完善任务配置");
    return;
  }
  if (!canGoStep4.value) {
    ui.warning("请选择模型或开启自动比较");
    return;
  }
  submitting.value = true;
  stopPoll();
  try {
    const body = {
      dataset_id: datasetId.value,
      task: task.value,
      target: needsTarget.value ? target.value : null,
      feature_columns: featureColumns.value.length ? featureColumns.value : null,
      ignore_features: ignoreFeatures.value.length ? ignoreFeatures.value : [],
      compare: supportsCompare.value ? compare.value : false,
      model_ids: modelIds.value.length ? modelIds.value : null,
      normalize: normalize.value,
      date_column: isTimeSeries.value ? dateColumn.value : null,
      fh: Number(fh.value) || 3,
    };
    const data = await createAutoMlRun(body);
    runId.value = data.run_id;
    run.value = data;
    ui.success("已提交训练任务");
    pollTimer = setInterval(refreshRun, 2000);
  } catch (e) {
    ui.error(e?.message || "提交失败");
  } finally {
    submitting.value = false;
  }
}

async function refreshRun() {
  if (!runId.value) return;
  try {
    const data = await fetchAutoMlRun(runId.value);
    run.value = data;
    if (["done", "failed", "cancelled"].includes(data.status)) {
      stopPoll();
    }
  } catch {
    /* keep polling */
  }
}

async function onDownloadPredictions() {
  try {
    await downloadAutoMlPredictions(runId.value);
  } catch (e) {
    ui.error(e?.message || "下载失败");
  }
}

async function onDownloadModel() {
  try {
    await downloadAutoMlModel(runId.value);
  } catch (e) {
    ui.error(e?.message || "下载失败");
  }
}

function resetAll() {
  stopPoll();
  datasetId.value = "";
  profile.value = null;
  task.value = "classification";
  target.value = null;
  dateColumn.value = null;
  featureColumns.value = [];
  ignoreFeatures.value = [];
  compare.value = true;
  modelIds.value = [];
  runId.value = "";
  run.value = null;
}

onMounted(async () => {
  await loadMeta();
  if (configured.value) loadModels();
});
onUnmounted(stopPoll);
</script>

<template>
  <FeatureSubsystemShell fill :show-intro="false">
    <div class="automl-page">
      <div class="automl-toolbar">
        <NButton quaternary size="small" @click="resetAll">重新开始</NButton>
      </div>

      <NSpin :show="loadingMeta">
        <NAlert
          v-if="meta && !configured"
          type="warning"
          title="自动化机器学习暂不可用"
          style="margin-bottom: 16px"
        >
          {{ meta.service_hint || "当前运行环境未安装 PyCaret，请联系管理员重建 API 镜像（./dev.sh sync --automl）" }}
        </NAlert>

        <section class="automl-panel">
          <h2 class="automl-section-title">1. 数据与任务</h2>
          <NFormItem label="上传 CSV" :show-feedback="false">
            <div class="automl-upload-row">
              <NUpload
                class="automl-upload-compact"
                :accept="acceptedFormats"
                :show-file-list="false"
                :default-upload="false"
                :disabled="!configured || uploading"
                @change="onUploadChange"
              >
                <NUploadDragger>
                  <div class="automl-upload">
                    <NIcon :size="22" :component="CloudUploadOutline" />
                    <div class="automl-upload-title">
                      {{ uploading ? "上传中…" : "点击或拖拽上传" }}
                    </div>
                    <div class="automl-upload-hint">.csv · ≤{{ maxMb }}MB</div>
                  </div>
                </NUploadDragger>
              </NUpload>
              <NTag v-if="profile" type="success" size="small">
                {{ profile.filename }} · {{ profile.rows }}×{{ profile.columns }}
              </NTag>
            </div>
          </NFormItem>
          <NDataTable
            v-if="sampleTableData.length"
            size="small"
            :columns="sampleTableColumns"
            :data="sampleTableData"
            :bordered="false"
            :max-height="160"
            style="margin: 0 0 12px"
          />

          <NFormItem label="任务类型">
            <NRadioGroup v-model:value="task">
              <NSpace>
                <NRadio
                  v-for="opt in taskOptions"
                  :key="opt.value"
                  :value="opt.value"
                  :label="opt.label"
                />
              </NSpace>
            </NRadioGroup>
          </NFormItem>

          <NFormItem v-if="needsTarget" label="目标列" required>
            <NSelect
              v-model:value="target"
              :options="columnOptions"
              placeholder="选择预测目标"
              filterable
              clearable
              style="max-width: 360px"
            />
          </NFormItem>

          <NFormItem v-if="isTimeSeries" label="时间列（可选）">
            <NSelect
              v-model:value="dateColumn"
              :options="columnOptions"
              placeholder="设为索引的日期列"
              filterable
              clearable
              style="max-width: 360px"
            />
          </NFormItem>

          <NFormItem v-if="isTimeSeries" label="预测步长 fh">
            <NInputNumber v-model:value="fh" :min="1" :max="365" style="width: 160px" />
          </NFormItem>

          <NFormItem v-if="task === 'clustering'" label="标准化 normalize">
            <NSwitch v-model:value="normalize" />
          </NFormItem>

          <NFormItem label="使用的特征列">
            <NSelect
              v-model:value="featureColumns"
              :options="columnOptions"
              multiple
              filterable
              placeholder="默认全部列"
              style="max-width: 640px"
            />
          </NFormItem>

          <NFormItem label="忽略列">
            <NSelect
              v-model:value="ignoreFeatures"
              :options="columnOptions"
              multiple
              filterable
              placeholder="训练时忽略"
              style="max-width: 640px"
            />
          </NFormItem>
        </section>

        <section class="automl-panel">
          <h2 class="automl-section-title">2. 选择模型</h2>
          <NSpin :show="loadingModels">
            <NFormItem v-if="supportsCompare" label="自动比较模型（compare_models）">
              <NSwitch v-model:value="compare" />
            </NFormItem>
            <NFormItem :label="compare && supportsCompare ? '限定模型子集（可选）' : '选择模型'">
              <NCheckboxGroup v-model:value="modelIds">
                <NSpace vertical>
                  <NCheckbox
                    v-for="m in modelOptions"
                    :key="m.value"
                    :value="m.value"
                    :label="m.label"
                  />
                </NSpace>
              </NCheckboxGroup>
              <div v-if="!modelOptions.length" class="automl-muted">暂无可用模型列表</div>
            </NFormItem>
            <p v-if="isUnsupervised" class="automl-muted">
              聚类 / 异常检测不支持自动比较，将训练所选模型（默认
              {{ selectedTaskMeta?.default_model }}）。
            </p>
          </NSpin>
        </section>

        <section class="automl-panel">
          <h2 class="automl-section-title">3. 训练结果</h2>
          <div v-if="!run" class="automl-muted">配置完成后点击下方「开始训练」提交任务</div>
          <template v-else>
            <div class="automl-run-status">
              <NTag :type="runDone ? 'success' : runFailed ? 'error' : 'info'">
                {{ run.status }}
              </NTag>
              <span v-if="run.message">{{ run.message }}</span>
              <span v-if="run.best_model">最佳模型：{{ run.best_model }}</span>
            </div>
            <NProgress
              type="line"
              :percentage="Number(run.progress || 0)"
              :status="runFailed ? 'error' : runDone ? 'success' : 'default'"
              style="margin: 12px 0"
            />
            <NAlert v-if="runFailed && run.error_message" type="error" style="margin-bottom: 12px">
              {{ run.error_message }}
            </NAlert>

            <h3 v-if="(run.metrics || []).length" class="automl-section-title">评估指标</h3>
            <NDataTable
              v-if="(run.metrics || []).length"
              size="small"
              :columns="metricsColumns"
              :data="run.metrics"
              :bordered="false"
              :max-height="280"
            />

            <h3 v-if="(run.prediction_preview || []).length" class="automl-section-title">
              预测预览
            </h3>
            <NDataTable
              v-if="(run.prediction_preview || []).length"
              size="small"
              :columns="previewColumns"
              :data="run.prediction_preview"
              :bordered="false"
              :max-height="280"
            />

            <NSpace style="margin-top: 16px">
              <NButton
                v-if="run.has_predictions"
                type="primary"
                secondary
                @click="onDownloadPredictions"
              >
                下载预测 CSV
              </NButton>
              <NButton v-if="run.has_model" secondary @click="onDownloadModel">
                下载模型
              </NButton>
              <NButton v-if="runBusy" quaternary @click="refreshRun">刷新状态</NButton>
            </NSpace>
          </template>
        </section>

        <footer class="automl-footer">
          <NButton
            type="primary"
            :loading="submitting"
            :disabled="!configured || runBusy"
            @click="startRun"
          >
            开始训练
          </NButton>
        </footer>
      </NSpin>
    </div>
  </FeatureSubsystemShell>
</template>

<style scoped>
.automl-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: 8px 4px 16px;
  overflow: auto;
}
.automl-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 8px;
}
.automl-panel {
  padding: 4px 0 20px;
  border-bottom: 1px solid var(--border-color, rgba(0, 0, 0, 0.06));
}
.automl-panel:last-of-type {
  border-bottom: none;
}
.automl-upload-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  width: 100%;
}
.automl-upload-compact {
  width: 240px;
  max-width: 100%;
}
.automl-upload-compact :deep(.n-upload-dragger) {
  padding: 0;
}
.automl-upload {
  padding: 10px 12px;
  text-align: center;
}
.automl-upload-title {
  margin-top: 4px;
  font-size: 0.85rem;
  font-weight: 600;
}
.automl-upload-hint {
  margin-top: 2px;
  color: var(--text-secondary, #889);
  font-size: 0.75rem;
}
.automl-muted {
  color: var(--text-secondary, #889);
  font-size: 0.9rem;
  margin-top: 8px;
}
.automl-run-status {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}
.automl-section-title {
  margin: 8px 0 12px;
  font-size: 1rem;
  font-weight: 600;
}
.automl-footer {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  padding-top: 12px;
  position: sticky;
  bottom: 0;
  background: var(--card-color, #fff);
}
</style>
