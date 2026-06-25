import { getApiBase, getToken, rejectHttpFailure, fetchWithTimeout } from "../api/http.js";

const AUTH_API_IMAGE_RE = /\/api\/v1\/(?:browser-rpa\/screenshot|documents\/[^/]+\/file)\b/;
const MARKDOWN_IMAGE_RE = /!\[[^\]]*\]\(([^)]+)\)/g;

export function isAuthenticatedApiImageUrl(url) {
  return AUTH_API_IMAGE_RE.test(String(url || ""));
}

export function normalizeAuthImageSrc(url) {
  const raw = normalizeChatAttachmentUrl(url);
  if (!raw || !isAuthenticatedApiImageUrl(raw)) return raw;
  return raw;
}

export function collectAuthImageUrlsFromMarkdown(content) {
  const urls = [];
  const text = String(content || "");
  for (const match of text.matchAll(MARKDOWN_IMAGE_RE)) {
    const src = normalizeAuthImageSrc(match[1] || "");
    if (src && isAuthenticatedApiImageUrl(src)) urls.push(src);
  }
  return urls;
}

export function authImageUrlFingerprint(content) {
  return collectAuthImageUrlsFromMarkdown(content).join("\0");
}

export function markdownHasAuthScreenshot(content) {
  return collectAuthImageUrlsFromMarkdown(content).length > 0;
}

export function resolveApiAssetUrl(url) {
  const raw = String(url || "").trim();
  if (!raw) return "";
  if (raw.startsWith("http") || raw.startsWith("blob:") || raw.startsWith("data:")) return raw;
  const base = getApiBase().replace(/\/$/, "");
  if (base && (raw === base || raw.startsWith(`${base}/`))) return raw;
  return `${base}${raw.startsWith("/") ? raw : `/${raw}`}`;
}

/** 流式附件等场景：统一为 /api/v1/... 相对路径，避免与 resolveApiAssetUrl 重复拼接 base */
export function normalizeChatAttachmentUrl(url) {
  const raw = String(url || "").trim();
  if (!raw) return "";
  if (raw.startsWith("http") || raw.startsWith("blob:") || raw.startsWith("data:")) return raw;
  const base = getApiBase().replace(/\/$/, "");
  if (base && raw.startsWith(`${base}/`)) {
    const stripped = raw.slice(base.length);
    return stripped.startsWith("/") ? stripped : `/${stripped}`;
  }
  return raw.startsWith("/") ? raw : `/${raw}`;
}

export async function fetchAuthenticatedImageBlob(url, { signal } = {}) {
  const full = resolveApiAssetUrl(url);
  if (!full) throw new Error("缺少图片地址");
  const token = getToken();
  const res = await fetchWithTimeout(
    full,
    {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      signal,
    },
    60_000
  );
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    rejectHttpFailure(res, { message: text });
  }
  return res.blob();
}

/** 为查看器/下载创建独立于消息 DOM 的 blob URL，避免流式 refresh revoke 后失效 */
export async function resolveStableImageObjectUrl(url, { signal } = {}) {
  const raw = String(url || "").trim();
  if (!raw) throw new Error("缺少图片地址");
  if (raw.startsWith("blob:") || raw.startsWith("data:")) {
    const res = await fetch(raw);
    return URL.createObjectURL(await res.blob());
  }
  if (isAuthenticatedApiImageUrl(raw)) {
    const blob = await fetchAuthenticatedImageBlob(raw, { signal });
    return URL.createObjectURL(blob);
  }
  return raw;
}

export function revokeObjectUrlIfBlob(url) {
  if (String(url || "").startsWith("blob:")) {
    URL.revokeObjectURL(url);
  }
}

const hydratedBlobUrls = new WeakMap();
const imgAbortControllers = new WeakMap();

function abortPendingHydration(img) {
  imgAbortControllers.get(img)?.abort();
  imgAbortControllers.delete(img);
}

export async function hydrateAuthenticatedImagesInElement(root) {
  if (!root) return;
  const imgs = root.querySelectorAll("img[src]");
  const jobs = [];
  for (const img of imgs) {
    const src = normalizeAuthImageSrc(img.getAttribute("src") || "");
    if (!src || !isAuthenticatedApiImageUrl(src)) continue;
    if (img.dataset.authHydrated === "1" && img.src.startsWith("blob:")) continue;
    if (img.dataset.authHydrated === "pending") continue;
    abortPendingHydration(img);
    img.dataset.authHydrated = "pending";
    const ac = new AbortController();
    imgAbortControllers.set(img, ac);
    jobs.push(
      (async () => {
        try {
          const blob = await fetchAuthenticatedImageBlob(src, { signal: ac.signal });
          if (ac.signal.aborted || !img.isConnected) return;
          const objectUrl = URL.createObjectURL(blob);
          const urls = hydratedBlobUrls.get(root) || [];
          urls.push(objectUrl);
          hydratedBlobUrls.set(root, urls);
          img.src = objectUrl;
          img.dataset.authHydrated = "1";
        } catch {
          if (ac.signal.aborted || !img.isConnected) return;
          img.dataset.authHydrated = "error";
          img.alt = img.alt || "截图加载失败";
        } finally {
          if (imgAbortControllers.get(img) === ac) {
            imgAbortControllers.delete(img);
          }
        }
      })()
    );
  }
  await Promise.all(jobs);
}

export function revokeAuthenticatedImagesInElement(root) {
  if (!root) return;
  root.querySelectorAll('img[data-auth-hydrated="pending"]').forEach((img) => {
    abortPendingHydration(img);
  });
  root.querySelectorAll("img[data-auth-hydrated]").forEach((img) => {
    delete img.dataset.authHydrated;
  });
  const urls = hydratedBlobUrls.get(root);
  if (!urls?.length) return;
  for (const url of urls) URL.revokeObjectURL(url);
  hydratedBlobUrls.delete(root);
}
