<script setup>
import { computed } from "vue";
import { NPagination } from "naive-ui";

const props = defineProps({
  page: { type: Number, required: true },
  pageSize: { type: Number, required: true },
  itemCount: { type: Number, default: 0 },
  pageSlot: { type: Number, default: 7 },
});

const emit = defineEmits(["update:page"]);

const show = computed(() => props.itemCount > props.pageSize);
</script>

<template>
  <footer v-if="show" class="list-table-footer feature-bottom-strip">
    <n-pagination
      :page="page"
      :page-size="pageSize"
      :item-count="itemCount"
      :page-slot="pageSlot"
      @update:page="emit('update:page', $event)"
    />
  </footer>
</template>
