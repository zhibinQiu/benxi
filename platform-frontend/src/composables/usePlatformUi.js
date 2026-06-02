import { useMessage, useDialog } from "naive-ui";
import { useI18n } from "./useI18n";
import { notifyDeduped, sanitizeUserFacingMessage } from "../utils/uiMessage";

/** 统一 toast / 确认框：去重、友好错误、i18n */
export function usePlatformUi() {
  const message = useMessage();
  const dialog = useDialog();
  const { t } = useI18n();

  function resolveText(keyOrText, params) {
    if (keyOrText == null) return "";
    const raw = String(keyOrText);
    if (raw.includes(" ") || raw.includes("？") || raw.includes("?")) return raw;
    const translated = t(raw, params);
    return translated === raw && !raw.includes(".") ? raw : translated;
  }

  function toast(type, keyOrText, params) {
    const text = resolveText(keyOrText, params);
    const fallback =
      type === "error"
        ? t("messages.operationFailed")
        : type === "warning"
          ? t("messages.pleaseNote")
          : t("messages.operationSuccess");
    notifyDeduped(message, type, text, fallback);
  }

  function success(keyOrText, params) {
    toast("success", keyOrText, params);
  }

  function error(keyOrText, params) {
    const text =
      typeof keyOrText === "object" && keyOrText?.message
        ? sanitizeUserFacingMessage(keyOrText.message, t("messages.operationFailed"))
        : resolveText(keyOrText, params);
    notifyDeduped(message, "error", text, t("messages.operationFailed"));
  }

  function warning(keyOrText, params) {
    toast("warning", keyOrText, params);
  }

  function info(keyOrText, params) {
    toast("info", keyOrText, params);
  }

  function confirmDelete(options) {
    const {
      title = t("common.delete"),
      content,
      onPositive,
      positiveText = t("common.delete"),
      negativeText = t("common.cancel"),
    } = options;
    dialog.warning({
      title,
      content: resolveText(content),
      positiveText,
      negativeText,
      onPositiveClick: async () => {
        try {
          await onPositive?.();
        } catch (e) {
          error(e);
        }
      },
    });
  }

  function confirmAction(options) {
    const {
      title = t("common.confirm"),
      content,
      onPositive,
      positiveText = t("common.confirm"),
      negativeText = t("common.cancel"),
    } = options;
    dialog.info({
      title,
      content: resolveText(content),
      positiveText,
      negativeText,
      onPositiveClick: async () => {
        try {
          await onPositive?.();
        } catch (e) {
          error(e);
        }
      },
    });
  }

  return {
    t,
    success,
    error,
    warning,
    info,
    confirmDelete,
    confirmAction,
    resolveText,
  };
}
