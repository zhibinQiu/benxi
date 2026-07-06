import { onBeforeUnmount, ref, watch } from "vue";
import { bindRichMediaViewer, unbindRichMediaViewer } from "../utils/richMediaInteractions.js";
import {
  resolveStableImageObjectUrl,
  revokeObjectUrlIfBlob,
} from "../utils/authenticatedImage.js";
import { useI18n } from "./useI18n.js";
import { usePlatformUi } from "./usePlatformUi.js";

export function useRichMediaViewer() {
  const { t } = useI18n();
  const ui = usePlatformUi();
  const viewerOpen = ref(false);
  const viewerPayload = ref(null);
  let viewerImageBlobUrl = null;
  let openImageGeneration = 0;

  function revokeViewerImageBlob() {
    revokeObjectUrlIfBlob(viewerImageBlobUrl);
    viewerImageBlobUrl = null;
  }

  watch(viewerOpen, (open) => {
    if (!open) {
      openImageGeneration += 1;
      revokeViewerImageBlob();
    }
  });

  async function openRichMediaViewer(payload) {
    if (payload?.type === "image" && payload.imageUrl) {
      const gen = ++openImageGeneration;
      revokeViewerImageBlob();
      try {
        const stable = await resolveStableImageObjectUrl(payload.imageUrl);
        if (gen !== openImageGeneration) {
          revokeObjectUrlIfBlob(stable);
          return;
        }
        if (stable.startsWith("blob:")) {
          viewerImageBlobUrl = stable;
        }
        payload = { ...payload, imageUrl: stable };
      } catch (e) {
        if (gen === openImageGeneration) {
          ui.error(e.message || t("richMedia.saveFailed"));
        }
        return;
      }
    }
    viewerPayload.value = payload;
    viewerOpen.value = true;
  }

  function bindRichMediaViewerOnRoot(root) {
    if (!root) return;
    bindRichMediaViewer(root, openRichMediaViewer, {
      expandHint: t("richMedia.expandHint"),
    });
  }

  function unbindRichMediaViewerOnRoot(root) {
    unbindRichMediaViewer(root);
  }

  onBeforeUnmount(() => {
    openImageGeneration += 1;
    revokeViewerImageBlob();
  });

  return {
    viewerOpen,
    viewerPayload,
    bindRichMediaViewerOnRoot,
    unbindRichMediaViewerOnRoot,
  };
}
