import { onUnmounted, ref } from "vue";
import { fetchDocument } from "../api/documents.js";
import { subscribePlatformJobEvents } from "../api/jobEvents.js";
import { isDocumentIndexReady } from "../utils/knowledgeIndex.js";
import { navigateWithReturn } from "../utils/navigationReturn.js";

const INDEX_POLL_MS = 4000;
const INDEX_POLL_MAX = 90;

/**
 * 网站收藏/资讯导入文档库：导入后立即给出 document_id，后台跟踪 PDF/索引直至可检索。
 */
export function useSubscriptionImportFlow({ router, route, ui }) {
  const importing = ref(false);
  const indexing = ref(false);
  const documentId = ref(null);

  let closeImportSse = null;
  let indexPollTimer = null;

  function stopImportSse() {
    if (closeImportSse) {
      closeImportSse();
      closeImportSse = null;
    }
  }

  function stopIndexPoll() {
    if (indexPollTimer) {
      clearTimeout(indexPollTimer);
      indexPollTimer = null;
    }
  }

  function stopTracking() {
    stopImportSse();
    stopIndexPoll();
    indexing.value = false;
  }

  function notifyIndexUpdated() {
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("platform:knowledge-index-updated"));
    }
  }

  async function pollDocumentIndex(docId, attempt = 0) {
    try {
      const doc = await fetchDocument(docId);
      if (isDocumentIndexReady(doc)) {
        indexing.value = false;
        ui.success("文档索引已完成，可用于知识检索");
        notifyIndexUpdated();
        return;
      }
      const version = (doc.versions || [])[0];
      const status = version?.parse_status || doc.parse_status || "";
      if (status === "解析失败" || status === "索引失效") {
        indexing.value = false;
        ui.warning("文档索引未完成，可在文档详情页重新索引");
        notifyIndexUpdated();
        return;
      }
      if (attempt >= INDEX_POLL_MAX) {
        indexing.value = false;
        ui.info("索引仍在进行，请稍后在「我的文件」查看状态");
        return;
      }
      indexing.value = true;
      indexPollTimer = setTimeout(
        () => pollDocumentIndex(docId, attempt + 1),
        INDEX_POLL_MS
      );
    } catch {
      if (attempt >= INDEX_POLL_MAX) {
        indexing.value = false;
        return;
      }
      indexPollTimer = setTimeout(
        () => pollDocumentIndex(docId, attempt + 1),
        INDEX_POLL_MS
      );
    }
  }

  function startIndexPoll(docId) {
    stopIndexPoll();
    documentId.value = docId;
    indexing.value = true;
    void pollDocumentIndex(docId, 0);
  }

  function trackImportJob(jobId, docId) {
    stopImportSse();
    documentId.value = docId;
    indexing.value = true;
    closeImportSse = subscribePlatformJobEvents(jobId, {
      onComplete: (data) => {
        stopImportSse();
        if (data?.status === "failed") {
          indexing.value = false;
          ui.warning(data?.error_message || "资讯导入未完成，请稍后重试");
          return;
        }
        startIndexPoll(docId);
      },
      onError: () => {
        stopImportSse();
        startIndexPoll(docId);
      },
    });
  }

  async function runImport(importFn, ...args) {
    importing.value = true;
    try {
      const res = await importFn(...args);
      if (res?.document_id) {
        documentId.value = res.document_id;
      }
      if (res?.queued && res?.job_id && res?.document_id) {
        ui.success("已加入个人级文档库，PDF 生成与知识索引正在后台进行");
        trackImportJob(res.job_id, res.document_id);
      } else if (res?.knowflow_synced) {
        indexing.value = false;
        ui.success("已入「个人级」文档库并同步知识库");
        notifyIndexUpdated();
      } else {
        indexing.value = false;
        ui.success("已入「个人级」文档库");
        notifyIndexUpdated();
      }
      return res;
    } catch (e) {
      ui.error(e.message);
      throw e;
    } finally {
      importing.value = false;
    }
  }

  function openDocument(id = documentId.value) {
    const targetId = id || documentId.value;
    if (!targetId) return;
    void navigateWithReturn(
      router,
      { name: "document-detail", params: { id: String(targetId) } },
      route
    ).catch((err) => {
      if (err?.name === "NavigationDuplicated") return;
      ui.error(err);
    });
  }

  onUnmounted(stopTracking);

  return {
    importing,
    indexing,
    documentId,
    runImport,
    openDocument,
    stopTracking,
  };
}
