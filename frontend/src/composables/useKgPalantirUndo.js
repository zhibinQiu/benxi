import { computed, ref } from "vue";

const UNDO_LIMIT = 32;

export function useKgPalantirUndo() {
  const undoStack = ref([]);
  const redoStack = ref([]);
  const busy = ref(false);

  const canUndo = computed(() => undoStack.value.length > 0 && !busy.value);
  const canRedo = computed(() => redoStack.value.length > 0 && !busy.value);

  function pushEntry(entry) {
    undoStack.value.push(entry);
    if (undoStack.value.length > UNDO_LIMIT) {
      undoStack.value.shift();
    }
    redoStack.value = [];
  }

  function clearUndoHistory() {
    undoStack.value = [];
    redoStack.value = [];
  }

  async function runUndo() {
    const entry = undoStack.value.at(-1);
    if (!entry || busy.value) return null;
    busy.value = true;
    try {
      await entry.undo();
      undoStack.value.pop();
      redoStack.value.push(entry);
      return entry;
    } finally {
      busy.value = false;
    }
  }

  async function runRedo() {
    const entry = redoStack.value.at(-1);
    if (!entry || busy.value) return null;
    busy.value = true;
    try {
      await entry.redo();
      redoStack.value.pop();
      undoStack.value.push(entry);
      return entry;
    } finally {
      busy.value = false;
    }
  }

  return {
    canUndo,
    canRedo,
    busy,
    pushEntry,
    clearUndoHistory,
    runUndo,
    runRedo,
  };
}
