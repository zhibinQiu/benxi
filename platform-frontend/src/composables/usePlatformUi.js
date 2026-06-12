import { useMessage, useDialog } from "naive-ui";
import { useI18n } from "./useI18n";
import {
  isAuthSilentError,
  shouldSuppressAuthFeedback,
} from "../utils/authError.js";
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
    if (isAuthSilentError(keyOrText)) return;
    const text =
      typeof keyOrText === "object" && keyOrText?.message
        ? sanitizeUserFacingMessage(keyOrText.message, t("messages.operationFailed"))
        : resolveText(keyOrText, params);
    if (shouldSuppressAuthFeedback(text)) return;
    notifyDeduped(message, "error", text, t("messages.operationFailed"));
  }

  function warning(keyOrText, params) {
    toast("warning", keyOrText, params);
  }

  function info(keyOrText, params) {
    toast("info", keyOrText, params);
  }

  function confirmDialog(type, options) {
    const {
      title = t("common.confirm"),
      content,
      onPositive,
      positiveText = t("common.confirm"),
      negativeText = t("common.cancel"),
    } = options;
    dialog[type]({
      class: "platform-confirm-dialog",
      title,
      content: resolveText(content),
      positiveText,
      negativeText,
      onPositiveClick: async () => {
        try {
          await onPositive?.();
          return true;
        } catch (e) {
          error(e);
          return false;
        }
      },
    });
  }

  function confirmDelete(options) {
    confirmDialog("warning", {
      title: options.title ?? t("common.delete"),
      content: options.content,
      onPositive: options.onPositive,
      positiveText: options.positiveText ?? t("common.delete"),
      negativeText: options.negativeText ?? t("common.cancel"),
    });
  }

  function confirmAction(options) {
    confirmDialog("info", {
      title: options.title ?? t("common.confirm"),
      content: options.content,
      onPositive: options.onPositive,
      positiveText: options.positiveText ?? t("common.confirm"),
      negativeText: options.negativeText ?? t("common.cancel"),
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
