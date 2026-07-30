import { ref } from "vue";

/**
 * 弹窗式台账 CRUD：新建/编辑模态、保存与删除确认的统一流程。
 */
export function useCarbonCrud({ emptyForm, mapRowToForm, ui }) {
  const form = ref(emptyForm());
  const modalMode = ref("create");
  const showModal = ref(false);

  function openCreate() {
    modalMode.value = "create";
    form.value = emptyForm();
    showModal.value = true;
  }

  function startEdit(row) {
    modalMode.value = "edit";
    form.value = mapRowToForm(row);
    showModal.value = true;
  }

  function closeModal() {
    showModal.value = false;
  }

  function confirmDelete({ title, content, onPositive }) {
    ui.confirmDelete({ title, content, onPositive });
  }

  async function runSave({ saving, saveFn, successMessage, afterSave }) {
    saving.value = true;
    try {
      await saveFn();
      ui.success(successMessage);
      showModal.value = false;
      if (afterSave) await afterSave();
    } catch (e) {
      ui.error(e?.message || "保存失败");
    } finally {
      saving.value = false;
    }
  }

  async function runDelete({ deleteFn, afterDelete }) {
    try {
      await deleteFn();
      ui.success("已删除");
      if (afterDelete) await afterDelete();
    } catch (e) {
      ui.error(e?.message || "删除失败");
    }
  }

  return {
    form,
    modalMode,
    showModal,
    openCreate,
    startEdit,
    closeModal,
    confirmDelete,
    runSave,
    runDelete,
  };
}
