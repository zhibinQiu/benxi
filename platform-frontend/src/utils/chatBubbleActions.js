/** 对话气泡：复制 / 分享助手回复 */

export async function copyChatMessageText(text, { ui, t }) {
  const content = String(text || "").trim();
  if (!content) return false;
  try {
    await navigator.clipboard.writeText(content);
    ui.success(t("chat.copied"));
    return true;
  } catch {
    ui.error(t("chat.copyFailed"));
    return false;
  }
}

export async function shareChatMessageText(text, { ui, t, title, shareUrl = null }) {
  const content = String(text || "").trim();
  if (!content) return false;
  const payload = {
    title: title || t("chat.defaultSubtitle"),
    text: content,
  };
  const url = String(shareUrl || "").trim();
  if (url) payload.url = url;

  try {
    if (navigator.share) {
      await navigator.share(payload);
      return true;
    }
    const shareText = payload.url ? `${content}\n\n${payload.url}` : content;
    await navigator.clipboard.writeText(shareText);
    ui.success(t("chat.shareCopied"));
    return true;
  } catch (e) {
    if (e?.name === "AbortError") return false;
    ui.error(t("chat.shareFailed"));
    return false;
  }
}

export function buildChatShareUrl(conversationId, chatScope) {
  const cid = String(conversationId || "").trim();
  const scope = String(chatScope || "").trim();
  if (!cid || !scope || typeof window === "undefined") return null;
  const url = new URL(window.location.href);
  url.searchParams.set("conversationId", cid);
  return url.toString();
}
