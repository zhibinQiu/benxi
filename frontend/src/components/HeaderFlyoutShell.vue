<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

const show = defineModel("show", { type: Boolean, default: false });

const props = defineProps({
  width: { type: String, default: "min(420px, calc(100vw - 32px))" },
  ariaLabel: { type: String, default: "" },
  anchorEl: { type: Object, default: null },
  placement: { type: String, default: "bottom" },
  drawer: { type: Boolean, default: false }});

const panelRef = ref(null);
const position = ref({ top: "70px", right: "19px" });
/** 等宿主布局稳定后再 Teleport，避免与路由 Transition 同时 patch 导致 parentNode 为 null */
const teleportReady = ref(false);
const isMobile = ref(window.innerWidth < 768);

function resolveAnchorNode() {
  const raw = props.anchorEl;
  if (!raw) return null;
  if (raw instanceof HTMLElement) return raw;
  if (raw.$el instanceof HTMLElement) return raw.$el;
  if (raw.value instanceof HTMLElement) return raw.value;
  if (raw.value?.$el instanceof HTMLElement) return raw.value.$el;
  return null;
}

function updatePosition() {
  const anchor = resolveAnchorNode();
  if (!anchor) {
    position.value = { top: "70px", right: "19px" };
    return;
  }
  const rect = anchor.getBoundingClientRect();
  if (isMobile.value) {
    position.value = {
      top: `${Math.max(56, rect.bottom + 8)}px`,
      left: "50%",
      right: "auto",
    };
  } else if (props.placement === "top-start") {
    position.value = {
      top: `${Math.max(8, rect.top - 8)}px`,
      left: `${rect.right + 8}px`,
      right: "auto",
    };
  } else {
    position.value = {
      top: `${Math.max(56, rect.bottom + 8)}px`,
      right: `${Math.max(12, window.innerWidth - rect.right)}px`,
    };
  }
}

const panelStyle = computed(() => ({
  width: props.width,
  top: position.value.top,
  ...(position.value.right !== undefined
    ? { right: position.value.right }
    : position.value.left !== undefined
      ? { left: position.value.left }
      : { left: "50%", transform: "translateX(-50%)" }),
}));

const drawerStyle = computed(() => ({
  width: props.width,
  height: "100vh",
  maxHeight: "100vh",
}));

function onViewportResize() {
  isMobile.value = window.innerWidth < 768;
  if (show.value) updatePosition();
}

function onKeydown(event) {
  if (show.value && event.key === "Escape") {
    show.value = false;
  }
}

const OUTSIDE_CLOSE_IGNORE_SELECTOR =
  ".n-dialog, .n-modal, .n-popover, .n-dropdown, .n-tooltip, .platform-confirm-dialog";

function onOutsidePointerDown(event) {
  if (props.drawer) return;
  if (!show.value) return;
  const target = event.target;
  if (!(target instanceof Node)) return;
  if (panelRef.value?.contains(target)) return;
  if (resolveAnchorNode()?.contains(target)) return;
  if (target instanceof Element && target.closest(OUTSIDE_CLOSE_IGNORE_SELECTOR)) return;
  show.value = false;
}

watch(
  show,
  async (visible) => {
    if (visible) {
      if (!props.drawer) {
        updatePosition();
        await nextTick();
        updatePosition();
      }
      document.addEventListener("keydown", onKeydown);
      document.addEventListener("pointerdown", onOutsidePointerDown, true);
    } else {
      document.removeEventListener("keydown", onKeydown);
      document.removeEventListener("pointerdown", onOutsidePointerDown, true);
    }
  },
  { immediate: true },
);

watch(
  () => props.anchorEl,
  () => {
    if (show.value) updatePosition();
  },
);

function onViewportChange() {
  if (show.value) updatePosition();
}

onMounted(() => {
  requestAnimationFrame(() => {
    teleportReady.value = true;
  });
  window.addEventListener("resize", onViewportChange, { passive: true });
  window.addEventListener("resize", onViewportResize, { passive: true });
});

onBeforeUnmount(() => {
  document.removeEventListener("keydown", onKeydown);
  document.removeEventListener("pointerdown", onOutsidePointerDown, true);
  window.removeEventListener("resize", onViewportChange);
  window.removeEventListener("resize", onViewportResize);
});
</script>

<template>
  <Teleport v-if="teleportReady" to="body">
    <template v-if="drawer">
      <Transition name="drawer-backdrop">
        <div v-if="show" class="drawer-backdrop" @click="show = false" />
      </Transition>
      <Transition name="drawer-slide">
        <div
          v-if="show"
          ref="panelRef"
          class="header-flyout header-flyout--drawer"
          :style="drawerStyle"
          role="dialog"
          :aria-label="ariaLabel"
          @click.stop
        >
          <div class="drawer-header">
            <span class="drawer-title">{{ ariaLabel }}</span>
            <button class="drawer-close-btn" @click="show = false" aria-label="关闭">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
          <slot />
        </div>
      </Transition>
    </template>
    <template v-else>
      <div
        v-if="show"
        ref="panelRef"
        class="header-flyout"
        :style="panelStyle"
        role="dialog"
        :aria-label="ariaLabel"
        @click.stop
      >
        <slot />
      </div>
    </template>
  </Teleport>
</template>

<style scoped>
.header-flyout {
  position: fixed;
  z-index: var(--platform-z-flyout);
  min-height: 192px;
  min-width: min(336px, calc(100vw - 38px));
  max-height: min(672px, calc(100vh - 86px));
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-radius: var(--platform-radius);
  background: var(--platform-bg-elevated-solid);
  border: 1px solid var(--platform-border);
  box-shadow: var(--platform-shadow-lg);
}

.header-flyout > :deep(*) {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

/* ====== Drawer 模式 ====== */

.drawer-backdrop {
  position: fixed;
  inset: 0;
  z-index: 10590;
  background: rgba(0, 0, 0, 0.25);
}

.header-flyout--drawer {
  position: fixed;
  right: 0 !important;
  left: auto !important;
  top: 0 !important;
  height: 100vh;
  max-height: 100vh;
  border-radius: 0;
  z-index: 10600;
  border-right: none;
  border-top: none;
  border-bottom: none;
}

.drawer-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px 12px;
  border-bottom: 1px solid var(--platform-border);
  background: var(--platform-bg-elevated-solid);
}

.drawer-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--platform-text);
}

.drawer-close-btn {
  all: unset;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: var(--platform-radius-sm, 6px);
  cursor: pointer;
  color: var(--platform-text-secondary);
  transition: background 0.2s ease, color 0.2s ease;
}

.drawer-close-btn:hover {
  background: var(--platform-bg-tertiary);
  color: var(--platform-text);
}

.header-flyout--drawer > :deep(*) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

/* 滑入/滑出动画 */
.drawer-slide-enter-active {
  transition: transform 0.28s cubic-bezier(0.22, 0.85, 0.32, 1);
}

.drawer-slide-leave-active {
  transition: transform 0.22s cubic-bezier(0.22, 0.85, 0.32, 1);
}

.drawer-slide-enter-from,
.drawer-slide-leave-to {
  transform: translateX(100%);
}

.drawer-backdrop-enter-active {
  transition: opacity 0.28s ease;
}

.drawer-backdrop-leave-active {
  transition: opacity 0.22s ease;
}

.drawer-backdrop-enter-from,
.drawer-backdrop-leave-to {
  opacity: 0;
}
</style>
