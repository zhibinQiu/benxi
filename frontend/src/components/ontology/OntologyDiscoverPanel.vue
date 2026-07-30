<template>
  <n-space vertical :size="12">
    <n-alert type="info" :bordered="false">
      本面板只更新<strong>本体定义（TBox）</strong>：概念与关系类型。实例抽取请切换到「知识图谱」。
    </n-alert>

    <n-card title="粘贴文本发现" size="small">
      <n-form :model="form" label-placement="top" size="small">
        <n-form-item label="标题">
          <n-input v-model:value="form.title" placeholder="资料标题" />
        </n-form-item>
        <n-form-item label="正文" required>
          <n-input
            v-model:value="form.text"
            type="textarea"
            :rows="8"
            placeholder="粘贴业务文档、规范或说明正文…"
          />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button
            type="primary"
            :loading="discovering"
            :disabled="!form.text.trim()"
            @click="handleDiscoverText"
          >
            发现候选
          </n-button>
        </n-space>
      </template>
    </n-card>

    <n-card title="从文档发现" size="small">
      <n-space vertical :size="8">
        <n-text depth="3" style="font-size: 12px">
          选择可查询的文档，拼正文后发现概念/关系（同步，单次最多 20 份）。
        </n-text>
        <n-select
          v-model:value="selectedDocIds"
          multiple
          filterable
          :options="docOptions"
          :loading="loadingDocs"
          max-tag-count="responsive"
          placeholder="搜索并选择文档"
          @focus="ensureDocsLoaded"
          @search="onDocSearch"
        />
        <n-button
          type="primary"
          secondary
          :loading="discovering"
          :disabled="!selectedDocIds.length"
          @click="handleDiscoverDocs"
        >
          从文档发现候选
        </n-button>
      </n-space>
    </n-card>

    <n-card v-if="result" title="候选预览" size="small">
      <n-descriptions :column="3" size="small" bordered style="margin-bottom: 12px">
        <n-descriptions-item label="概念候选">
          {{ (result.entity_types || []).length }}
        </n-descriptions-item>
        <n-descriptions-item label="关系候选">
          {{ (result.relation_types || []).length }}
        </n-descriptions-item>
        <n-descriptions-item label="已跳过">
          {{ (result.skipped || []).length }}
        </n-descriptions-item>
      </n-descriptions>

      <n-text strong>概念</n-text>
      <n-data-table
        size="small"
        :columns="entityColumns"
        :data="entityRows"
        :pagination="false"
        style="margin: 8px 0 16px"
      />

      <n-text strong>关系类型</n-text>
      <n-data-table
        size="small"
        :columns="relationColumns"
        :data="relationRows"
        :pagination="false"
        style="margin: 8px 0 16px"
      />

      <n-collapse v-if="(result.skipped || []).length">
        <n-collapse-item title="跳过项" name="skipped">
          <ul style="margin: 0; padding-left: 18px; font-size: 12px">
            <li v-for="(s, i) in result.skipped.slice(0, 20)" :key="i">
              [{{ s.kind }}] {{ s.code || s.label }} — {{ s.reason }}
            </li>
          </ul>
        </n-collapse-item>
      </n-collapse>

      <n-space justify="end" style="margin-top: 12px">
        <n-button :disabled="!hasSelected" :loading="applying" type="primary" @click="handleApply">
          写入本体
        </n-button>
      </n-space>
    </n-card>
  </n-space>
</template>

<script setup>
import { computed, h, reactive, ref } from "vue";
import { NCheckbox, NTag } from "naive-ui";
import { usePlatformUi } from "../../composables/usePlatformUi";
import { fetchDocuments } from "../../api/documents.js";
import {
  applyOntologyDiscover,
  discoverOntologyFromDocuments,
  discoverOntologyFromText,
} from "../../api/ontology.js";

const emit = defineEmits(["applied"]);

const ui = usePlatformUi();
const discovering = ref(false);
const applying = ref(false);
const result = ref(null);
const entityRows = ref([]);
const relationRows = ref([]);
const loadingDocs = ref(false);
const docOptions = ref([]);
const selectedDocIds = ref([]);
let docsLoaded = false;

const form = reactive({
  title: "文档抽取",
  text: "",
});

const actionTag = (action) => {
  const type =
    action === "create" ? "success" : action === "merge" ? "warning" : "default";
  const label =
    action === "create" ? "新建" : action === "merge" ? "合并" : action === "exists" ? "已存在" : action;
  return h(NTag, { size: "small", type, bordered: false }, { default: () => label });
};

const entityColumns = [
  {
    title: "选",
    key: "selected",
    width: 48,
    render(row) {
      if (row.action === "exists") return null;
      return h(NCheckbox, {
        checked: row.selected,
        "onUpdate:checked": (v) => {
          row.selected = v;
        },
      });
    },
  },
  { title: "code", key: "code", ellipsis: { tooltip: true } },
  { title: "名称", key: "label", ellipsis: { tooltip: true } },
  {
    title: "动作",
    key: "action",
    width: 72,
    render: (row) => actionTag(row.action),
  },
  {
    title: "说明",
    key: "note",
    ellipsis: { tooltip: true },
    render: (row) =>
      row.merge_into ? `${row.note || ""} → ${row.merge_into}` : row.note || "",
  },
];

const relationColumns = [
  {
    title: "选",
    key: "selected",
    width: 48,
    render(row) {
      if (row.action !== "create") return null;
      return h(NCheckbox, {
        checked: row.selected,
        "onUpdate:checked": (v) => {
          row.selected = v;
        },
      });
    },
  },
  { title: "code", key: "code", ellipsis: { tooltip: true } },
  { title: "名称", key: "label", ellipsis: { tooltip: true } },
  {
    title: "domain→range",
    key: "dr",
    ellipsis: { tooltip: true },
    render: (row) =>
      `${(row.domain_types || []).join(",") || "?"} → ${(row.range_types || []).join(",") || "?"}`,
  },
  {
    title: "动作",
    key: "action",
    width: 72,
    render: (row) => actionTag(row.action),
  },
];

const hasSelected = computed(
  () =>
    entityRows.value.some((e) => e.selected && ["create", "merge"].includes(e.action)) ||
    relationRows.value.some((r) => r.selected && r.action === "create")
);

function setResult(data) {
  result.value = data || null;
  entityRows.value = (data?.entity_types || []).map((e) => ({
    ...e,
    selected: e.selected !== false && ["create", "merge"].includes(e.action),
  }));
  relationRows.value = (data?.relation_types || []).map((r) => ({
    ...r,
    selected: r.selected !== false && r.action === "create",
  }));
}

async function ensureDocsLoaded() {
  if (docsLoaded) return;
  await loadDocs("");
}

async function onDocSearch(q) {
  await loadDocs(q || "");
}

async function loadDocs(keyword) {
  loadingDocs.value = true;
  try {
    const res = await fetchDocuments({
      page: 1,
      page_size: 30,
      keyword: keyword || undefined,
      scope: "personal",
    });
    const items = res?.items || res?.data?.items || res || [];
    const list = Array.isArray(items) ? items : [];
    docOptions.value = list.map((d) => ({
      label: d.title || d.id,
      value: d.id,
    }));
    docsLoaded = true;
  } catch (err) {
    if (err?.code === "ROUTE_ABORT") return;
    ui.error("加载文档失败: " + (err.message || ""));
  } finally {
    loadingDocs.value = false;
  }
}

async function handleDiscoverText() {
  if (!form.text.trim()) {
    ui.warning("请输入正文");
    return;
  }
  discovering.value = true;
  try {
    const data = await discoverOntologyFromText({
      title: form.title || "文档抽取",
      text: form.text,
    });
    setResult(data);
    ui.success(
      `发现 ${(data?.entity_types || []).length} 个概念、${(data?.relation_types || []).length} 个关系候选`
    );
  } catch (err) {
    if (err?.code === "ROUTE_ABORT") return;
    ui.error("发现失败: " + (err.message || ""));
  } finally {
    discovering.value = false;
  }
}

async function handleDiscoverDocs() {
  if (!selectedDocIds.value.length) {
    ui.warning("请选择文档");
    return;
  }
  discovering.value = true;
  try {
    const data = await discoverOntologyFromDocuments({
      documentIds: selectedDocIds.value,
    });
    setResult(data);
    ui.success(
      `发现 ${(data?.entity_types || []).length} 个概念、${(data?.relation_types || []).length} 个关系候选`
    );
  } catch (err) {
    if (err?.code === "ROUTE_ABORT") return;
    ui.error("发现失败: " + (err.message || ""));
  } finally {
    discovering.value = false;
  }
}

async function handleApply() {
  if (!hasSelected.value) {
    ui.warning("请至少勾选一项");
    return;
  }
  applying.value = true;
  try {
    const stats = await applyOntologyDiscover({
      entityTypes: entityRows.value.filter(
        (e) => e.selected && ["create", "merge"].includes(e.action)
      ),
      relationTypes: relationRows.value.filter(
        (r) => r.selected && r.action === "create"
      ),
    });
    ui.success(
      `已写入：概念 +${stats?.entity_types_created || 0}` +
        `（合并 ${stats?.entity_types_merged || 0}），` +
        `关系 +${stats?.relation_types_created || 0}`
    );
    emit("applied", stats);
  } catch (err) {
    if (err?.code === "ROUTE_ABORT") return;
    ui.error("写入失败: " + (err.message || ""));
  } finally {
    applying.value = false;
  }
}
</script>
