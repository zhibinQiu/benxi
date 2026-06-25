import { ref, onUnmounted } from "vue";
import { usePlatformUi } from "./usePlatformUi";
import { fetchParserOptions, reindexDocument } from "../api/knowledge.js";
import { fetchDocument } from "../api/documents.js";
import { fetchJob } from "../api/client.js";
import { subscribePlatformJobEvents } from "../api/jobEvents.js";
import { notifyKnowledgeScopeTreeStale } from "../utils/knowledgeScopeRefresh.js";

const POLL_INTERVAL_MS = 3000;
const MAX_POLL_ATTEMPTS = 120;
const STALE_FAILURE_GRACE_MS = 20000;

function isTerminalSuccess(status) {
  return status === "已完成" || status === "已索引";
}

function isTerminalFailure(status) {
  return (
    status === "解析失败"
    || status === "索引失败"
    || status === "索引失效"
    || status === "已取消"
  );
}

function mapSelectOptions(items = [], { pageindexReady = true } = {}) {
  return items.map((p) => ({
    label: p.label,
    hint: p.hint || "",
    value: p.id,
    disabled: p.id === "pageindex" && !pageindexReady,
  }));
}

export const reindexSelectMenuProps = {
  class: "platform-select-in-modal",
  style: { maxHeight: "280px" },
};
/** 弹窗靠下时默认向下展开会超出视口，统一向上弹出 */
export const reindexSelectPlacement = "top-start";

export function renderIndexedSelectLabel(option) {
  return option?.label ?? "";
}

/** 选项悬浮时用原生 title 展示说明，避免在下拉列表中占行 */
export function reindexSelectNodeProps(option) {
  const hint = option?.hint?.trim?.() ?? String(option?.hint || "").trim();
  if (!hint) return {};
  return { title: hint };
}

/** 文档版本重新索引：切换解析器；默认从存储重新上传以修复引用截图 */
export function useDocumentReindex(documentId, onUpdated) {
  const ui = usePlatformUi();

  const reindexModalShow = ref(false);
  const reindexTargetVersion = ref(null);
  const parserId = ref("");
  const layoutRecognize = ref("PaddleOCR");
  const chunkMethodOptions = ref([]);
  const layoutOptions = ref([]);
  const pageindexBlockReason = ref("");
  const reparsing = ref(false);
  const indexPolling = ref(false);

  let pollTimer = null;
  let closeJobEvents = null;
  let reindexSession = null;

  function notifyUpdated() {
    onUpdated?.();
    notifyKnowledgeScopeTreeStale();
  }

  function stopPoll() {
    if (pollTimer) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
    if (closeJobEvents) {
      closeJobEvents();
      closeJobEvents = null;
    }
  }

  function clearReindexSession() {
    reindexSession = null;
  }

  function beginReindexSession(versionId, baselineStatus = null) {
    reindexSession = {
      versionId,
      startedAt: Date.now(),
      baselineStatus,
      sawParsing: false,
    };
  }

  function finishReindexSession() {
    stopPoll();
    indexPolling.value = false;
    clearReindexSession();
  }

  function isStaleFailureStatus(status) {
    if (!reindexSession || !isTerminalFailure(status)) return false;
    if (reindexSession.sawParsing) return false;
    const elapsed = Date.now() - reindexSession.startedAt;
    if (status === reindexSession.baselineStatus) {
      return elapsed < STALE_FAILURE_GRACE_MS * 6;
    }
    return elapsed < STALE_FAILURE_GRACE_MS;
  }

  async function loadParserOptions() {
    try {
      const data = await fetchParserOptions();
      const methods = data?.chunk_methods || data?.items || [];
      const pageindexReady = data?.pageindex?.available !== false;
      pageindexBlockReason.value = data?.pageindex?.block_reason || "";
      chunkMethodOptions.value = mapSelectOptions(methods, { pageindexReady });
      layoutOptions.value = mapSelectOptions(data?.layout_recognizers || []);
      const defaults = data?.defaults || {};
      if (defaults.parser_id) parserId.value = defaults.parser_id;
      if (defaults.layout_recognize) layoutRecognize.value = defaults.layout_recognize;
      if (!pageindexReady && parserId.value === "pageindex") {
        parserId.value = defaults.parser_id && defaults.parser_id !== "pageindex"
          ? defaults.parser_id
          : "naive";
      }
      if (!parserId.value && chunkMethodOptions.value.length) {
        const first = chunkMethodOptions.value.find((o) => !o.disabled) || chunkMethodOptions.value[0];
        parserId.value = first?.value || "naive";
      }
      if (!layoutRecognize.value && layoutOptions.value.length) {
        layoutRecognize.value = layoutOptions.value[0]?.value || "PaddleOCR";
      }
    } catch {
      chunkMethodOptions.value = [
        { label: "Naive（通用）", hint: "通用文本分块；配 DeepDOC/纯文本", value: "naive" },
        { label: "智能分块", hint: "推荐；配合 PaddleOCR/MinerU 等现代 OCR", value: "smart" },
      ];
      layoutOptions.value = [
        {
          label: "PaddleOCR",
          hint: "版面 OCR（默认；使用资源管理中的 PaddleOCR-VL 服务）",
          value: "PaddleOCR",
        },
        { label: "纯文本", hint: "跳过复杂版面分析，适合已提取文本", value: "Plain Text" },
      ];
      if (!parserId.value) parserId.value = "smart";
    }
  }

  function openReindexModal(version) {
    if (!version?.uploaded || indexPolling.value) return;
    reindexTargetVersion.value = version;
    reindexModalShow.value = true;
    void loadParserOptions();
  }

  async function pollReindexStatus(versionId, attempt = 0) {
    try {
      const doc = await fetchDocument(documentId);
      const version = (doc.versions || []).find((v) => v.id === versionId);
      const status = version?.parse_status || null;

      if (status === "解析中" && reindexSession) {
        reindexSession.sawParsing = true;
      }

      if (isStaleFailureStatus(status)) {
        notifyUpdated();
        if (attempt >= MAX_POLL_ATTEMPTS) {
          finishReindexSession();
          ui.warning("索引仍在进行，请稍后刷新");
          return;
        }
        pollTimer = setTimeout(
          () => pollReindexStatus(versionId, attempt + 1),
          POLL_INTERVAL_MS
        );
        return;
      }

      notifyUpdated();

      if (isTerminalSuccess(status)) {
        finishReindexSession();
        ui.success("索引已完成");
        return;
      }

      if (isTerminalFailure(status)) {
        finishReindexSession();
        return;
      }

      if (attempt >= MAX_POLL_ATTEMPTS) {
        finishReindexSession();
        ui.warning("索引仍在进行，请稍后刷新");
        return;
      }

      pollTimer = setTimeout(
        () => pollReindexStatus(versionId, attempt + 1),
        POLL_INTERVAL_MS
      );
    } catch (e) {
      finishReindexSession();
      ui.error(e?.message || "获取索引状态失败");
    }
  }

  function startReindexPolling(versionId, baselineStatus = null) {
    stopPoll();
    beginReindexSession(versionId, baselineStatus);
    indexPolling.value = true;
    pollReindexStatus(versionId, 0);
  }

  function applyJobProgress(job) {
    return job.status;
  }

  async function pollReindexJob(jobId, attempt = 0) {
    try {
      const job = await fetchJob(jobId);
      const status = applyJobProgress(job);
      notifyUpdated();

      if (status === "done") {
        finishReindexSession();
        ui.success("索引已完成");
        return;
      }

      if (status === "failed" || status === "cancelled") {
        finishReindexSession();
        if (job.error_message) ui.error(job.error_message);
        return;
      }

      if (attempt >= MAX_POLL_ATTEMPTS) {
        finishReindexSession();
        ui.warning("索引仍在进行，可在「后台任务」查看");
        return;
      }

      pollTimer = setTimeout(() => pollReindexJob(jobId, attempt + 1), POLL_INTERVAL_MS);
    } catch (e) {
      finishReindexSession();
      ui.error(e?.message || "获取任务状态失败");
    }
  }

  function startReindexJobPolling(jobId) {
    stopPoll();
    indexPolling.value = true;
    closeJobEvents = subscribePlatformJobEvents(jobId, {
      onUpdate: () => notifyUpdated(),
      onComplete: (job) => {
        const status = applyJobProgress(job);
        finishReindexSession();
        notifyUpdated();
        if (status === "done") ui.success("索引已完成");
        else if (job.error_message) ui.error(job.error_message);
      },
      onError: () => pollReindexJob(jobId, 0),
      onTimeout: () => {
        finishReindexSession();
        ui.warning("索引仍在进行，可在「后台任务」查看");
      },
    });
  }

  async function submitReindex() {
    const version = reindexTargetVersion.value;
    if (!documentId || !version?.id || indexPolling.value) return;
    reparsing.value = true;
    clearReindexSession();
    try {
      const res = await reindexDocument(documentId, {
        versionId: version.id,
        parserId: parserId.value,
        layoutRecognize: layoutRecognize.value,
        resync: true,
      });
      ui.success(res?.message || "已提交重新索引");
      reindexModalShow.value = false;
      if (res?.knowledge_job_id) {
        startReindexJobPolling(res.knowledge_job_id);
      } else {
        startReindexPolling(version.id, version.parse_status || null);
      }
    } catch (e) {
      ui.error(e?.message || "重新索引失败");
    } finally {
      reparsing.value = false;
    }
  }

  onUnmounted(() => {
    stopPoll();
    clearReindexSession();
  });

  return {
    reindexModalShow,
    reindexTargetVersion,
    parserId,
    layoutRecognize,
    chunkMethodOptions,
    layoutOptions,
    pageindexBlockReason,
    reparsing,
    indexPolling,
    loadParserOptions,
    openReindexModal,
    submitReindex,
    reindexSelectMenuProps,
    reindexSelectPlacement,
    renderIndexedSelectLabel,
    reindexSelectNodeProps,
  };
}
