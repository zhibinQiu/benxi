import { h } from "vue";
import { NButton, NIcon, NTooltip } from "naive-ui";

function tableIconActionClass(type) {
  if (type === "primary") return "table-icon-action table-icon-action--accent";
  if (type === "error") return "table-icon-action table-icon-action--danger";
  if (type === "warning") return "table-icon-action table-icon-action--caution";
  return "table-icon-action";
}

/** 表格 / 列表内嵌图标按钮（悬浮显示文案） */
export function renderIconAction({
  label,
  icon,
  onClick,
  type = "default",
  disabled = false,
  loading = false,
}) {
  return h(
    NTooltip,
    { placement: "top" },
    {
      trigger: () =>
        h(
          NButton,
          {
            quaternary: true,
            circle: true,
            size: "small",
            type: "default",
            disabled: disabled || loading,
            class: [
              tableIconActionClass(type),
              loading ? "table-icon-action--loading" : null,
            ],
            "aria-label": label,
            "aria-busy": loading || undefined,
            onClick: (e) => {
              e.stopPropagation();
              if (loading) return;
              onClick?.(e);
            },
          },
          {
            default: () =>
              h(NIcon, {
                size: 16,
                component: icon,
                class: loading ? "table-icon-action__spin" : undefined,
              }),
          }
        ),
      default: () => label,
    }
  );
}

export function renderIconActionGroup(actions) {
  return h(
    "div",
    { class: "table-icon-actions" },
    actions.filter(Boolean).map((action) => renderIconAction(action))
  );
}
