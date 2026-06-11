import { h } from "vue";
import { NTag } from "naive-ui";

/** 文档是否已成功索引、可用于知识检索问答 */
export function isDocumentIndexReady(row) {
  if (!row?.knowledge_synced) return false;
  const status = row.parse_status || "";
  return status === "已完成" || status === "已索引";
}

/** 索引状态 → Naive Tag 配置（知识检索场景优先展示「可检索」） */
export function knowledgeIndexTagProps(row, { forSearch = false } = {}) {
  const ready = isDocumentIndexReady(row);
  if (forSearch && ready) {
    return { type: "success", label: "可检索" };
  }
  if (forSearch && !ready) {
    if (!row?.knowledge_synced) {
      return { type: "warning", label: "不可检索", hint: "未索引" };
    }
    const status = row.parse_status || "待确认";
    return { type: "error", label: "不可检索", hint: status };
  }
  if (!row?.knowledge_synced) {
    return { type: "warning", label: "未索引" };
  }
  const status = row.parse_status;
  if (!status) {
    return { type: "default", label: "待确认" };
  }
  if (status === "解析中" || status === "未解析") {
    return { type: "info", label: status };
  }
  if (status === "已完成" || status === "已索引") {
    return { type: "success", label: "已索引" };
  }
  if (status === "解析失败" || status === "索引失效" || status === "未同步") {
    return { type: "error", label: status };
  }
  return { type: "default", label: status };
}

/** 文件夹/知识库节点：可检索文档占比标签 */
export function knowledgeScopeIndexSummary(node) {
  const total = Number(node?.document_count ?? 0);
  const ready = Number(node?.index_ready_count ?? 0);
  if (total <= 0) return null;
  if (ready >= total) return { type: "success", label: `${ready} 可检索` };
  if (ready <= 0) return { type: "warning", label: `${total} 篇不可检索` };
  return { type: "info", label: `${ready}/${total} 可检索` };
}

export function renderKnowledgeIndexTag(row) {
  const tag = knowledgeIndexTagProps(row);
  return h(
    NTag,
    { size: "small", type: tag.type, bordered: false },
    { default: () => tag.label }
  );
}
