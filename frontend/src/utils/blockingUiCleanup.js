import { LOGIN_FLY_CLONE_CLASS } from "../constants/loginFlyAnimation.js";

/**
 * Naive UI teleport 浮层兜底清理（仅处理 DOM 残留，不是弹窗生命周期的主路径）。
 *
 * 主路径：
 * - 功能弹窗：AdminFormModal + useModalLifecycle
 * - 路由切换：router.afterEach
 * - 壳层初始化：useBlockingUiCleanup（MainLayout onMounted）
 */

const MODAL_SURFACE_SELECTOR = ".n-modal.n-card, .n-modal .n-card, .n-modal";
const DIALOG_SURFACE_SELECTOR = ".n-dialog.n-card, .n-dialog .n-card, .n-dialog";
const PRESERVED_MODAL_SELECTOR = ".release-highlights, .platform-confirm-dialog";

function isElementVisible(el) {
  if (!(el instanceof Element)) return false;
  const style = getComputedStyle(el);
  if (style.display === "none" || style.visibility === "hidden") return false;
  if (parseFloat(style.opacity) < 0.01) return false;
  return true;
}

function isElementDisplayed(el) {
  if (!(el instanceof Element)) return false;
  const style = getComputedStyle(el);
  return style.display !== "none" && style.visibility !== "hidden";
}

function shouldPreserveModalContainer(container) {
  const preserved = container.querySelector(PRESERVED_MODAL_SELECTOR);
  return Boolean(preserved && isElementVisible(preserved));
}

function findModalSurface(container) {
  return container.querySelector(MODAL_SURFACE_SELECTOR);
}

function findDialogSurface(container) {
  return container.querySelector(DIALOG_SURFACE_SELECTOR);
}

function isStaleOverlay(mask, surface) {
  const maskVisible = Boolean(mask && isElementVisible(mask));
  const surfaceDisplayed = Boolean(surface && isElementDisplayed(surface));

  if (!mask && !surface) return true;
  if (maskVisible && !surfaceDisplayed) return true;
  return false;
}

function removeStaleModalContainer(container, { aggressive = false } = {}) {
  if (container.querySelector(".login-auth-modal, .login-glass-panel")) {
    container.remove();
    return true;
  }

  if (shouldPreserveModalContainer(container)) return false;
  if (aggressive) {
    container.remove();
    return true;
  }

  const mask = container.querySelector(".n-modal-mask");
  const surface = findModalSurface(container);
  if (!isStaleOverlay(mask, surface)) return false;

  container.remove();
  return true;
}

function removeStaleDialogContainer(container, { aggressive = false } = {}) {
  const confirm = container.querySelector(".platform-confirm-dialog");
  if (confirm && isElementVisible(confirm)) return false;

  if (aggressive) {
    container.remove();
    return true;
  }

  const mask = container.querySelector(".n-dialog-mask");
  const surface = findDialogSurface(container);
  if (!isStaleOverlay(mask, surface)) return false;

  container.remove();
  return true;
}

function removeStaleDrawerContainer(container, { aggressive = false } = {}) {
  const confirm = container.querySelector(".platform-confirm-dialog");
  if (confirm && isElementVisible(confirm)) return false;

  if (aggressive) {
    container.remove();
    return true;
  }

  const mask = container.querySelector(".n-drawer-mask");
  const body = container.querySelector(".n-drawer-body");
  if (!isStaleOverlay(mask, body)) return false;

  container.remove();
  return true;
}

function clearBodyScrollLockIfNoOverlayMask() {
  const hasVisibleMask = Array.from(
    document.querySelectorAll(
      "body > .n-modal-container .n-modal-mask, body > .n-drawer-container .n-drawer-mask, body > .n-dialog-container .n-dialog-mask",
    ),
  ).some(isElementVisible);

  if (!hasVisibleMask) {
    document.body.style.overflow = "";
    document.body.style.paddingRight = "";
    document.body.classList.remove("n-modal-body-lock-scroll");
  }
}

/**
 * @param {{ aggressive?: boolean }} options
 * aggressive: 路由切换时移除页面级弹窗/抽屉（保留版本说明、系统确认框）
 */
export function cleanupBlockingUiArtifacts({ aggressive = false } = {}) {
  document.querySelectorAll(`.${LOGIN_FLY_CLONE_CLASS}`).forEach((el) => el.remove());

  document.querySelectorAll("body > .n-modal-container").forEach((el) => {
    removeStaleModalContainer(el, { aggressive });
  });

  document.querySelectorAll("body > .n-drawer-container").forEach((el) => {
    removeStaleDrawerContainer(el, { aggressive });
  });

  document.querySelectorAll("body > .n-dialog-container").forEach((el) => {
    removeStaleDialogContainer(el, { aggressive });
  });

  clearBodyScrollLockIfNoOverlayMask();
}
