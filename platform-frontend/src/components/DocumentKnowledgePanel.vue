<script setup>
import { computed, onMounted, ref, watch } from "vue";
import {
  NAlert,
  NButton,
  NCard,
  NSelect,
  NSpace,
  NSwitch,
  NTag,
  NText,
  useMessage,
} from "naive-ui";
import { fetchParserOptions, reindexDocument } from "../api/knowledge.js";
import { knowledgeIndexTagProps } from "../utils/knowledgeIndex.js";

const props = defineProps({
  documentId: { type: String, required: true },
  title: { type: String, default: "" },
  /** DocumentVersionOut[] */
  versions: { type: Array, default: () => [] },
  currentVersionId: { type: String, default: null },
  canManage: { type: Boolean, default: false },
});

const emit = defineEmits(["updated"]);

const message = useMessage();

const selectedVersionId = ref(null);
const parserId = ref("smart");
const layoutRecognize = ref("DeepDOC");
const chunkMethodOptions = ref([]);
const layoutOptions = ref([]);
const configHints = ref([]);
const resyncBeforeReindex = ref(false);
const reparsing = ref(false);

const uploadedVersions = computed(() =>
  (props.versions || []).filter((v) => v.uploaded)
);

const versionOptions = computed(() =>
  uploadedVersions.value.map((v) => ({
    label: `v${v.version_no}${v.is_current ? "（当前）" : ""}`,
    value: v.id,
  }))
);

const activeVersion = computed(
  () => uploadedVersions.value.find((v) => v.id === selectedVersionId.value) || null
);

const indexTag = computed(() =>
  knowledgeIndexTagProps({
    knowledge_synced: activeVersion.value?.knowledge_synced,
    parse_status: activeVersion.value?.parse_status,
  })
);

const parseFailed = computed(
  () =>
    activeVersion.value?.parse_status === "解析失败" ||
    activeVersion.value?.parse_status === "索引失效"
);

function pickDefaultVersion() {
  const list = uploadedVersions.value;
  if (!list.length) {
    selectedVersionId.value = null;
    return;
  }
  const current = list.find((v) => v.id === props.currentVersionId);
  selectedVersionId.value = current?.id || list[list.length - 1]?.id || null;
}

function mapSelectOptions(items = []) {
  return items.map((p) => ({
    label: p.hint ? `${p.label}（${p.hint}）` : p.label,
    value: p.id,
  }));
}

async function loadParserOptions() {
  try {
    const data = await fetchParserOptions();
    const methods = data?.chunk_methods || data?.items || [];
    chunkMethodOptions.value = mapSelectOptions(methods);
    layoutOptions.value = mapSelectOptions(data?.layout_recognizers || []);
    configHints.value = data?.config_hints || [];
    const defaults = data?.defaults || {};
    if (defaults.parser_id) parserId.value = defaults.parser_id;
    if (defaults.layout_recognize) layoutRecognize.value = defaults.layout_recognize;
  } catch {
    chunkMethodOptions.value = [
      { label: "智能分块（推荐）", value: "smart" },
      { label: "Naive（通用）", value: "naive" },
    ];
    layoutOptions.value = [
      { label: "DeepDOC", value: "DeepDOC" },
      { label: "PaddleOCR", value: "PaddleOCR" },
    ];
  }
}

async function handleReindex() {
  if (!props.documentId || !selectedVersionId.value) return;
  reparsing.value = true;
  try {
    const ver = activeVersion.value;
    const res = await reindexDocument(props.documentId, {
      versionId: selectedVersionId.value,
      parserId: parserId.value,
      layoutRecognize: layoutRecognize.value,
      resync:
        resyncBeforeReindex.value ||
        ver?.parse_status === "索引失效" ||
        !ver?.knowledge_synced,
    });
    message.success(res?.message || "已提交重新解析");
    emit("updated");
  } catch (e) {
    message.error(e?.message || "重新解析失败");
  } finally {
    reparsing.value = false;
  }
}

watch(
  () => [props.versions, props.currentVersionId],
  () => {
    pickDefaultVersion();
  },
  { deep: true, immediate: true }
);

onMounted(loadParserOptions);
</script>

<template>
  <n-card title="知识索引">
    <n-space vertical :size="14">
      <n-text depth="3" style="font-size: 12px">
        每个历史版本单独建立索引，供知识问答检索。可在此选择 PDF 解析器（OCR）与分块方法。
      </n-text>

      <n-space v-if="versionOptions.length" align="center" :size="10" wrap>
        <n-text depth="3">文档版本</n-text>
        <n-select
          v-model:value="selectedVersionId"
          size="small"
          style="min-width: 160px"
          :options="versionOptions"
        />
        <n-tag size="small" :type="indexTag.type" :bordered="false">
          {{ indexTag.label }}
        </n-tag>
        <n-text
          v-if="activeVersion?.chunk_count != null"
          depth="3"
          style="font-size: 13px"
        >
          切片数 {{ activeVersion.chunk_count }}
        </n-text>
      </n-space>

      <n-alert
        v-if="parseFailed"
        type="warning"
        :show-icon="false"
        style="margin: 0"
        title="解析失败"
      >
        <template v-if="activeVersion?.parse_message">
          {{ activeVersion.parse_message }}
        </template>
        <template v-else>
          常见原因：OCR 服务未启动、嵌入模型未在 KnowFlow 启用、或 Elasticsearch 异常。
          可改用 DeepDOC / 纯文本 后重新索引。
        </template>
      </n-alert>

      <n-alert
        v-else-if="activeVersion && !activeVersion.knowledge_synced"
        type="info"
        :show-icon="false"
        style="margin: 0"
      >
        该版本尚未同步到知识库。请先上传文件并点击「同步知识库」，或在此配置解析器后重新索引。
      </n-alert>

      <template v-if="canManage && selectedVersionId">
        <n-text depth="3" style="font-size: 12px">PDF 解析器（OCR / 版面识别）</n-text>
        <n-select
          v-model:value="layoutRecognize"
          size="small"
          :options="layoutOptions"
          placeholder="选择 PDF 解析器"
        />
        <n-text depth="3" style="font-size: 12px">分块方法</n-text>
        <n-select
          v-model:value="parserId"
          size="small"
          :options="chunkMethodOptions"
          placeholder="选择分块方法"
        />
        <n-space align="center" :size="8">
          <n-switch v-model:value="resyncBeforeReindex" size="small" />
          <n-text depth="3" style="font-size: 12px">重新索引前先全量同步</n-text>
        </n-space>
        <n-button type="primary" size="small" :loading="reparsing" @click="handleReindex">
          应用配置并重新索引
        </n-button>
      </template>

      <n-alert
        v-if="configHints.length"
        type="default"
        :show-icon="false"
        style="margin: 0"
        title="配置说明"
      >
        <ul class="parser-hints">
          <li v-for="(hint, idx) in configHints" :key="idx">{{ hint }}</li>
        </ul>
      </n-alert>
    </n-space>
  </n-card>
</template>

<style scoped>
.parser-hints {
  margin: 0;
  padding-left: 1.1em;
  font-size: 12px;
  line-height: 1.55;
  color: var(--n-text-color-3);
}
</style>
