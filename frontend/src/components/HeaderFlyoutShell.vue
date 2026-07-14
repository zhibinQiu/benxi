<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

const show = defineModel("show", { type: Boolean, default: false });

const props = defineProps({
  width: { type: String, default: "min(420px, calc(100vw - 32px))" },
  ariaLabel: { type: String, default: "" },
  anchorEl: { type: Object, default: null }});

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
    : { left: "50%", transform: "translateX(-50%)" }),
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
      updatePosition();
      await nextTick();
      updatePosition();
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
  border: 1px solid var(--platform-glass-border);
  box-shadow: var(--platform-shadow-lg);
}

.header-flyout > :deep(*) {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
</style>
