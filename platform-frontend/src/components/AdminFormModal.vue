<script setup>
/**
 * 统一管理/表单弹窗：白底实板、轻盈遮罩、弹簧入场动效。
 * 所有管理类弹窗应优先使用本组件，避免原生 n-modal 样式不一致。
 */
import { NModal } from "naive-ui";

defineProps({
  show: { type: Boolean, default: false },
  title: { type: String, required: true },
  /** 副标题；较长说明请改用表单项旁的 HintTooltip */
  subtitle: { type: String, default: "" },
  width: { type: [Number, String], default: 520 },
});

const emit = defineEmits(["update:show", "after-leave"]);

function onUpdateShow(value) {
  emit("update:show", value);
}
</script>

<template>
  <n-modal
    :show="show"
    preset="card"
    class="admin-form-modal platform-glass-modal"
    :style="{ width: typeof width === 'number' ? `${width}px` : width }"
    :mask-closable="false"
    transform-origin="center"
    @update:show="onUpdateShow"
    @after-leave="emit('after-leave')"
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
