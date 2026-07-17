<template>
  <n-space vertical>
    <n-card title="LLM 实体/关系抽取" size="small">
      <n-form :model="form" label-placement="top">
        <n-form-item label="标题">
          <n-input v-model:value="form.title" placeholder="文档/会议标题" />
        </n-form-item>
        <n-form-item label="正文" required>
          <n-input v-model:value="form.text" type="textarea" :rows="8"
            placeholder="粘贴文档正文，LLM 将自动抽取实体和关系..." />
        </n-form-item>
        <n-form-item label="来源类型">
          <n-select v-model:value="form.source_type" :options="sourceOptions" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button type="primary" @click="handleExtract" :loading="extracting"
            :disabled="!form.text.trim()">
            <template #icon><n-icon><RocketOutline /></n-icon></template>
            开始抽取
          </n-button>
        </n-space>
      </template>
    </n-card>

    <n-card v-if="result" title="抽取结果" size="small">
      <n-result v-if="result.skipped" status="warning" :title="result.reason" />
      <div v-else>
        <n-descriptions :column="3" bordered size="small">
          <n-descriptions-item label="新增实体">
            <n-number-animation :from="0" :to="result.entities_created" />
          </n-descriptions-item>
          <n-descriptions-item label="新增关系">
            <n-number-animation :from="0" :to="result.relations_created" />
          </n-descriptions-item>
          <n-descriptions-item>
            <n-button size="small" @click="emit('extracted')">刷新列表</n-button>
          </n-descriptions-item>
        </n-descriptions>
      </div>
    </n-card>
  </n-space>
</template>

<script setup>
import { ref, reactive } from "vue";
import { useMessage } from "naive-ui";
import { RocketOutline } from "@vicons/ionicons5";
import { extractKgFromText } from "../../api/kg.js";

const props = defineProps({
  entityTypes: { type: Array, default: () => [] },
});

const emit = defineEmits(["extracted"]);

const message = useMessage();
const extracting = ref(false);
const result = ref(null);

const form = reactive({
  title: "文档抽取",
  text: "",
  source_type: "manual",
});

const sourceOptions = [
  { label: "手动输入", value: "manual" },
  { label: "会议总结", value: "meeting_summary" },
  { label: "文档抽取", value: "extraction" },
];

async function handleExtract() {
  if (!form.text.trim()) {
    message.warning("请输入正文");
    return;
  }
  extracting.value = true;
  result.value = null;
  try {
    const res = await extractKgFromText(form.title || "文档抽取", form.text, {
      sourceType: form.source_type,
    });
    result.value = res || { skipped: true, reason: "无返回" };
    if (!result.value.skipped) {
      message.success(`抽取完成: ${result.value.entities_created || 0} 实体, ${result.value.relations_created || 0} 关系`);
    }
  } catch (err) {
    message.error("抽取失败: " + (err.message || ""));
    result.value = { skipped: true, reason: err.message };
  } finally {
    extracting.value = false;
  }
}
</script>
