<script setup>
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { NCard, NGrid, NGi, NText, NTag, NIcon, useMessage } from "naive-ui";
import {
  LanguageOutline,
  ChatbubblesOutline,
  GitCompareOutline,
  DocumentTextOutline,
} from "@vicons/ionicons5";
import { fetchSystemFeatures } from "../api/client";

const router = useRouter();
const message = useMessage();
const features = ref([]);
const loading = ref(true);

const iconMap = {
  language: LanguageOutline,
  chatbubbles: ChatbubblesOutline,
  "git-compare": GitCompareOutline,
  "document-text": DocumentTextOutline,
};

onMounted(async () => {
  try {
    features.value = await fetchSystemFeatures();
  } catch (e) {
    message.error(e.message);
  } finally {
    loading.value = false;
  }
});

function openFeature(f) {
  if (!f.enabled) {
    message.info("该功能即将推出");
    return;
  }
  if (!f.accessible || !f.route) {
    message.warning("暂无权限，请联系管理员在角色管理中开通");
    return;
  }
  router.push(f.route);
}
</script>

<template>
  <div class="functions-page">
    <n-text depth="2" class="page-hint">
      选择功能进入；长任务提交后可离开，在任务中心或消息中查看结果
    </n-text>

    <n-grid
      v-if="!loading"
      :cols="4"
      :x-gap="12"
      :y-gap="12"
      responsive="screen"
      item-responsive
      style="margin-top: 12px"
    >
      <n-gi v-for="f in features" :key="f.id" span="4 m:2 l:1">
        <n-card
          size="small"
          class="feature-card"
          :class="{ disabled: !f.enabled, locked: f.enabled && !f.accessible }"
          hoverable
          @click="openFeature(f)"
        >
          <div class="feature-row">
            <n-icon :size="22" class="feature-icon">
              <component :is="iconMap[f.icon] || DocumentTextOutline" />
            </n-icon>
            <div class="feature-body">
              <n-text strong class="feature-title">{{ f.title }}</n-text>
              <n-text depth="3" class="feature-desc">{{ f.description }}</n-text>
            </div>
          </div>
          <n-tag
            size="small"
            :bordered="false"
            :type="f.enabled && f.accessible ? 'success' : f.enabled ? 'warning' : 'default'"
            class="feature-tag"
          >
            {{ f.tag }}
          </n-tag>
        </n-card>
      </n-gi>
    </n-grid>
  </div>
</template>

<style scoped>
.functions-page {
  max-width: 960px;
}
.page-hint {
  display: block;
  font-size: 13px;
}
.feature-card {
  cursor: pointer;
}
.feature-card.disabled,
.feature-card.locked {
  cursor: not-allowed;
  opacity: 0.6;
}
.feature-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}
.feature-icon {
  flex-shrink: 0;
  margin-top: 2px;
  color: var(--n-text-color);
}
.feature-body {
  min-width: 0;
  flex: 1;
}
.feature-title {
  display: block;
  font-size: 14px;
  line-height: 1.35;
}
.feature-desc {
  font-size: 12px;
  line-height: 1.4;
  margin-top: 4px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.feature-tag {
  margin-top: 8px;
}
</style>
