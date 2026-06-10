import { h } from "vue";
import { NTag } from "naive-ui";

/** 索引状态 → Naive Tag 配置 */
export function knowledgeIndexTagProps(row) {
  if (!row?.knowledge_synced) {
    return { type: "warning", label: "未索引" };
  }
  const status = row.parse_status || "已索引";
  if (status === "已完成" || status === "已索引") {
    return { type: "success", label: "已索引" };
  }
  if (status === "解析失败" || status === "索引失效" || status === "未同步") {
    return { type: "error", label: status };
  }
  if (status === "解析中" || status === "未解析") {
    return { type: "info", label: status };
  }
  return { type: "default", label: status };
}

export function renderKnowledgeIndexTag(row) {
  const tag = knowledgeIndexTagProps(row);
  return h(
    NTag,
    { size: "small", type: tag.type, bordered: false },
    { default: () => tag.label }
  );
}
