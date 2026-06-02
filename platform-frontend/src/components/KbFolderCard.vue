<script setup>
import { computed } from "vue";
import { NButton, NDropdown, NIcon } from "naive-ui";
import { EllipsisHorizontal } from "@vicons/ionicons5";

const props = defineProps({
  folder: { type: Object, required: true },
  cardKey: { type: String, default: "folder" },
  menuOptions: { type: Array, default: () => [] },
});

const emit = defineEmits(["open", "menu-select"]);

const variant = computed(() => {
  const f = props.folder;
  if (f.kind === "shared") return "shared";
  if (f.kind === "uncategorized") return "muted";
  if (f.is_system) return "system";
  return "default";
});

const uid = computed(() =>
  String(props.cardKey).replace(/[^a-zA-Z0-9_-]/g, "_")
);

const countLabel = computed(() => `${props.folder.document_count ?? 0} 项`);
</script>

<template>
  <article
    class="kb-folder-card"
    :class="`kb-folder-card--${variant}`"
    role="button"
    tabindex="0"
    @click="emit('open', folder)"
    @keydown.enter="emit('open', folder)"
    @dblclick="emit('open', folder)"
  >
    <span v-if="folder.is_system" class="kb-folder-card__badge">内置</span>

    <div v-if="menuOptions.length" class="kb-folder-card__menu" @click.stop>
      <n-dropdown
        trigger="click"
        :options="menuOptions"
        @select="(key) => emit('menu-select', key, folder)"
      >
        <n-button quaternary circle size="tiny" title="更多操作">
          <template #icon>
            <n-icon :component="EllipsisHorizontal" />
          </template>
        </n-button>
      </n-dropdown>
    </div>

    <div class="kb-folder-card__body">
      <svg
        class="kb-folder-card__art"
        viewBox="0 0 200 148"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        <defs>
          <linearGradient
            :id="`kb-f-back-${uid}`"
            x1="36"
            y1="40"
            x2="172"
            y2="128"
            gradientUnits="userSpaceOnUse"
          >
            <stop offset="0%" class="kb-folder-stop-a" />
            <stop offset="100%" class="kb-folder-stop-b" />
          </linearGradient>
          <linearGradient
            :id="`kb-f-front-${uid}`"
            x1="16"
            y1="48"
            x2="184"
            y2="138"
            gradientUnits="userSpaceOnUse"
          >
            <stop offset="0%" class="kb-folder-stop-c" />
            <stop offset="55%" class="kb-folder-stop-d" />
            <stop offset="100%" class="kb-folder-stop-e" />
          </linearGradient>
        </defs>
        <path
          d="M30 46h42l11 13h71c5.5 0 10 4.5 10 10v54c0 5.5-4.5 10-10 10H38c-5.5 0-10-4.5-10-10V56c0-5.5 4.5-10 10-10z"
          :fill="`url(#kb-f-back-${uid})`"
          opacity="0.42"
        />
        <path
          d="M18 54h50l15 17h81c8.3 0 15 6.7 15 15v50c0 8.3-6.7 15-15 15H33c-8.3 0-15-6.7-15-15V69c0-8.3 6.7-15 15-15z"
          :fill="`url(#kb-f-front-${uid})`"
        />
        <path
          d="M18 54h50l15 17h24v-11L67 54H30c-5 0-9 4-9 9v0z"
          fill="rgba(255,255,255,0.22)"
        />
      </svg>

      <h3 class="kb-folder-card__title" :title="folder.name">
        {{ folder.name }}
      </h3>
      <p class="kb-folder-card__meta">{{ countLabel }}</p>
    </div>
  </article>
</template>

<style scoped>
.kb-folder-card {
  --accent: #0d9488;
  --accent-border: rgba(13, 148, 136, 0.2);
  --stop-a: #52c9bc;
  --stop-b: #3db5a8;
  --stop-c: #6adccf;
  --stop-d: #5ad0c4;
  --stop-e: #42b0a4;

  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100%;
  padding: 10px 8px 12px;
  border-radius: 10px;
  background: transparent;
  border: none;
  box-shadow: none;
  cursor: pointer;
  outline: none;
  user-select: none;
  transition: background 0.15s ease;
}

.kb-folder-card:hover,
.kb-folder-card:focus-visible {
  background: rgba(13, 148, 136, 0.06);
}

.kb-folder-card:focus-visible {
  box-shadow: 0 0 0 2px rgba(153, 246, 228, 0.9);
}

.kb-folder-card--shared {
  --accent: #0891b2;
  --accent-border: rgba(8, 145, 178, 0.2);
  --stop-a: #5ec9dc;
  --stop-b: #48adc4;
  --stop-c: #72d4e8;
  --stop-d: #5ec9dc;
  --stop-e: #48adc4;
}

.kb-folder-card--system,
.kb-folder-card--muted {
  --accent: #64748b;
  --accent-border: rgba(100, 116, 139, 0.18);
  --stop-a: #a0adbe;
  --stop-b: #8a98aa;
  --stop-c: #b0bac8;
  --stop-d: #a2aebd;
  --stop-e: #8a98aa;
}

.kb-folder-card__badge {
  position: absolute;
  top: 4px;
  left: 4px;
  z-index: 2;
  font-size: 9px;
  font-weight: 600;
  padding: 2px 5px;
  border-radius: 4px;
  color: var(--accent);
  background: rgba(255, 255, 255, 0.9);
  line-height: 1.2;
}

.kb-folder-card__menu {
  position: absolute;
  top: 2px;
  right: 2px;
  z-index: 2;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.kb-folder-card:hover .kb-folder-card__menu,
.kb-folder-card:focus-within .kb-folder-card__menu {
  opacity: 1;
}

.kb-folder-card__body {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100%;
  text-align: center;
}

.kb-folder-card__art {
  width: 72%;
  max-width: 88px;
  height: auto;
  display: block;
  margin-bottom: 8px;
  filter: drop-shadow(0 2px 5px rgba(13, 148, 136, 0.14));
}

.kb-folder-card__title {
  margin: 0;
  width: 100%;
  max-width: 120px;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.35;
  color: #0f172a;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  word-break: break-word;
}

.kb-folder-card__meta {
  margin: 3px 0 0;
  font-size: 11px;
  font-weight: 500;
  color: var(--accent);
  opacity: 0.85;
}

:deep(.kb-folder-stop-a) {
  stop-color: var(--stop-a);
}
:deep(.kb-folder-stop-b) {
  stop-color: var(--stop-b);
}
:deep(.kb-folder-stop-c) {
  stop-color: var(--stop-c);
}
:deep(.kb-folder-stop-d) {
  stop-color: var(--stop-d);
}
:deep(.kb-folder-stop-e) {
  stop-color: var(--stop-e);
}
</style>
