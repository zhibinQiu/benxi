import { useMessage, useDialog } from "naive-ui";
import { useI18n } from "./useI18n";
import {
  isAuthSilentError,
  shouldSuppressAuthFeedback,
} from "../utils/authError.js";
import { notifyDeduped, sanitizeUserFacingMessage } from "../utils/uiMessage";
import { withSystemDialogLayer } from "../utils/systemDialog.js";

/** 统一 toast / 确认框：去重、友好错误、i18n。
 *
 * 实现思路：
 * - 所有页面应用 usePlatformUi，勿直接使用 naive-ui useMessage
 * - error() 经 sanitizeUserFacingMessage 过滤后端技术词，与 app/core/user_messages 对齐
 * - notifyDeduped 防止同一操作连续弹多条相同 toast
 */
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
    dialog[type](
      withSystemDialogLayer({
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
      })
    );
  }

  function confirmDelete(options) {
    const {
      title = t("common.delete"),
      content,
      onPositive,
      positiveText = t("common.delete"),
      negativeText = t("common.cancel"),
      pendingMessage = "messages.deleting",
      blocking = false,
    } = options;
    if (blocking) {
      confirmDialog("warning", {
        title,
        content,
        onPositive,
        positiveText,
        negativeText,
      });
      return;
    }
    dialog.warning(
      withSystemDialogLayer({
        title,
        content: resolveText(content),
        positiveText,
        negativeText,
        onPositiveClick: () => {
          info(pendingMessage);
          void (async () => {
            try {
              await onPositive?.();
            } catch (e) {
              error(e);
            }
          })();
          return true;
        },
      })
    );
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
