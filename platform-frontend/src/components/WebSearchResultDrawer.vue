<script setup>
import { computed, ref, watch } from "vue";
import { NButton, NDrawer, NDrawerContent, NSpace, NTag, NText } from "naive-ui";
import {
  siteFaviconUrl,
  siteHostFromUrl,
  siteInitialFromHost,
} from "../utils/siteFavicon.js";

const props = defineProps({
  show: { type: Boolean, default: false },
  item: { type: Object, default: null },
  collecting: { type: Boolean, default: false },
});

const emit = defineEmits(["update:show", "collect", "open-original"]);

const siteHost = computed(() => siteHostFromUrl(props.item?.url));

const favicon = computed(() => siteFaviconUrl(props.item?.url || siteHost.value));

const siteInitial = computed(() => siteInitialFromHost(siteHost.value));

const faviconBroken = ref(false);

watch(
  () => props.item?.url,
  () => {
    faviconBroken.value = false;
  }
);

function close() {
  emit("update:show", false);
}
</script>

<template>
  <NDrawer
    :show="show"
    :width="480"
    placement="right"
    @update:show="emit('update:show', $event)"
  >
    <NDrawerContent v-if="item" closable @close="close">
      <template #header>
        <div class="web-detail-head">
          <span v-if="favicon" class="web-detail-head__favicon" aria-hidden="true">
            <img
              v-show="!faviconBroken"
              :src="favicon"
              alt=""
              loading="lazy"
              @error="faviconBroken = true"
            />
            <span v-if="faviconBroken" class="web-detail-head__favicon-fallback">
              {{ siteInitial }}
            </span>
          </span>
          <span class="web-detail-head__site">{{ siteHost || "网页" }}</span>
        </div>
      </template>

      <h2 class="web-detail-title">{{ item.title }}</h2>

      <a
        class="web-detail-url"
        :href="item.url"
        target="_blank"
        rel="noopener noreferrer"
        @click.prevent="emit('open-original')"
      >
        {{ item.url }}
      </a>

      <p class="web-detail-snippet">{{ item.snippet || "暂无摘要" }}</p>

      <NTag v-if="item.engine" size="small" :bordered="false" class="web-detail-engine">
        {{ item.engine }}
      </NTag>

      <template #footer>
        <NSpace justify="end">
          <NButton @click="emit('open-original')">打开原文</NButton>
          <NButton type="primary" :loading="collecting" @click="emit('collect')">
            收藏到本地
          </NButton>
        </NSpace>
      </template>
    </NDrawerContent>
  </NDrawer>
</template>

<style scoped>
.web-detail-head {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.web-detail-head__favicon {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  overflow: hidden;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--platform-bg-muted);
}

.web-detail-head__favicon img {
  width: 16px;
  height: 16px;
}

.web-detail-head__favicon-fallback {
  font-size: 11px;
  font-weight: 600;
  color: var(--platform-text-secondary);
}

.web-detail-head__site {
  font-size: 14px;
  color: var(--platform-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.web-detail-title {
  margin: 0 0 12px;
  font-size: 22px;
  font-weight: 600;
  line-height: 1.35;
  color: var(--platform-text);
}

.web-detail-url {
  display: block;
  margin-bottom: 16px;
  font-size: 13px;
  line-height: 1.45;
  color: var(--platform-accent);
  word-break: break-all;
  text-decoration: none;
}

.web-detail-url:hover {
  text-decoration: underline;
}

.web-detail-snippet {
  margin: 0 0 16px;
  font-size: 15px;
  line-height: 1.65;
  color: var(--platform-text-secondary);
}

.web-detail-engine {
  margin-top: 4px;
}
</style>
