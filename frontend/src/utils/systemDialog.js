import { PLATFORM_Z } from "../constants/zIndex.js";

export const SYSTEM_CONFIRM_DIALOG_CLASS = "platform-confirm-dialog";

/** 统一系统确认弹窗样式与层级（须高于功能弹窗） */
export function withSystemDialogLayer(options = {}) {
  const { class: extraClass, zIndex, positiveButtonProps, negativeButtonProps, ...rest } = options;
  const classes = [SYSTEM_CONFIRM_DIALOG_CLASS, extraClass].filter(Boolean);
  return {
    ...rest,
    zIndex: zIndex ?? PLATFORM_Z.systemDialog,
    class: classes.join(" "),
    positiveButtonProps: { type: "primary", ...positiveButtonProps },
    negativeButtonProps: { ...negativeButtonProps },
  };
}
