import { computed, ref } from "vue";
import {
  clearTokens,
  fetchMe,
  getToken,
  login as apiLogin,
  registerUser,
  setTokens,
} from "../api/client";
import { resetClientSessionState } from "../utils/resetClientSessionState.js";
import { bumpSessionEpoch } from "../utils/sessionEpoch.js";

const user = ref(null);
const loading = ref(false);

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
    return user.value?.display_name || user.value?.username || user.value?.phone || "";
  }

  async function loadUser() {
    if (!getToken()) {
      user.value = null;
      return null;
    }
    loading.value = true;
    try {
      user.value = await fetchMe();
      return user.value;
    } catch (e) {
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
    }
  }

  async function login(account, password) {
    resetClientSessionState();
    bumpSessionEpoch();
    const tokens = await apiLogin(account, password);
    setTokens(tokens.access_token, tokens.refresh_token);
    return loadUser();
  }

  async function register({ phone, email, displayName, password }) {
    resetClientSessionState();
    bumpSessionEpoch();
    const tokens = await registerUser({ phone, email, displayName, password });
    setTokens(tokens.access_token, tokens.refresh_token);
    return loadUser();
  }

  function logout() {
    clearTokens();
    resetClientSessionState();
    bumpSessionEpoch();
    user.value = null;
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
    register,
    logout,
  };
}
