import { useMessage } from "naive-ui";
import { isAuthSilentError, shouldSuppressAuthFeedback } from "../utils/authError.js";
import { notifyDeduped } from "../utils/uiMessage";

/** 带去重的 Naive UI message（同一文案 2.2s 内不重复） */
export function useUiMessage() {
  const message = useMessage();
  function error(text) {
    if (isAuthSilentError(text)) return;
    if (shouldSuppressAuthFeedback(text)) return;
    notifyDeduped(message, "error", text);
  }
  return {
    success: (text) => notifyDeduped(message, "success", text),
    error,
    warning: (text) => notifyDeduped(message, "warning", text),
    info: (text) => notifyDeduped(message, "info", text),
  };
}
