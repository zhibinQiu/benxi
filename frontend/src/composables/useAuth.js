import { computed, ref } from "vue";
import {
  clearTokens,
  fetchMe,
  getToken,
  login as apiLogin,
  logout as apiLogout,
  registerUser,
  setTokens,
  trialLogin as apiTrialLogin,
} from "../api/client";
import { isAuthSilentError } from "../utils/authError.js";
import { resetClientSessionState } from "../utils/resetClientSessionState.js";
import { redirectToLoginAfterLogout } from "../utils/sessionGuard.js";
import { bumpSessionEpoch, loggingOut } from "../utils/sessionEpoch.js";

const user = ref(null);
const loading = ref(false);
let loadUserPromise = null;

const GENERIC_DISPLAY_NAMES = new Set(["用户", "User"]);

function resolveDisplayName(profile) {
  if (!profile) return "";
  const candidates = [
    (profile.display_name || "").trim(),
    (profile.username || "").trim(),
    (profile.phone || "").trim(),
    (profile.email || "").trim(),
  ];
  for (const value of candidates) {
    if (value && !GENERIC_DISPLAY_NAMES.has(value)) return value;
  }
  return candidates.find(Boolean) || "";
}

export function useAuth() {
  const isLoggedIn = computed(() => !!getToken());
  const permissions = computed(() => user.value?.permissions || []);

  /** 持有系统管理员权限（sys_admin 角色，与后端 is_system_admin 一致） */
  const isSystemAdmin = computed(() => user.value?.is_system_admin === true);
  /** 唯一内置管理员账号（bootstrap 手机号） */
  const isBootstrapAdmin = computed(() => user.value?.is_bootstrap_admin === true);
  const isSuperuser = isSystemAdmin;

  function hasPerm(code) {
    if (isSystemAdmin.value) return true;
    return permissions.value.includes(code);
  }

  function displayName() {
    return resolveDisplayName(user.value);
  }

  async function loadUser({ force = false } = {}) {
    if (!getToken()) {
      user.value = null;
      loadUserPromise = null;
      return null;
    }
    if (user.value && !force) return user.value;
    if (loadUserPromise && !force) return loadUserPromise;

    loading.value = true;
    loadUserPromise = (async () => {
      try {
        user.value = await fetchMe();
        return user.value;
      } catch (e) {
        if (isAuthSilentError(e)) {
          user.value = null;
          return null;
        }
        const msg = String(e?.message || "");
        const authFailed =
          /401|403|未授权|Unauthorized|Invalid access token|token/i.test(msg);
        if (authFailed) {
          clearTokens();
          user.value = null;
        }
        return null;
      } finally {
        loading.value = false;
        loadUserPromise = null;
      }
    })();
    return loadUserPromise;
  }

  async function login(account, password, captchaToken) {
    loggingOut.value = false;
    resetClientSessionState();
    bumpSessionEpoch();
    const tokens = await apiLogin(account, password, captchaToken);
    setTokens(tokens.access_token, tokens.refresh_token);
    const profile = await loadUser();
    if (!profile) {
      throw new Error(
        getToken()
          ? "获取用户信息失败，请重试"
          : "登录验证失败，请重试"
      );
    }
    return profile;
  }

  async function trialLogin() {
    loggingOut.value = false;
    resetClientSessionState();
    bumpSessionEpoch();
    const tokens = await apiTrialLogin();
    setTokens(tokens.access_token, tokens.refresh_token);
    const profile = await loadUser({ force: true });
    if (!profile) {
      throw new Error(
        getToken()
          ? "获取用户信息失败，请重试"
          : "体验登录失败，请重试"
      );
    }
    return profile;
  }

  async function register({ phone, email, displayName, password, captchaToken }) {
    loggingOut.value = false;
    resetClientSessionState();
    bumpSessionEpoch();
    const tokens = await registerUser({ phone, email, displayName, password, captchaToken });
    setTokens(tokens.access_token, tokens.refresh_token);
    const profile = await loadUser({ force: true });
    if (!profile) {
      throw new Error(
        getToken()
          ? "获取用户信息失败，请重试"
          : "注册验证失败，请重试"
      );
    }
    return profile;
  }

  function logout() {
    loggingOut.value = true;
    apiLogout();
    clearTokens();
    resetClientSessionState();
    bumpSessionEpoch();
    user.value = null;
    loadUserPromise = null;
    redirectToLoginAfterLogout();
  }

  return {
    user,
    loading,
    isLoggedIn,
    permissions,
    hasPerm,
    isSystemAdmin,
    isBootstrapAdmin,
    isSuperuser,
    displayName,
    loadUser,
    login,
    trialLogin,
    register,
    logout,
  };
}
