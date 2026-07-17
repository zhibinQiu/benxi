<script setup>
import { computed } from "vue";
import { NButton, NDropdown, NIcon } from "naive-ui";
import { EllipsisHorizontal } from "@vicons/ionicons5";

const props = defineProps({
  folder: { type: Object, required: true },
  cardKey: { type: String, default: "folder" },
  menuOptions: { type: Array, default: () => [] }});

const emit = defineEmits(["open", "menu-select"]);

const variant = computed(() => {
  const f = props.folder;
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
      <div class="kb-folder-card__art-wrap">
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
          <g class="kb-folder-card__layer kb-folder-card__layer--back">
            <path
              d="M30 46h42l11 13h71c5.5 0 10 4.5 10 10v54c0 5.5-4.5 10-10 10H38c-5.5 0-10-4.5-10-10V56c0-5.5 4.5-10 10-10z"
              :fill="`url(#kb-f-back-${uid})`"
              opacity="0.42"
            />
          </g>
          <g class="kb-folder-card__layer kb-folder-card__layer--front">
            <path
              d="M18 54h50l15 17h81c8.3 0 15 6.7 15 15v50c0 8.3-6.7 15-15 15H33c-8.3 0-15-6.7-15-15V69c0-8.3 6.7-15 15-15z"
              :fill="`url(#kb-f-front-${uid})`"
            />
            <path
              d="M18 54h50l15 17h24v-11L67 54H30c-5 0-9 4-9 9v0z"
              fill="rgba(255,255,255,0.22)"
            />
          </g>
        </svg>
      </div>

      <div class="kb-folder-card__caption">
        <h3 class="kb-folder-card__title" :title="folder.name">
          {{ folder.name }}
        </h3>
        <p class="kb-folder-card__meta">{{ countLabel }}</p>
      </div>
    </div>
  </article>
</template>

<style scoped>
.kb-folder-card {
  --accent: var(--platform-accent);
  --accent-border: var(--platform-accent-soft);
  --stop-a: var(--platform-accent-stop-a);
  --stop-b: var(--platform-accent-stop-b);
  --stop-c: var(--platform-accent-stop-c);
  --stop-d: var(--platform-accent-stop-d);
  --stop-e: var(--platform-accent-stop-e);

  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100%;
  padding: 10px 9px 12px;
  border-radius: var(--platform-card-radius);
  background: transparent;
  border: 1px solid transparent;
  box-shadow: none;
  cursor: pointer;
  outline: none;
  user-select: none;
  transition:
    background 0.2s ease,
    border-color 0.2s ease,
    box-shadow 0.2s ease,
    transform 0.2s cubic-bezier(0.34, 1.2, 0.64, 1);
}

.kb-folder-card:hover,
.kb-folder-card:focus-visible {
  background: var(--platform-accent-soft);
  border-color: var(--platform-card-hover-border-color);
  box-shadow: var(--platform-shadow-sm);
  transform: var(--platform-card-hover-transform);
}

.kb-folder-card:focus-visible {
  box-shadow: var(--platform-focus-ring);
}

.kb-folder-card--shared {
  --accent: var(--platform-accent-secondary);
  --accent-border: var(--platform-accent-soft-2);
  --stop-a: var(--platform-accent-stop-c);
  --stop-b: var(--platform-accent-stop-b);
  --stop-c: var(--platform-accent-stop-a);
  --stop-d: var(--platform-accent-stop-d);
  --stop-e: var(--platform-accent-pressed);
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
  top: 2px;
  left: 2px;
  z-index: 2;
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 5px;
  color: var(--accent);
  background: rgba(255, 255, 255, 0.92);
  line-height: 1.2;
  box-shadow: 0 1px 4px rgba(15, 23, 42, 0.08);
}

.kb-folder-card__menu {
  position: absolute;
  top: 0;
  right: 0;
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
}

.kb-folder-card__art-wrap {
  width: var(--kb-folder-icon-width, 84%);
  max-width: var(--kb-folder-icon-max, 125px);
  margin: 0 auto;
  transition: transform 0.32s cubic-bezier(0.34, 1.25, 0.64, 1);
}

.kb-folder-card__art {
  width: 100%;
  height: auto;
  display: block;
  overflow: visible;
  filter: drop-shadow(0 5px 12px color-mix(in srgb, var(--platform-accent) 15%, transparent));
  transition: filter 0.28s cubic-bezier(0.34, 1.2, 0.64, 1);
}

.kb-folder-card__layer {
  transition: transform 0.34s cubic-bezier(0.34, 1.35, 0.64, 1);
  transform-box: fill-box;
}

.kb-folder-card__layer--back {
  transform-origin: 50% 88%;
}

.kb-folder-card__layer--front {
  transform-origin: 8% 46%;
}

.kb-folder-card:hover .kb-folder-card__art-wrap,
.kb-folder-card:focus-visible .kb-folder-card__art-wrap {
  transform: translateY(-4px) scale(1.02);
}

.kb-folder-card:hover .kb-folder-card__layer--back,
.kb-folder-card:focus-visible .kb-folder-card__layer--back {
  transform: scale(1.05) translateY(2%);
}

.kb-folder-card:hover .kb-folder-card__layer--front,
.kb-folder-card:focus-visible .kb-folder-card__layer--front {
  transform: rotate(-16deg) translate(-2%, -4%) scale(1.02);
}

.kb-folder-card:hover .kb-folder-card__art,
.kb-folder-card:focus-visible .kb-folder-card__art {
  filter: drop-shadow(0 12px 26px color-mix(in srgb, var(--platform-accent) 28%, transparent));
}

.kb-folder-card__caption {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  width: 100%;
  max-width: 100%;
  margin-top: 10px;
  padding: 0 5px;
  text-align: center;
}

.kb-folder-card__title {
  margin: 0 auto;
  width: 100%;
  max-width: 100%;
  font-size: var(--platform-font-size-xs);
  font-weight: var(--platform-font-weight-strong);
  line-height: 1.4;
  text-align: center;
  color: var(--platform-text, #0f172a);
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  word-break: break-word;
  transition: color 0.2s ease;
}

.kb-folder-card:hover .kb-folder-card__title,
.kb-folder-card:focus-visible .kb-folder-card__title {
  color: var(--accent);
}

.kb-folder-card__meta {
  margin: 4px 0 0;
  width: 100%;
  font-size: var(--platform-font-size-sm);
  font-weight: var(--platform-font-weight-normal);
  line-height: 1.2;
  text-align: center;
  color: var(--accent);
  opacity: 0.88;
}

@media (prefers-reduced-motion: reduce) {
  .kb-folder-card,
  .kb-folder-card__art-wrap,
  .kb-folder-card__art,
  .kb-folder-card__layer {
    transition: none;
  }

  .kb-folder-card:hover,
  .kb-folder-card:focus-visible {
    transform: none;
  }

  .kb-folder-card:hover .kb-folder-card__art-wrap,
  .kb-folder-card:focus-visible .kb-folder-card__art-wrap,
  .kb-folder-card:hover .kb-folder-card__layer--back,
  .kb-folder-card:focus-visible .kb-folder-card__layer--back,
  .kb-folder-card:hover .kb-folder-card__layer--front,
  .kb-folder-card:focus-visible .kb-folder-card__layer--front {
    transform: none;
  }
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
