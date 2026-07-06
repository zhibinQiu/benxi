import { h } from "vue";
import { NTag } from "naive-ui";

const STATUS_I18N_KEYS = {
  已完成: "knowledgeSearch.index.indexed",
  已索引: "knowledgeSearch.index.indexed",
  解析中: "knowledgeSearch.index.parsing",
  未解析: "knowledgeSearch.index.unparsed",
  解析失败: "knowledgeSearch.index.parseFailed",
  索引失效: "knowledgeSearch.index.stale",
  未同步: "knowledgeSearch.index.notSynced",
};

function tr(t, key, fallback, params) {
  if (!t) {
    if (params && fallback.includes("{{")) {
      return fallback.replace(/\{\{(\w+)\}\}/g, (_, name) =>
        params[name] != null ? String(params[name]) : ""
      );
    }
    return fallback;
  }
  const out = t(key, params);
  return out === key ? fallback : out;
}

function localizeStatus(status, t) {
  const raw = (status || "").trim();
  if (!raw) return tr(t, "knowledgeSearch.index.pending", "待确认");
  const key = STATUS_I18N_KEYS[raw];
  return key ? tr(t, key, raw) : raw;
}

/** 已索引版本的索引方法展示文案 */
export function versionIndexMethodLabel(row, { t } = {}) {
  if (!isDocumentIndexReady(row)) return null;
  const engine = (row.index_engine || "").trim().toLowerCase();
  if (engine === "pageindex") {
    return tr(t, "documents.detail.indexMethodPageIndex", "PageIndex");
  }
  return tr(t, "documents.detail.indexMethodDefault", "Vector");
}

/** 文档是否已成功索引、可用于知识检索问答 */
export function isDocumentIndexReady(row) {
  if (!row?.knowledge_synced) return false;
  const status = row.parse_status || "";
  return status === "已完成" || status === "已索引";
}

/** 索引状态 → Naive Tag 配置（知识检索场景优先展示「可检索」） */
export function knowledgeIndexTagProps(row, { forSearch = false, t } = {}) {
  const ready = isDocumentIndexReady(row);
  if (forSearch && ready) {
    return {
      type: "success",
      label: tr(t, "knowledgeSearch.index.searchable", "可检索"),
    };
  }
  if (forSearch && !ready) {
    if (!row?.knowledge_synced) {
      return {
        type: "warning",
        label: tr(t, "knowledgeSearch.index.notSearchable", "不可检索"),
        hint: tr(t, "knowledgeSearch.index.notIndexed", "未索引"),
      };
    }
    const status = localizeStatus(row.parse_status, t);
    return {
      type: "error",
      label: tr(t, "knowledgeSearch.index.notSearchable", "不可检索"),
      hint: status,
    };
  }
  if (!row?.knowledge_synced) {
    return {
      type: "warning",
      label: tr(t, "knowledgeSearch.index.notIndexed", "未索引"),
    };
  }
  const status = localizeStatus(row.parse_status, t);
  if (!row.parse_status) {
    return { type: "default", label: tr(t, "knowledgeSearch.index.pending", "待确认") };
  }
  if (row.parse_status === "解析中" || row.parse_status === "未解析") {
    return { type: "info", label: status };
  }
  if (row.parse_status === "已完成" || row.parse_status === "已索引") {
    return {
      type: "success",
      label: tr(t, "knowledgeSearch.index.indexed", "已索引"),
    };
  }
  if (
    row.parse_status === "解析失败" ||
    row.parse_status === "索引失效" ||
    row.parse_status === "未同步"
  ) {
    return { type: "error", label: status };
  }
  return { type: "default", label: status };
}

/** 文件夹/知识库节点：可检索文档占比标签 */
export function knowledgeScopeIndexSummary(node, t) {
  const total = Number(node?.document_count ?? 0);
  const ready = Number(node?.index_ready_count ?? 0);
  if (total <= 0) return null;
  if (ready >= total) {
    return {
      type: "success",
      label: tr(t, "knowledgeSearch.index.scopeAllReady", "{{count}} 可检索", {
        count: ready,
      }),
    };
  }
  if (ready <= 0) {
    return {
      type: "warning",
      label: tr(t, "knowledgeSearch.index.scopeNoneReady", "{{count}} 篇不可检索", {
        count: total,
      }),
    };
  }
  return {
    type: "info",
    label: tr(t, "knowledgeSearch.index.scopePartial", "{{ready}}/{{total}} 可检索", {
      ready,
      total,
    }),
  };
}

export function renderKnowledgeIndexTag(row, t) {
  const tag = knowledgeIndexTagProps(row, { t });
  return h(
    NTag,
    { size: "small", type: tag.type, bordered: false },
    { default: () => tag.label }
  );
}
