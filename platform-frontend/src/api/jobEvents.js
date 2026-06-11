/** 平台任务 SSE（对比 / 后台任务 / 重新索引等） */
import { getApiBase, getToken } from "./http.js";

function buildSseUrl(path) {
  const token = getToken();
  const base = getApiBase();
  const q = token ? `?token=${encodeURIComponent(token)}` : "";
  return `${base}${path}${q}`;
}

function parseEventData(event) {
  try {
    return JSON.parse(event.data);
  } catch {
    return null;
  }
}

/**
 * 订阅平台 Job SSE（/api/v1/jobs/{id}/events）
 * @returns {() => void} close
 */
export function subscribePlatformJobEvents(
  jobId,
  { onUpdate, onComplete, onError, onTimeout } = {}
) {
  const es = new EventSource(buildSseUrl(`/api/v1/jobs/${jobId}/events`));

  es.addEventListener("status", (e) => {
    const data = parseEventData(e);
    if (data) onUpdate?.(data);
  });

  es.addEventListener("complete", (e) => {
    const data = parseEventData(e);
    if (data) onComplete?.(data);
    es.close();
  });

  es.addEventListener("timeout", () => {
    onTimeout?.();
    es.close();
  });

  es.onerror = () => {
    onError?.(new Error("SSE 连接中断"));
    es.close();
  };

  return () => es.close();
}

/**
 * 订阅文档对比 Job SSE（/api/v1/compare/jobs/{id}/events）
 */
export function subscribeCompareJobEvents(
  jobId,
  { onUpdate, onComplete, onError, onTimeout } = {}
) {
  const es = new EventSource(buildSseUrl(`/api/v1/compare/jobs/${jobId}/events`));

  es.addEventListener("status", (e) => {
    const data = parseEventData(e);
    if (data) onUpdate?.(data);
  });

  es.addEventListener("complete", (e) => {
    const data = parseEventData(e);
    if (data) onComplete?.(data);
    es.close();
  });

  es.addEventListener("timeout", () => {
    onTimeout?.();
    es.close();
  });

  es.onerror = () => {
    onError?.(new Error("SSE 连接中断"));
    es.close();
  };

  return () => es.close();
}

/** Promise：等待 Job 进入终态（SSE 优先，失败时由调用方自行降级轮询） */
export function waitPlatformJobViaSse(jobId, { timeoutMs = 120000 } = {}) {
  return new Promise((resolve, reject) => {
    let settled = false;
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      close();
      reject(new Error("任务等待超时"));
    }, timeoutMs);

    const close = subscribePlatformJobEvents(jobId, {
      onComplete: (data) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        resolve(data);
      },
      onError: (err) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        reject(err);
      },
      onTimeout: () => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        reject(new Error("任务等待超时"));
      },
    });
  });
}

export function waitCompareJobViaSse(jobId, { timeoutMs = 120000 } = {}) {
  return new Promise((resolve, reject) => {
    let settled = false;
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      close();
      reject(new Error("文档对比超时，请稍后重试"));
    }, timeoutMs);

    const close = subscribeCompareJobEvents(jobId, {
      onComplete: (data) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        resolve(data);
      },
      onError: (err) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        reject(err);
      },
      onTimeout: () => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        reject(new Error("文档对比超时，请稍后重试"));
      },
    });
  });
}
