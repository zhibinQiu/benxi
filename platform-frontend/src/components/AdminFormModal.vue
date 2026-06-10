<script setup>
import { NModal } from "naive-ui";

defineProps({
  show: { type: Boolean, default: false },
  title: { type: String, required: true },
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
    class="admin-form-modal"
    :style="{ width: typeof width === 'number' ? `${width}px` : width }"
    :mask-closable="false"
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
