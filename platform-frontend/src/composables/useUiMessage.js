import { useMessage } from "naive-ui";
import { notifyDeduped } from "../utils/uiMessage";

/** 带去重的 Naive UI message（同一文案 2.2s 内不重复） */
export function useUiMessage() {
  const message = useMessage();
  return {
    success: (text) => notifyDeduped(message, "success", text),
    error: (text) => notifyDeduped(message, "error", text),
    warning: (text) => notifyDeduped(message, "warning", text),
    info: (text) => notifyDeduped(message, "info", text),
  };
}
