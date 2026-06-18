<script setup>
import TodosPanel from "../components/TodosPanel.vue";
</script>

<template>
  <div class="todos-page feature-page">
    <TodosPanel variant="page" />
  </div>
</template>

<style scoped>
.todos-page {
  max-width: 1100px;
  margin: 0 auto;
}
</style>
