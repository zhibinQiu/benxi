<script setup>
/**
 * 平台标准功能弹窗：统一样式 + 正确的 Naive Modal 生命周期。
 * 业务页请使用本组件，不要直接写 n-modal preset="card"。
 */
import { NModal } from "naive-ui";
import { PLATFORM_Z } from "../constants/zIndex.js";
import { useModalLifecycle } from "../composables/useModalLifecycle.js";

const show = defineModel("show", { type: Boolean, default: false });

defineProps({
  title: { type: String, required: true },
  /** 副标题；较长说明请改用表单项旁的 HintTooltip */
  subtitle: { type: String, default: "" },
  width: { type: [Number, String], default: 624 },
});

const emit = defineEmits(["after-enter", "after-leave"]);

const { mounted, onAfterLeave: unmountModal } = useModalLifecycle(show);

function handleAfterLeave() {
  unmountModal();
  emit("after-leave");
}
</script>

<template>
  <n-modal
    v-if="mounted"
    v-model:show="show"
    preset="card"
    class="admin-form-modal platform-glass-modal"
    :z-index="PLATFORM_Z.featureModal"
    :style="{ width: typeof width === 'number' ? `${width}px` : width }"
    :mask-closable="false"
    transform-origin="center"
    @after-enter="emit('after-enter')"
    @after-leave="handleAfterLeave"
  >
    <template #header>
      <div class="admin-form-modal__head">
        <h3 class="admin-form-modal__title">{{ title }}</h3>
        <p v-if="subtitle" class="admin-form-modal__subtitle">{{ subtitle }}</p>
      </div>
    </template>

    <div class="admin-form-modal__body">
      <slot />
    </div>

    <template v-if="$slots.footer" #footer>
      <div class="admin-form-modal__footer">
        <slot name="footer" />
      </div>
    </template>
  </n-modal>
</template>
