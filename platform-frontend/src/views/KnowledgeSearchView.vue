<script setup>
import { NAlert, NButton } from "naive-ui";
import FeatureSubsystemShell from "../components/FeatureSubsystemShell.vue";
import KnowledgeServiceStartup from "../components/KnowledgeServiceStartup.vue";
import { useKnowflowEmbed } from "../composables/useKnowflowEmbed";

const STARTUP_HINT = "正在加载知识搜索";

const {
  bootstrapping,
  meta,
  embedSession,
  iframeSrc,
  showStartupHint,
  loadMeta,
  onIframeLoad,
} = useKnowflowEmbed({
  knowflowPath: "/search",
  watchRouteName: "knowledge-search",
  iframeElementId: "knowflow-search-embed",
  embedMode: "search",
});
</script>

<template>
  <FeatureSubsystemShell fill :show-intro="false">
    <div class="subsystem-embed-host">
      <n-alert
        v-if="!bootstrapping && !meta.ui_available"
        type="warning"
        title="知识搜索未就绪"
        class="embed-alert"
      >
        <p>KnowFlow 检索服务暂不可用，请确认知识服务已启动。</p>
        <p v-if="meta.ui_hint" style="margin: 8px 0 0">{{ meta.ui_hint }}</p>
        <template #action>
          <n-button size="small" @click="loadMeta">重新检测</n-button>
        </template>
      </n-alert>

      <n-alert
        v-if="!bootstrapping && meta.ui_available && embedSession?.sso && !embedSession.sso.ready"
        type="info"
        title="登录未完成"
        class="embed-alert"
      >
        {{ embedSession.sso.message || "请刷新页面重试。" }}
        <template #action>
          <n-button size="small" @click="loadMeta">重试</n-button>
        </template>
      </n-alert>

      <KnowledgeServiceStartup v-if="showStartupHint" :message="STARTUP_HINT" />

      <iframe
        v-if="iframeSrc"
        id="knowflow-search-embed"
        class="subsystem-embed-frame"
        :class="{ 'subsystem-embed-frame--loading': showStartupHint }"
        :src="iframeSrc"
        title="知识搜索"
        allow="fullscreen; clipboard-read; clipboard-write"
        referrerpolicy="no-referrer-when-downgrade"
        @load="onIframeLoad"
      />
    </div>
  </FeatureSubsystemShell>
</template>

<style scoped>
.embed-alert {
  margin: 16px;
  max-width: 640px;
}
</style>
