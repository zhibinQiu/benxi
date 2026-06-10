import { onBeforeUnmount, ref } from "vue";
import { useRouter } from "vue-router";
import {
  consumeSkipAfterLoginMotion,
  resolveInnerRouteTransition,
  shouldSkipInnerRouteMotion,
} from "../utils/routeTransition";

/** 主布局内页路由过渡：守卫注册与清理 */
export function useMainLayoutRouteMotion() {
  const router = useRouter();
  const innerRouteTransition = ref(
    shouldSkipInnerRouteMotion() ? "route-instant" : "route-push",
  );

  const removeBeforeEach = router.beforeEach((to, from) => {
    if (from.name === "login" && shouldSkipInnerRouteMotion()) {
      innerRouteTransition.value = "route-instant";
      return;
    }
    if (from.name && from.name !== "login") {
      innerRouteTransition.value = resolveInnerRouteTransition(from, to);
    }
  });

  const removeAfterEach = router.afterEach((to, from) => {
    if (from.name === "login" && to.name !== "login") {
      consumeSkipAfterLoginMotion();
    }
  });

  onBeforeUnmount(() => {
    removeBeforeEach();
    removeAfterEach();
  });

  return { innerRouteTransition };
}
