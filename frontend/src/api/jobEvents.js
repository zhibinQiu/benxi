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
 * 通用 Job SSE 订阅
 * @param {string} eventsPath 如 `/api/v1/jobs/{id}/events`
 * @returns {() => void} close
 */
export function subscribeJobEvents(
  eventsPath,
  { onUpdate, onComplete, onError, onTimeout } = {}
) {
  const es = new EventSource(buildSseUrl(eventsPath));

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

  let onerrorCalled = false;
  es.onerror = () => {
    if (onerrorCalled) return;
    onerrorCalled = true;
    try {
      onError?.(new Error("SSE 连接中断"));
    } finally {
      es.close();
    }
  };

  return () => {
    onerrorCalled = true;
    es.close();
  };
}

/** 订阅平台 Job SSE（/api/v1/jobs/{id}/events） */
export function subscribePlatformJobEvents(jobId, handlers = {}) {
  return subscribeJobEvents(`/api/v1/jobs/${jobId}/events`, handlers);
}

/** 订阅文档对比 Job SSE（/api/v1/compare/jobs/{id}/events） */
export function subscribeCompareJobEvents(jobId, handlers = {}) {
  return subscribeJobEvents(`/api/v1/compare/jobs/${jobId}/events`, handlers);
}

function waitJobViaSse(subscribe, jobId, { timeoutMs = 120000, timeoutMessage = "任务等待超时" } = {}) {
  return new Promise((resolve, reject) => {
    let settled = false;
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      close();
      reject(new Error(timeoutMessage));
    }, timeoutMs);

    const close = subscribe(jobId, {
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
        reject(new Error(timeoutMessage));
      },
    });
  });
}

/** Promise：等待 Job 进入终态（SSE 优先，失败时由调用方自行降级轮询） */
export function waitPlatformJobViaSse(jobId, options = {}) {
  return waitJobViaSse(subscribePlatformJobEvents, jobId, options);
}

export function waitCompareJobViaSse(jobId, options = {}) {
  return waitJobViaSse(subscribeCompareJobEvents, jobId, {
    timeoutMessage: "文档对比超时，请稍后重试",
    ...options,
  });
}
