<template>
  <n-space vertical>
    <n-card title="文档批量抽取" size="small">
      <n-space vertical :size="12">
        <n-text depth="3">
          读取已上传文档正文：先发现候选本体并写入 GraphDB，再用完整本体约束抽取实体/关系（写入 Neo4j）。
        </n-text>
        <n-space align="center" wrap>
          <n-text>最多文档</n-text>
          <n-input-number v-model:value="batch.maxDocs" :min="1" :max="50" size="small" style="width:100px" />
          <n-checkbox v-model:checked="batch.discoverOntology">发现并合并本体</n-checkbox>
          <n-checkbox v-model:checked="batch.force">强制重抽</n-checkbox>
          <n-button type="primary" :loading="batchExtracting" @click="handleBatchExtract">
            <template #icon><n-icon><DocumentsOutline /></n-icon></template>
            批量抽取文档
          </n-button>
        </n-space>
        <n-descriptions v-if="batchResult" :column="3" bordered size="small">
          <n-descriptions-item label="处理文档">{{ batchResult.processed || 0 }}</n-descriptions-item>
          <n-descriptions-item label="已跳过">{{ batchResult.skipped_already || 0 }}</n-descriptions-item>
          <n-descriptions-item label="错误">{{ batchResult.errors || 0 }}</n-descriptions-item>
          <n-descriptions-item label="新增实体">{{ batchResult.entities_created || 0 }}</n-descriptions-item>
          <n-descriptions-item label="新增关系">{{ batchResult.relations_created || 0 }}</n-descriptions-item>
          <n-descriptions-item label="新增本体类型">
            {{ (batchResult.entity_types_created || 0) + (batchResult.relation_types_created || 0) }}
            <n-text depth="3" style="margin-left:6px;font-size:12px">
              (实体 {{ batchResult.entity_types_created || 0 }} / 关系 {{ batchResult.relation_types_created || 0 }})
            </n-text>
          </n-descriptions-item>
        </n-descriptions>
      </n-space>
    </n-card>

    <n-card title="粘贴文本抽取" size="small">
      <n-form :model="form" label-placement="top">
        <n-form-item label="标题">
          <n-input v-model:value="form.title" placeholder="文档/会议标题" />
        </n-form-item>
        <n-form-item label="正文" required>
          <n-input
            v-model:value="form.text"
            type="textarea"
            :rows="8"
            placeholder="粘贴文档正文，将先发现本体再抽取实体/关系..."
          />
        </n-form-item>
        <n-form-item label="来源类型">
          <n-select v-model:value="form.source_type" :options="sourceOptions" />
        </n-form-item>
        <n-form-item>
          <n-checkbox v-model:checked="form.discoverOntology">发现并合并本体后再抽取</n-checkbox>
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button
            type="primary"
            :loading="extracting"
            :disabled="!form.text.trim()"
            @click="handleExtract"
          >
            <template #icon><n-icon><RocketOutline /></n-icon></template>
            开始抽取
          </n-button>
        </n-space>
      </template>
    </n-card>

    <n-card v-if="result" title="文本抽取结果" size="small">
      <n-result v-if="result.skipped" status="warning" :title="result.reason || '已跳过'" />
      <div v-else>
        <n-descriptions :column="3" bordered size="small">
          <n-descriptions-item label="新增实体">{{ result.entities_created || 0 }}</n-descriptions-item>
          <n-descriptions-item label="新增关系">{{ result.relations_created || 0 }}</n-descriptions-item>
          <n-descriptions-item label="丢弃不合规">{{ result.dropped || 0 }}</n-descriptions-item>
          <n-descriptions-item label="新增实体类型">
            {{ result.ontology?.entity_types_created || 0 }}
          </n-descriptions-item>
          <n-descriptions-item label="新增关系类型">
            {{ result.ontology?.relation_types_created || 0 }}
          </n-descriptions-item>
          <n-descriptions-item>
            <n-button size="small" @click="emit('extracted')">刷新列表</n-button>
          </n-descriptions-item>
        </n-descriptions>
        <n-alert
          v-if="(result.validation_errors || []).length"
          type="warning"
          style="margin-top:12px"
          title="约束校验提示"
        >
          <ul style="margin:0;padding-left:18px">
            <li v-for="(err, i) in result.validation_errors.slice(0, 8)" :key="i">{{ err }}</li>
          </ul>
        </n-alert>
      </div>
    </n-card>
  </n-space>
</template>

<script setup>
import { ref, reactive } from "vue";
import { RocketOutline, DocumentsOutline } from "@vicons/ionicons5";
import { usePlatformUi } from "../../composables/usePlatformUi";
import { extractKgFromText, extractKgDocuments } from "../../api/kg.js";
import { PLATFORM_JOBS_REFRESH_EVENT } from "../../constants/platformEvents.js";

defineProps({
  entityTypes: { type: Array, default: () => [] },
});

const emit = defineEmits(["extracted"]);

const ui = usePlatformUi();
const extracting = ref(false);
const batchExtracting = ref(false);
const result = ref(null);
const batchResult = ref(null);

const form = reactive({
  title: "文档抽取",
  text: "",
  source_type: "manual",
  discoverOntology: true,
});

const batch = reactive({
  maxDocs: 20,
  discoverOntology: true,
  force: false,
});

const sourceOptions = [
  { label: "手动输入", value: "manual" },
  { label: "会议总结", value: "meeting_summary" },
  { label: "文档抽取", value: "extraction" },
];

async function handleBatchExtract() {
  batchExtracting.value = true;
  batchResult.value = null;
  try {
    const res = await extractKgDocuments({
      maxDocs: batch.maxDocs,
      force: batch.force,
      discoverOntology: batch.discoverOntology,
    });
    batchResult.value = res || {};
    if (batchResult.value.queued || batchResult.value.job_id) {
      ui.success(
        batchResult.value.message ||
          "文档抽取已加入后台任务，可在右上角「后台任务」查看进度"
      );
      window.dispatchEvent(new CustomEvent(PLATFORM_JOBS_REFRESH_EVENT));
      return;
    }
    ui.success("文档抽取完成");
    emit("extracted");
  } catch (err) {
    if (err?.code === "ROUTE_ABORT") return;
    ui.error("批量抽取失败: " + (err.message || ""));
  } finally {
    batchExtracting.value = false;
  }
}

async function handleExtract() {
  if (!form.text.trim()) {
    ui.warning("请输入正文");
    return;
  }
  extracting.value = true;
  result.value = null;
  try {
    const res = await extractKgFromText(form.title || "文档抽取", form.text, {
      sourceType: form.source_type,
      discoverOntology: form.discoverOntology,
    });
    result.value = res || { skipped: true, reason: "无返回" };
    if (!result.value.skipped) {
      const ont = result.value.ontology || {};
      ui.success(
        `抽取完成: ${result.value.entities_created || 0} 实体, ${result.value.relations_created || 0} 关系` +
          (ont.entity_types_created || ont.relation_types_created
            ? `；本体 +${(ont.entity_types_created || 0) + (ont.relation_types_created || 0)}`
            : "")
      );
      emit("extracted");
    }
  } catch (err) {
    if (err?.code === "ROUTE_ABORT") return;
    ui.error("抽取失败: " + (err.message || ""));
    result.value = { skipped: true, reason: err.message };
  } finally {
    extracting.value = false;
  }
}
</script>
