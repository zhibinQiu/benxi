<script setup>
import { computed } from "vue";
import { NCheckbox } from "naive-ui";
import DocumentFileIcon from "./DocumentFileIcon.vue";
import { knowledgeIndexTagProps } from "../utils/knowledgeIndex.js";

const props = defineProps({
  document: { type: Object, required: true },
  selectable: { type: Boolean, default: false },
  selected: { type: Boolean, default: false },
  selectDisabled: { type: Boolean, default: false },
});

const emit = defineEmits(["open", "update:selected"]);

const formatCode = computed(() => props.document.file_format || "");
const uploadedAtLabel = computed(() => {
  const ts = props.document.uploaded_at || props.document.created_at;
  return ts ? new Date(ts).toLocaleString() : "";
});
const indexTag = computed(() => knowledgeIndexTagProps(props.document));
</script>

<template>
  <article
    class="doc-icon-card"
    :class="{ 'doc-icon-card--selected': selected }"
    role="button"
    tabindex="0"
    @click="emit('open', document)"
    @keydown.enter="emit('open', document)"
  >
    <div
      v-if="selectable"
      class="doc-icon-card__check"
      @click.stop
    >
      <n-checkbox
        :checked="selected"
        :disabled="selectDisabled"
        @update:checked="(v) => emit('update:selected', v)"
      />
    </div>

    <div class="doc-icon-card__body">
      <div class="doc-icon-card__art-wrap">
        <div class="doc-icon-card__icon-box">
          <DocumentFileIcon :format="formatCode" :size="38" />
          <span
            class="doc-index-badge"
            :class="`doc-index-badge--${indexTag.type}`"
            :title="indexTag.label"
          >
            {{ indexTag.label }}
          </span>
        </div>
      </div>
      <div class="doc-icon-card__caption">
        <h3 class="doc-icon-card__title" :title="document.title">
          {{ document.title || "—" }}
        </h3>
        <div v-if="uploadedAtLabel" class="doc-icon-card__meta">
          <span class="doc-icon-card__time">{{ uploadedAtLabel }}</span>
        </div>
      </div>
    </div>
  </article>
</template>

<style scoped>
.doc-icon-card {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100%;
  padding: 8px 6px 10px;
  border-radius: var(--platform-card-radius);
  background: transparent;
  border: 1px solid transparent;
  cursor: pointer;
  outline: none;
  user-select: none;
  transition:
    background 0.2s ease,
    border-color 0.2s ease,
    box-shadow 0.2s ease,
    transform 0.2s cubic-bezier(0.34, 1.2, 0.64, 1);
}

.doc-icon-card:hover,
.doc-icon-card:focus-visible {
  background: var(--platform-accent-soft);
  border-color: var(--platform-card-hover-border-color);
  box-shadow: var(--platform-shadow-sm);
  transform: var(--platform-card-hover-transform);
}

.doc-icon-card--selected {
  background: var(--platform-accent-soft);
  border-color: color-mix(in srgb, var(--platform-accent) 35%, transparent);
}

.doc-icon-card:focus-visible {
  box-shadow: var(--platform-focus-ring);
}

.doc-icon-card__check {
  position: absolute;
  top: 4px;
  left: 4px;
  z-index: 2;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.doc-icon-card:hover .doc-icon-card__check,
.doc-icon-card:focus-within .doc-icon-card__check,
.doc-icon-card--selected .doc-icon-card__check {
  opacity: 1;
}

.doc-icon-card__body {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100%;
}

.doc-icon-card__art-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-height: 46px;
  transition: transform 0.28s cubic-bezier(0.34, 1.25, 0.64, 1);
}

.doc-icon-card:hover .doc-icon-card__art-wrap,
.doc-icon-card:focus-visible .doc-icon-card__art-wrap {
  transform: translateY(-3px) scale(1.03);
}

.doc-icon-card__icon-box {
  position: relative;
  display: inline-flex;
  line-height: 0;
  /* 角标在图标右侧外侧 */
  margin-right: 44px;
}

.doc-icon-card__caption {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100%;
  margin-top: 6px;
  padding: 0 4px;
  text-align: center;
}

.doc-icon-card__title {
  margin: 0;
  width: 100%;
  font-size: var(--platform-font-size-sm, 12px);
  font-weight: 500;
  line-height: 1.35;
  color: var(--platform-text, #0f172a);
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  word-break: break-word;
}

.doc-icon-card:hover .doc-icon-card__title,
.doc-icon-card:focus-visible .doc-icon-card__title {
  color: var(--platform-accent);
}

.doc-icon-card__meta {
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 4px;
  width: 100%;
}

.doc-icon-card__time {
  font-size: 10px;
  color: var(--platform-text-quaternary, #999);
  line-height: 1.2;
}

.doc-icon-card .doc-index-badge {
  position: absolute;
  top: -3px;
  left: calc(100% + 2px);
  right: auto;
  z-index: 1;
}

@media (prefers-reduced-motion: reduce) {
  .doc-icon-card,
  .doc-icon-card__art-wrap {
    transition: none;
  }

  .doc-icon-card:hover,
  .doc-icon-card:focus-visible {
    transform: none;
  }

  .doc-icon-card:hover .doc-icon-card__art-wrap,
  .doc-icon-card:focus-visible .doc-icon-card__art-wrap {
    transform: none;
  }
}
</style>
