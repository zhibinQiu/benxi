import { LOGIN_FLY_CLONE_CLASS } from "../constants/loginFlyAnimation.js";

/** Naive Modal·Drawer 卸载后残留的遮罩会挡住侧栏点击 */

function isElementVisible(el) {
  if (!(el instanceof Element)) return false;
  const style = getComputedStyle(el);
  if (style.display === "none" || style.visibility === "hidden") return false;
  if (parseFloat(style.opacity) < 0.01) return false;
  return true;
}

function shouldPreserveModalContainer(container) {
  if (container.querySelector(".release-highlights")) return true;
  if (container.querySelector(".platform-confirm-dialog")) return true;
  return false;
}

function removeOrphanedModalContainer(container, { aggressive = false } = {}) {
  if (container.querySelector(".login-auth-modal, .login-glass-panel")) {
    container.remove();
    return;
  }

  if (shouldPreserveModalContainer(container)) return;

  if (aggressive) {
    container.remove();
    return;
  }

  const card = container.querySelector(
    ".n-modal .n-card, .admin-form-modal .n-card, .platform-glass-modal .n-card",
  );
  const mask = container.querySelector(".n-modal-mask");
  if ((mask && !card) || (!mask && !card)) {
    container.remove();
  }
}

function clearBodyScrollLockIfNoOverlayMask() {
  const hasVisibleMask = Array.from(
    document.querySelectorAll("body > .n-modal-container .n-modal-mask, body > .n-drawer-container .n-drawer-mask"),
  ).some(isElementVisible);

  if (!hasVisibleMask) {
    document.body.style.overflow = "";
    document.body.style.paddingRight = "";
    document.body.classList.remove("n-modal-body-lock-scroll");
  }
}

/**
 * @param {{ aggressive?: boolean }} options
 * aggressive: 路由切换时移除子页面弹窗/抽屉（保留版本说明、系统确认框）
 */
export function cleanupBlockingUiArtifacts({ aggressive = false } = {}) {
  document.querySelectorAll(`.${LOGIN_FLY_CLONE_CLASS}`).forEach((el) => el.remove());

  document.querySelectorAll("body > .n-modal-container").forEach((el) => {
    removeOrphanedModalContainer(el, { aggressive });
  });

  document.querySelectorAll("body > .n-drawer-container").forEach((el) => {
    if (el.querySelector(".platform-confirm-dialog")) return;
    if (aggressive) {
      el.remove();
      return;
    }
    const mask = el.querySelector(".n-drawer-mask");
    const body = el.querySelector(".n-drawer-body");
    if (mask && !body) el.remove();
  });

  clearBodyScrollLockIfNoOverlayMask();
}
