<script setup>
import { NIcon } from "naive-ui";
import { AddOutline } from "@vicons/ionicons5";

defineEmits(["create"]);
</script>

<template>
  <button
    type="button"
    class="kb-folder-create-card"
    title="新建文件夹"
    aria-label="新建文件夹"
    @click="$emit('create')"
  >
    <div class="kb-folder-create-card__art" aria-hidden="true">
      <svg viewBox="0 0 200 148" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path
          d="M30 46h42l11 13h71c5.5 0 10 4.5 10 10v54c0 5.5-4.5 10-10 10H38c-5.5 0-10-4.5-10-10V56c0-5.5 4.5-10 10-10z"
          fill="var(--platform-accent-soft)"
        />
        <path
          d="M18 54h50l15 17h81c8.3 0 15 6.7 15 15v50c0 8.3-6.7 15-15 15H33c-8.3 0-15-6.7-15-15V69c0-8.3 6.7-15 15-15z"
          fill="var(--platform-accent-muted)"
          stroke="var(--platform-accent-border)"
          stroke-width="2"
          stroke-dasharray="6 4"
        />
      </svg>
      <span class="kb-folder-create-card__plus">
        <n-icon :size="22" :component="AddOutline" />
      </span>
    </div>
    <span class="kb-folder-create-card__label">新建文件夹</span>
  </button>
</template>
