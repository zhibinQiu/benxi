<script setup>
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  NCard,
  NButton,
  NSpace,
  NDescriptions,
  NDescriptionsItem,
  NTag,
  NUpload,
  NTable,
  NModal,
  NForm,
  NFormItem,
  NInput,
  NSelect,
  useMessage,
  useDialog,
} from "naive-ui";
import {
  fetchDocument,
  prepareUpload,
  completeUpload,
  getDownloadUrl,
  deleteDocument,
  fetchDocumentPermissions,
  grantPermission,
  revokePermission,
} from "../api/client";

const route = useRoute();
const router = useRouter();
const message = useMessage();
const dialog = useDialog();

const docId = route.params.id;
const doc = ref(null);
const loading = ref(false);
const perms = ref([]);
const showGrant = ref(false);
const grantForm = ref({
  subject_type: "user",
  subject_id: "",
  level: "read",
});

const levelOptions = [
  { label: "查阅", value: "read" },
  { label: "使用", value: "use" },
  { label: "删除", value: "delete" },
];
const subjectTypeOptions = [
  { label: "用户", value: "user" },
  { label: "部门", value: "dept" },
  { label: "角色", value: "role" },
];

async function load() {
  loading.value = true;
  try {
    doc.value = await fetchDocument(docId);
    perms.value = await fetchDocumentPermissions(docId);
  } catch (e) {
    message.error(e.message);
  } finally {
    loading.value = false;
  }
}

async function uploadVersion({ file, onFinish, onError }) {
  const raw = file?.file;
  if (!raw) {
    onError?.();
    return;
  }
  try {
    const prep = await prepareUpload(
      docId,
      raw.name,
      raw.type || "application/octet-stream"
    );
    const putRes = await fetch(prep.upload_url, {
      method: "PUT",
      body: raw,
      headers: { "Content-Type": raw.type || "application/octet-stream" },
    });
    if (!putRes.ok) throw new Error("上传失败");
    await completeUpload(docId, {
      version_id: prep.version_id,
      file_size: raw.size,
    });
    message.success("新版本已上传");
    await load();
    onFinish?.();
  } catch (e) {
    message.error(e.message);
    onError?.();
  }
}

async function download() {
  try {
    const { download_url } = await getDownloadUrl(docId);
    window.open(download_url, "_blank");
  } catch (e) {
    message.error(e.message);
  }
}

function confirmDelete() {
  dialog.warning({
    title: "删除文档",
    content: "将软删除并异步清理存储与权限，确定继续？",
    positiveText: "删除",
    negativeText: "取消",
    onPositiveClick: async () => {
      try {
        const res = await deleteDocument(docId);
        message.success(`已提交删除任务：${res.job_id}`);
        router.push({ name: "documents" });
      } catch (e) {
        message.error(e.message);
      }
    },
  });
}

async function submitGrant() {
  if (!grantForm.value.subject_id.trim()) {
    message.warning("请填写主体 ID（用户/部门/角色的 UUID）");
    return;
  }
  try {
    await grantPermission(docId, {
      subject_type: grantForm.value.subject_type,
      subject_id: grantForm.value.subject_id.trim(),
      level: grantForm.value.level,
    });
    message.success("已授权");
    showGrant.value = false;
    perms.value = await fetchDocumentPermissions(docId);
  } catch (e) {
    message.error(e.message);
  }
}

async function removePerm(permId) {
  try {
    await revokePermission(docId, permId);
    message.success("已移除");
    perms.value = await fetchDocumentPermissions(docId);
  } catch (e) {
    message.error(e.message);
  }
}

onMounted(load);
</script>

<template>
  <n-space vertical :size="16" v-if="doc">
    <n-card :title="doc.title" :loading="loading">
      <template #header-extra>
        <n-space>
          <n-button @click="router.push({ name: 'documents' })">返回</n-button>
          <n-button type="primary" :disabled="!doc.current_version_id" @click="download">
            下载
          </n-button>
          <n-button type="error" tertiary @click="confirmDelete">删除</n-button>
        </n-space>
      </template>
      <n-descriptions :column="2" label-placement="left">
        <n-descriptions-item label="ID">{{ doc.id }}</n-descriptions-item>
        <n-descriptions-item label="状态">
          <n-tag size="small">{{ doc.status }}</n-tag>
        </n-descriptions-item>
        <n-descriptions-item label="说明" :span="2">{{ doc.description || "—" }}</n-descriptions-item>
        <n-descriptions-item label="创建时间">
          {{ new Date(doc.created_at).toLocaleString() }}
        </n-descriptions-item>
        <n-descriptions-item label="更新时间">
          {{ new Date(doc.updated_at).toLocaleString() }}
        </n-descriptions-item>
      </n-descriptions>
    </n-card>

    <n-card title="上传新版本">
      <n-upload :max="1" :custom-request="uploadVersion">
        <n-button>选择文件并上传</n-button>
      </n-upload>
    </n-card>

    <n-card title="版本历史">
      <n-table v-if="doc.versions?.length" :single-line="false">
        <thead>
          <tr>
            <th>版本</th>
            <th>文件名</th>
            <th>大小</th>
            <th>时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="v in doc.versions" :key="v.id">
            <td>v{{ v.version_no }}</td>
            <td>{{ v.file_name }}</td>
            <td>{{ (v.file_size / 1024).toFixed(1) }} KB</td>
            <td>{{ new Date(v.created_at).toLocaleString() }}</td>
          </tr>
        </tbody>
      </n-table>
      <span v-else>暂无文件版本</span>
    </n-card>

    <n-card title="访问授权">
      <template #header-extra>
        <n-button size="small" @click="showGrant = true">添加授权</n-button>
      </template>
      <n-table v-if="perms.length" :single-line="false">
        <thead>
          <tr>
            <th>类型</th>
            <th>主体 ID</th>
            <th>级别</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in perms" :key="p.id">
            <td>{{ p.subject_type }}</td>
            <td style="font-family: monospace; font-size: 12px">{{ p.subject_id }}</td>
            <td>{{ p.level }}</td>
            <td>
              <n-button text type="error" size="small" @click="removePerm(p.id)">移除</n-button>
            </td>
          </tr>
        </tbody>
      </n-table>
      <span v-else>仅所有者可见（可添加部门/用户授权）</span>
    </n-card>
  </n-space>

  <n-modal v-model:show="showGrant" preset="card" title="添加授权" style="width: 440px">
    <n-form>
      <n-form-item label="主体类型">
        <n-select v-model:value="grantForm.subject_type" :options="subjectTypeOptions" />
      </n-form-item>
      <n-form-item label="主体 UUID">
        <n-input v-model:value="grantForm.subject_id" placeholder="用户/部门/角色 ID" />
      </n-form-item>
      <n-form-item label="权限级别">
        <n-select v-model:value="grantForm.level" :options="levelOptions" />
      </n-form-item>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="showGrant = false">取消</n-button>
        <n-button type="primary" @click="submitGrant">确定</n-button>
      </n-space>
    </template>
  </n-modal>
</template>
