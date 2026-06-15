import { ref } from "vue";
import { fetchDocumentLibrary } from "../api/documents.js";
import { applyUploadLimitsFromLibrary } from "../constants/documentUpload.js";
import {
  readDocumentsLibraryCache,
  writeDocumentsLibraryCache,
} from "../utils/documentsViewCache.js";

const library = ref(null);
const loading = ref(false);
const loaded = ref(false);
let loadPromise = null;

function applyLibrarySideEffects(lib) {
  if (lib) applyUploadLimitsFromLibrary(lib);
}

export function useDocumentLibrary() {
  async function loadDocumentLibrary({ force = false, background = false } = {}) {
    if (loaded.value && library.value && !force) return library.value;
    if (loadPromise && !force) return loadPromise;

    if (!force) {
      const cached = readDocumentsLibraryCache();
      if (cached) {
        library.value = cached;
        applyLibrarySideEffects(cached);
        loaded.value = true;
        void loadDocumentLibrary({ force: true, background: true }).catch(() => {});
        return cached;
      }
    }

    if (!background) {
      loading.value = true;
    }
    loadPromise = (async () => {
      try {
        const lib = await fetchDocumentLibrary();
        library.value = lib;
        writeDocumentsLibraryCache(lib);
        applyLibrarySideEffects(lib);
        loaded.value = true;
        return lib;
      } catch (e) {
        if (!background) {
          loaded.value = false;
        }
        throw e;
      } finally {
        loading.value = false;
        loadPromise = null;
      }
    })();
    return loadPromise;
  }

  /** 详情页等场景：优先缓存，确保上传限制等侧效应已应用 */
  async function ensureUploadLimits() {
    const cached = readDocumentsLibraryCache();
    if (cached) {
      library.value = cached;
      applyLibrarySideEffects(cached);
      loaded.value = true;
      return cached;
    }
    try {
      return await loadDocumentLibrary();
    } catch {
      return null;
    }
  }

  function invalidateDocumentLibrary() {
    library.value = null;
    loaded.value = false;
    loadPromise = null;
  }

  return {
    library,
    loading,
    loaded,
    loadDocumentLibrary,
    ensureUploadLimits,
    invalidateDocumentLibrary,
  };
}
