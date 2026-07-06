/** KeepAlive 失活时释放富文本 DOM / 图表实例，降低浏览器内存占用 */

import { revokeAuthenticatedImagesInElement } from "./authenticatedImage.js";
import { disposeEchartsInElement } from "./richMarkdown.js";
import { unmountMermaidInElement } from "./mermaidRender.js";

const RICH_DOM_SELECTOR = ".md-rich, .knowledge-chat-content, .knowledge-citation-card__snippet";

export function disposeRichContentInElement(root) {
  if (!root) return;
  revokeAuthenticatedImagesInElement(root);
  disposeEchartsInElement(root);
  unmountMermaidInElement(root);
  root.querySelectorAll(RICH_DOM_SELECTOR).forEach((el) => {
    el.innerHTML = "";
  });
}
