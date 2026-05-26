import { computed, ref } from "vue";
import {
  clearTokens,
  fetchMe,
  getToken,
  login as apiLogin,
  registerUser,
  setTokens,
} from "../api/client";

const user = ref(null);
const loading = ref(false);

export function useAuth() {
  const isLoggedIn = computed(() => !!getToken());
  const permissions = computed(() => user.value?.permissions || []);

  function hasPerm(code) {
    if (permissions.value.includes("admin.user")) return true;
    if (user.value?.username === "admin") return true;
    return permissions.value.includes(code);
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
    } catch {
      clearTokens();
      user.value = null;
      return null;
    } finally {
      loading.value = false;
    }
  }

  async function login(username, password) {
    const tokens = await apiLogin(username, password);
    setTokens(tokens.access_token, tokens.refresh_token);
    return loadUser();
  }

  async function register(username, password) {
    const tokens = await registerUser(username, password);
    setTokens(tokens.access_token, tokens.refresh_token);
    return loadUser();
  }

  function logout() {
    clearTokens();
    user.value = null;
  }

  return {
    user,
    loading,
    isLoggedIn,
    permissions,
    hasPerm,
    loadUser,
    login,
    register,
    logout,
  };
}
